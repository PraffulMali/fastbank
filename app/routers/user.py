from typing import Annotated, Union
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config.settings import settings
from app.services.email_service import EmailService
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.user import (
    UserCreateBySuperAdmin,
    UserCreateByAdmin,
    UserUpdate,
    UserListResponse,
    UserDetailResponse,
    UserSelfResponse,
    ChangePasswordRequest
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
    try:
        new_user, token, temp_password = await UserService.create_user(db, user_in, current_user)
        
        background_tasks.add_task(
            EmailService.send_verification_email,
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
    return await UserService.list_users(db, current_user, paginator)


@router.get("/{user_id}", response_model=Union[UserDetailResponse, UserSelfResponse])
async def get_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    try:
        return await UserService.get_user_with_permissions(db, user_id, current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.patch("/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: uuid.UUID,
    user_update: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)]
):
    try:
        updated_user = await UserService.update_user_with_permissions(
            db, user_id, user_update, current_user
        )
        return updated_user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
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
    try:
        await UserService.soft_delete_user_with_permissions(db, user_id, current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    password_data: ChangePasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    try:
        await UserService.change_password(
            db,
            current_user.id,
            password_data.old_password,
            password_data.new_password
        )
        return {"message": "Password changed successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )
