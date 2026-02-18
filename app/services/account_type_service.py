from typing import Optional
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.account_type import AccountType
from app.models.interest_rule import InterestRule
from app.models.account import Account
from app.schemas.account_type import AccountTypeCreate, AccountTypeUpdate
from app.utils.pagination import Paginator, Page


class AccountTypeService:

    @staticmethod
    async def create_account_type(
        db: AsyncSession, account_type_in: AccountTypeCreate, tenant_id: uuid.UUID
    ) -> AccountType:
        existing_query = select(AccountType).where(
            and_(
                AccountType.tenant_id == tenant_id,
                AccountType.name == account_type_in.name,
                AccountType.is_active == True,
            )
        )
        result = await db.execute(existing_query)
        if result.scalar_one_or_none():
            raise ValueError(
                f"Account type '{account_type_in.name}' already exists in this tenant"
            )

        new_account_type = AccountType(
            tenant_id=tenant_id, name=account_type_in.name, is_active=True
        )

        db.add(new_account_type)
        await db.commit()
        await db.refresh(new_account_type)

        return new_account_type

    @staticmethod
    async def get_account_type_with_permissions(
        db: AsyncSession, account_type_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> AccountType:
        account_type = await db.get(AccountType, account_type_id)
        if not account_type:
            raise ValueError("Account type not found")

        if account_type.tenant_id != tenant_id:
            raise PermissionError("Cannot access account type from different tenant")

        return account_type

    @staticmethod
    async def list_account_types(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        paginator: Paginator,
        include_inactive: bool = False,
    ) -> Page:
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
        tenant_id: uuid.UUID,
    ) -> Optional[AccountType]:
        account_type = await AccountTypeService.get_account_type_with_permissions(
            db, account_type_id, tenant_id
        )

        if account_type_update.name is not None:
            duplicate_query = select(AccountType).where(
                and_(
                    AccountType.tenant_id == tenant_id,
                    AccountType.name == account_type_update.name,
                    AccountType.id != account_type_id,
                    AccountType.is_active == True,
                )
            )
            result = await db.execute(duplicate_query)
            if result.scalar_one_or_none():
                raise ValueError(
                    f"Account type '{account_type_update.name}' already exists"
                )

            account_type.name = account_type_update.name

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
        db: AsyncSession, account_type_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> None:
        account_type = await AccountTypeService.get_account_type_with_permissions(
            db, account_type_id, tenant_id
        )

        accounts_query = (
            select(func.count())
            .select_from(Account)
            .where(Account.account_type_id == account_type_id)
        )
        result = await db.execute(accounts_query)
        accounts_count = result.scalar_one()

        if accounts_count > 0:
            raise ValueError(
                f"Cannot delete account type: {accounts_count} accounts are using it. "
            )

        rules_query = (
            select(func.count())
            .select_from(InterestRule)
            .where(InterestRule.account_type_id == account_type_id)
        )
        result = await db.execute(rules_query)
        rules_count = result.scalar_one()

        if rules_count > 0:
            raise ValueError(
                f"Cannot delete account type: {rules_count} interest rules are using it. "
                "Delete the interest rules first or set account type to inactive."
            )

        await db.delete(account_type)
        await db.commit()

    @staticmethod
    async def get_account_type_with_rules(
        db: AsyncSession, account_type_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> dict:
        account_type = await AccountTypeService.get_account_type_with_permissions(
            db, account_type_id, tenant_id
        )

        rules_query = (
            select(InterestRule)
            .where(
                and_(
                    InterestRule.account_type_id == account_type_id,
                    InterestRule.is_active == True,
                )
            )
            .order_by(InterestRule.min_balance)
        )

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
                    "min_balance": (
                        float(rule.min_balance) / 100 if rule.min_balance else None
                    ),
                    "max_balance": (
                        float(rule.max_balance) / 100 if rule.max_balance else None
                    ),
                    "interest_rate": float(rule.interest_rate),
                }
                for rule in rules
            ],
        }
