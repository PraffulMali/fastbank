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
    query = AccountService.get_accounts_query(current_user.tenant_id)
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
    try:
        return await AccountService.get_my_accounts(db, current_user)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


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
    try:
        return await AccountService.get_account_with_permissions(
            db, account_id, current_user.tenant_id
        )
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
    try:
        return await AccountService.update_account_with_permissions(
            db, account_id, account_update, current_user.tenant_id
        )
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
    try:
        await AccountService.soft_delete_account_with_permissions(
            db, account_id, current_user.tenant_id
        )
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