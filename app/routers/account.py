from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.account import (
    AccountCreateByAdmin,
    AccountUpdate,
    AccountResponse,
    AccountUserResponse
)
from app.services.account_service import AccountService
from app.dependencies import get_current_user, require_tenant_admin  # Import from dependencies
from app.utils.pagination import Paginator, Page

router = APIRouter(
    prefix="/accounts",
    tags=["Accounts"]
)


@router.post("/", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    account_in: AccountCreateByAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    """
    Create an account for a user (ADMIN only).
    - ADMIN: Can create accounts for users in their tenant
    - Requires: user_id and account_type in body
    - SUPER_ADMIN: Cannot access this endpoint
    """
    try:
        account = await AccountService.create_account(
            db,
            account_in,
            account_in.user_id,
            current_user.tenant_id
        )
        return account
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/", response_model=Page[AccountResponse])
async def list_accounts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
    paginator: Paginator = Depends()
):
    """
    List all accounts in the tenant (ADMIN only).
    - ADMIN: Can list all accounts in their tenant
    - SUPER_ADMIN: Cannot access this endpoint
    """
    from sqlalchemy import select
    from app.models.account import Account
    
    query = select(Account).where(Account.tenant_id == current_user.tenant_id)
    return await paginator.paginate(db, query)


@router.get("/me", response_model=AccountUserResponse)
async def get_my_accounts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get all accounts for the current user (USER only).
    - USER: Can view their own accounts (without is_active and deleted_at)
    - ADMIN: Cannot access this endpoint (admins don't have accounts)
    - SUPER_ADMIN: Cannot access this endpoint
    """
    # Only regular users can access this endpoint
    if current_user.role != UserRole.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only regular users can access this endpoint. Admins don't have accounts."
        )
    
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must belong to a tenant"
        )
    
    accounts = await AccountService.list_user_accounts(
        db,
        current_user.id,
        current_user.tenant_id,
        include_inactive=False
    )
    
    # Convert Account objects to AccountUserSingleResponse (without is_active and deleted_at)
    from app.schemas.account import AccountUserSingleResponse
    account_responses = [AccountUserSingleResponse.model_validate(acc) for acc in accounts]
    
    return {"accounts": account_responses}


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    """
    Get specific account details (ADMIN only).
    - ADMIN: Can view any account in their tenant
    - SUPER_ADMIN: Cannot access this endpoint
    """
    account = await AccountService.get_account_by_id(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    # Check if account belongs to admin's tenant
    if account.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view account from different tenant"
        )
    
    return account


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    account_update: AccountUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    """
    Update account - only to reactivate account (ADMIN only).
    - ADMIN: Can reactivate accounts in their tenant
    - Only is_active can be updated (to restore deleted accounts)
    - SUPER_ADMIN: Cannot access this endpoint
    """
    account = await AccountService.get_account_by_id(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    if account.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update account from different tenant"
        )
    
    try:
        updated_account = await AccountService.update_account(db, account_id, account_update)
        return updated_account
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    """
    Soft delete an account (ADMIN only).
    - ADMIN: Can delete accounts in their tenant
    - Sets is_active to False and deleted_at to current timestamp
    - SUPER_ADMIN: Cannot access this endpoint
    """
    account = await AccountService.get_account_by_id(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    if account.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete account from different tenant"
        )
    
    try:
        await AccountService.soft_delete_account(db, account_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )