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
    AccountUserResponse,
)
from app.services.account_service import AccountService
from app.dependencies import get_current_user, require_tenant_admin, require_user
from app.utils.pagination import Paginator, Page

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post("/", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    account_in: AccountCreateByAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):
    try:
        account = await AccountService.create_account(
            db, account_in, account_in.user_id, current_user.tenant_id
        )
        return account
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=Page[AccountResponse])
async def list_accounts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
    paginator: Paginator = Depends(),
):
    return await AccountService.list_accounts(db, current_user.tenant_id, paginator)


@router.get("/me", response_model=AccountUserResponse)
async def get_my_accounts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_user)],
):
    try:
        return await AccountService.get_my_accounts(db, current_user)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):
    try:
        return await AccountService.get_account_with_permissions(
            db, account_id, current_user.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    account_update: AccountUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):
    try:
        return await AccountService.update_account_with_permissions(
            db, account_id, account_update, current_user.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):
    try:
        await AccountService.soft_delete_account_with_permissions(
            db, account_id, current_user.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
