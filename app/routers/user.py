from typing import Annotated, Union
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config.settings import settings
from app.utils.email import send_verification_email
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.user import (
    UserCreateBySuperAdmin,
    UserCreateByAdmin,
    UserUpdate,
    UserListResponse,
    UserDetailResponse,
    UserSelfResponse
)
from app.services.user_service import UserService
from app.dependencies import get_current_user, require_super_admin, require_admin
from app.utils.pagination import Paginator, Page

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

@router.post("/", response_model=UserListResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: Union[UserCreateBySuperAdmin, UserCreateByAdmin],
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Create a new user.
    - SUPER_ADMIN: Can create ADMIN users for any tenant
    - ADMIN: Can create USER users within their own tenant
    """
    try:
        if current_user.role == UserRole.SUPER_ADMIN:
            # Validate that the input is UserCreateBySuperAdmin
            if not isinstance(user_in, UserCreateBySuperAdmin):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="SUPER_ADMIN must provide tenant_id"
                )
            new_user, token, temp_password = await UserService.create_user_by_super_admin(db, user_in)
            
        else:  # ADMIN
            # Validate that the input is UserCreateByAdmin
            if isinstance(user_in, UserCreateBySuperAdmin):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ADMIN cannot specify tenant_id"
                )
            new_user, token, temp_password = await UserService.create_user_by_admin(
                db, user_in, current_user.tenant_id, current_user.id
            )
        
        # Send verification email asynchronously
        background_tasks.add_task(
            send_verification_email, 
            new_user.email, 
            token, 
            temp_password, 
            str(new_user.id)
        )
        
        return new_user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/", response_model=Page[UserListResponse])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    paginator: Paginator = Depends()
):
    """
    List users based on role:
    - SUPER_ADMIN: Lists all ADMIN users across all tenants
    - ADMIN: Lists all users within their own tenant
    """
    from sqlalchemy import select
    from app.models.user import User as UserModel
    
    if current_user.role == UserRole.SUPER_ADMIN:
        query = select(UserModel).where(UserModel.role == UserRole.ADMIN)
    else:  # ADMIN
        query = select(UserModel).where(UserModel.tenant_id == current_user.tenant_id)
    
    return await paginator.paginate(db, query)


@router.get("/{user_id}", response_model=Union[UserDetailResponse, UserSelfResponse])
async def get_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Retrieve user details:
    - SUPER_ADMIN: Can view any ADMIN user
    - ADMIN: Can view any user in their tenant
    - USER: Can only view their own profile (limited fields)
    """
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if current_user.role == UserRole.SUPER_ADMIN:
        if user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="SUPER_ADMIN can only view ADMIN users"
            )
        return UserDetailResponse.model_validate(user)
    
    elif current_user.role == UserRole.ADMIN:
        if user.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot view users from other tenants"
            )
        return UserDetailResponse.model_validate(user)
    
    else:  
        if user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own profile"
            )
        return UserSelfResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: uuid.UUID,
    user_update: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Update user details.
    - SUPER_ADMIN: Can update any ADMIN user
    - ADMIN: Can update any user in their tenant
    """
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if current_user.role == UserRole.SUPER_ADMIN:
        if user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="SUPER_ADMIN can only update ADMIN users"
            )
    else: 
        if user.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update users from other tenants"
            )
    
    try:
        updated_user = await UserService.update_user(db, user_id, user_update)
        return updated_user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Soft delete a user.
    - SUPER_ADMIN: Can delete any ADMIN user
    - ADMIN: Can delete any user in their tenant
    """
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if current_user.role == UserRole.SUPER_ADMIN:
        if user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="SUPER_ADMIN can only delete ADMIN users"
            )
    else: 
        if user.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete users from other tenants"
            )
    
    try:
        await UserService.soft_delete_user(db, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
