from typing import Optional
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.account_type import AccountType
from app.models.interest_rule import InterestRule
from app.schemas.account_type import AccountTypeCreate, AccountTypeUpdate
from app.utils.pagination import Paginator, Page


class AccountTypeService:
    
    @staticmethod
    async def create_account_type(
        db: AsyncSession,
        account_type_in: AccountTypeCreate,
        tenant_id: uuid.UUID
    ) -> AccountType:
        """
        Create a new account type for a tenant.
        Validates that name is unique within the tenant.
        """
        # Check for duplicate name within tenant
        existing_query = select(AccountType).where(
            and_(
                AccountType.tenant_id == tenant_id,
                AccountType.name == account_type_in.name,
                AccountType.is_active == True
            )
        )
        result = await db.execute(existing_query)
        if result.scalar_one_or_none():
            raise ValueError(f"Account type '{account_type_in.name}' already exists in this tenant")
        
        # Create account type
        new_account_type = AccountType(
            tenant_id=tenant_id,
            name=account_type_in.name,
            is_active=True
        )
        
        db.add(new_account_type)
        await db.commit()
        await db.refresh(new_account_type)
        
        return new_account_type
    
    @staticmethod
    async def get_account_type_by_id(
        db: AsyncSession,
        account_type_id: uuid.UUID
    ) -> Optional[AccountType]:
        """Get account type by ID"""
        return await db.get(AccountType, account_type_id)
    
    @staticmethod
    async def list_account_types(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        paginator: Paginator,
        include_inactive: bool = False
    ) -> Page:
        """
        List all account types for a tenant.
        By default, only active types are shown.
        """
        query = select(AccountType).where(AccountType.tenant_id == tenant_id)
        
        if not include_inactive:
            query = query.where(AccountType.is_active == True)
        
        query = query.order_by(AccountType.created_at.desc())
        
        return await paginator.paginate(db, query)
    
    @staticmethod
    async def update_account_type(
        db: AsyncSession,
        account_type_id: uuid.UUID,
        account_type_update: AccountTypeUpdate,
        tenant_id: uuid.UUID
    ) -> Optional[AccountType]:
        """
        Update account type.
        Validates tenant ownership.
        """
        account_type = await db.get(AccountType, account_type_id)
        if not account_type:
            return None
        
        # Verify ownership
        if account_type.tenant_id != tenant_id:
            raise PermissionError("Cannot update account type from different tenant")
        
        # Update name if provided
        if account_type_update.name is not None:
            # Check for duplicate name
            duplicate_query = select(AccountType).where(
                and_(
                    AccountType.tenant_id == tenant_id,
                    AccountType.name == account_type_update.name,
                    AccountType.id != account_type_id,
                    AccountType.is_active == True
                )
            )
            result = await db.execute(duplicate_query)
            if result.scalar_one_or_none():
                raise ValueError(f"Account type '{account_type_update.name}' already exists")
            
            account_type.name = account_type_update.name
        
        # Update is_active if provided
        if account_type_update.is_active is not None:
            account_type.is_active = account_type_update.is_active
            if account_type_update.is_active:
                account_type.deleted_at = None
            else:
                account_type.deleted_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(account_type)
        return account_type
    
    @staticmethod
    async def delete_account_type(
        db: AsyncSession,
        account_type_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> None:
        """
        Hard delete an account type with protection.
        Checks if any interest rules reference this account type.
        Raises ValueError if rules exist.
        """
        account_type = await db.get(AccountType, account_type_id)
        if not account_type:
            raise ValueError("Account type not found")
        
        # Verify ownership
        if account_type.tenant_id != tenant_id:
            raise PermissionError("Cannot delete account type from different tenant")
        
        # Check if any interest rules use this account type
        rules_query = select(func.count()).select_from(InterestRule).where(
            InterestRule.account_type_id == account_type_id
        )
        result = await db.execute(rules_query)
        count = result.scalar_one()
        
        if count > 0:
            raise ValueError(
                f"Cannot delete account type: {count} interest rule(s) are using it. "
                "Delete the interest rules first or set account type to inactive."
            )
        
        # Safe to delete
        await db.delete(account_type)
        await db.commit()
    
    @staticmethod
    async def get_account_type_with_rules(
        db: AsyncSession,
        account_type_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> Optional[dict]:
        """
        Get account type with its interest rules.
        Returns dict with account type info and rules.
        """
        account_type = await db.get(AccountType, account_type_id)
        if not account_type or account_type.tenant_id != tenant_id:
            return None
        
        # Get interest rules for this account type
        rules_query = select(InterestRule).where(
            and_(
                InterestRule.account_type_id == account_type_id,
                InterestRule.is_active == True
            )
        ).order_by(InterestRule.min_balance)
        
        result = await db.execute(rules_query)
        rules = list(result.scalars().all())
        
        return {
            "id": account_type.id,
            "tenant_id": account_type.tenant_id,
            "name": account_type.name,
            "is_active": account_type.is_active,
            "created_at": account_type.created_at,
            "interest_rules": [
                {
                    "id": rule.id,
                    "min_balance": float(rule.min_balance) / 100 if rule.min_balance else None,
                    "max_balance": float(rule.max_balance) / 100 if rule.max_balance else None,
                    "interest_rate": float(rule.interest_rate)
                }
                for rule in rules
            ]
        }