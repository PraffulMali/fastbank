from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.account_type import (
    AccountTypeCreate,
    AccountTypeUpdate,
    AccountTypeResponse,
    AccountTypeWithRulesResponse
)
from app.services.account_type_service import AccountTypeService
from app.models.enums import UserRole
from app.dependencies import require_admin, require_tenant_admin, require_tenant_member
from app.utils.pagination import Paginator, Page

router = APIRouter(
    prefix="/account-types",
    tags=["Account Types"]
)


@router.post("/", response_model=AccountTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_account_type(
    account_type_in: AccountTypeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    
    try:
        account_type = await AccountTypeService.create_account_type(
            db, account_type_in, current_user.tenant_id
        )
        return account_type
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/", response_model=Page[AccountTypeResponse])
async def list_account_types(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_member)],
    paginator: Paginator = Depends(),
    include_inactive: bool = False
):
    
    return await AccountTypeService.list_account_types(
        db, current_user.tenant_id, paginator, include_inactive
    )


@router.get("/{account_type_id}", response_model=AccountTypeWithRulesResponse)
async def get_account_type(
    account_type_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_member)]
):
    
    account_type = await AccountTypeService.get_account_type_with_rules(
        db, account_type_id, current_user.tenant_id
    )
    
    if not account_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account type not found"
        )
    
    return account_type


@router.patch("/{account_type_id}", response_model=AccountTypeResponse)
async def update_account_type(
    account_type_id: uuid.UUID,
    account_type_update: AccountTypeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    
    try:
        account_type = await AccountTypeService.update_account_type(
            db, account_type_id, account_type_update, current_user.tenant_id
        )
        
        if not account_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account type not found"
            )
        
        return account_type
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.delete("/{account_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account_type(
    account_type_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    
    try:
        await AccountTypeService.delete_account_type(
            db, account_type_id, current_user.tenant_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )