from typing import Optional, List
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import random
import string

from app.models.account import Account
from app.models.user import User
from app.models.enums import UserRole
from app.models.account_type import AccountType
from app.utils.pagination import Paginator, Page
from app.schemas.account import (
    AccountCreateByAdmin, 
    AccountUpdate,
    AccountUserSingleResponse
)


class AccountService:
    
    @staticmethod
    def generate_account_number() -> str:
        digits = ''.join(random.choices(string.digits, k=12))
        return f"ACC{digits}"
    
    @staticmethod
    async def create_account(
        db: AsyncSession,
        account_in: AccountCreateByAdmin,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> Account:
        # Validate user exists and belongs to the same tenant
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        
        if user.tenant_id != tenant_id:
            raise ValueError("User does not belong to this tenant")
        
        if not user.is_active:
            raise ValueError("Cannot create account for inactive user")
        
        # Validate account type exists for this tenant
        account_type_id = account_in.account_type_id
        account_type = await db.get(AccountType, account_type_id)
        
        if not account_type:
            raise ValueError("Account type not found")
            
        if account_type.tenant_id != tenant_id:
            raise ValueError("Account type does not belong to this tenant")
        
        # Check if user already has an account of this type in this tenant
        existing_query = select(Account).where(
            and_(
                Account.tenant_id == tenant_id,
                Account.user_id == user_id,
                Account.account_type_id == account_type_id,
                Account.is_active == True
            )
        )
        result = await db.execute(existing_query)
        existing_account = result.scalar_one_or_none()
        
        if existing_account:
            raise ValueError(f"User already has an active {account_type.name} account")
        
        # Generate unique account number
        account_number = None
        max_attempts = 10
        for _ in range(max_attempts):
            account_number = AccountService.generate_account_number()
            
            # Check if account number already exists
            check_query = select(Account).where(Account.account_number == account_number)
            check_result = await db.execute(check_query)
            if not check_result.scalar_one_or_none():
                break
        else:
            raise ValueError("Failed to generate unique account number")
        
        # Create account
        new_account = Account(
            tenant_id=tenant_id,
            user_id=user_id,
            account_number=account_number,
            account_type_id=account_type_id,
            balance=0,
            currency="INR",
            is_active=True
        )
        
        db.add(new_account)
        await db.commit()
        await db.refresh(new_account)
        
        return new_account
    
    @staticmethod
    async def get_account_by_id(
        db: AsyncSession,
        account_id: uuid.UUID
    ) -> Optional[Account]:
        return await db.get(Account, account_id)
    
    
    @staticmethod
    async def list_user_accounts(
        db: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        include_inactive: bool = False
    ) -> List[Account]:
        query = select(Account).where(
            and_(
                Account.user_id == user_id,
                Account.tenant_id == tenant_id
            )
        )
        
        if not include_inactive:
            query = query.where(Account.is_active == True)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    

    @staticmethod
    def get_accounts_query(tenant_id: uuid.UUID):
        return select(Account).where(Account.tenant_id == tenant_id)

    @staticmethod
    async def list_accounts(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        paginator: Paginator
    ) -> Page:
        query = AccountService.get_accounts_query(tenant_id)
        return await paginator.paginate(db, query)

    @staticmethod
    async def get_my_accounts(
        db: AsyncSession,
        current_user: User
    ):
        accounts = await AccountService.list_user_accounts(
            db,
            current_user.id,
            current_user.tenant_id,
            include_inactive=False
        )
        
        return {"accounts": [AccountUserSingleResponse.model_validate(acc) for acc in accounts]}

    @staticmethod
    async def get_account_with_permissions(
        db: AsyncSession,
        account_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> Account:
        account = await AccountService.get_account_by_id(db, account_id)
        if not account:
            raise ValueError("Account not found")
        
        if account.tenant_id != tenant_id:
            raise PermissionError("Cannot view account from different tenant")
        
        return account

    @staticmethod
    async def update_account_with_permissions(
        db: AsyncSession,
        account_id: uuid.UUID,
        account_update: AccountUpdate,
        tenant_id: uuid.UUID
    ) -> Account:
        account = await AccountService.get_account_by_id(db, account_id)
        if not account:
            raise ValueError("Account not found")
        
        if account.tenant_id != tenant_id:
            raise PermissionError("Cannot update account from different tenant")
        
        return await AccountService.update_account(db, account_id, account_update)

    @staticmethod
    async def soft_delete_account_with_permissions(
        db: AsyncSession,
        account_id: uuid.UUID,
        tenant_id: uuid.UUID
    ):
        account = await AccountService.get_account_by_id(db, account_id)
        if not account:
            raise ValueError("Account not found")
        
        if account.tenant_id != tenant_id:
            raise PermissionError("Cannot delete account from different tenant")
        
        return await AccountService.soft_delete_account(db, account_id)
    
    @staticmethod
    async def update_account(
        db: AsyncSession,
        account_id: uuid.UUID,
        account_update: AccountUpdate
    ) -> Optional[Account]:
        account = await db.get(Account, account_id)
        if not account:
            return None
        
        # Only allow setting is_active to True (reactivation)
        if account_update.is_active:
            account.is_active = True
            account.deleted_at = None
        
        await db.commit()
        await db.refresh(account)
        return account
    
    @staticmethod
    async def soft_delete_account(
        db: AsyncSession,
        account_id: uuid.UUID
    ) -> Optional[Account]:
        account = await db.get(Account, account_id)
        if not account:
            return None
        
        if not account.is_active:
            raise ValueError("Account is already deleted")
        
        # Check if account has balance (optional - remove if you want to allow)
        if account.balance > 0:
            raise ValueError("Cannot delete account with non-zero balance. Please withdraw funds first.")
        
        account.is_active = False
        account.deleted_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(account)
        return account
