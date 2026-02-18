from typing import Optional
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.tenant import Tenant
from app.models.account_type import AccountType
from app.models.loan_type import LoanType
from app.models.interest_rule import InterestRule
from app.models.enums import RuleType
from app.schemas.tenant import TenantCreate, TenantUpdate
from app.utils.pagination import Paginator, Page


class TenantService:
    @staticmethod
    async def create_tenant(db: AsyncSession, tenant_in: TenantCreate) -> Tenant:
        query = select(Tenant).where(Tenant.name == tenant_in.name)
        result = await db.execute(query)
        existing_tenant = result.scalar_one_or_none()

        if existing_tenant:
            raise ValueError("Tenant with this name already exists")

        new_tenant = Tenant(name=tenant_in.name)
        db.add(new_tenant)
        await db.flush()

        savings_type = AccountType(tenant_id=new_tenant.id, name="SAVINGS")
        current_type = AccountType(tenant_id=new_tenant.id, name="CURRENT")
        db.add_all([savings_type, current_type])
        await db.flush()

        personal_loan = LoanType(tenant_id=new_tenant.id, name="PERSONAL")
        vehicle_loan = LoanType(tenant_id=new_tenant.id, name="VEHICLE")
        db.add_all([personal_loan, vehicle_loan])
        await db.flush()

        rules = []

        rules.append(
            InterestRule(
                tenant_id=new_tenant.id,
                rule_type=RuleType.ACCOUNT,
                account_type_id=savings_type.id,
                min_balance=0,
                max_balance=None,
                interest_rate=4.0,
                is_active=True,
            )
        )

        rules.append(
            InterestRule(
                tenant_id=new_tenant.id,
                rule_type=RuleType.LOAN,
                loan_type_id=personal_loan.id,
                interest_rate=12.0,
                is_active=True,
            )
        )

        rules.append(
            InterestRule(
                tenant_id=new_tenant.id,
                rule_type=RuleType.LOAN,
                loan_type_id=vehicle_loan.id,
                interest_rate=10.0,
                is_active=True,
            )
        )

        db.add_all(rules)

        await db.commit()
        await db.refresh(new_tenant)
        return new_tenant

    @staticmethod
    async def get_tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
        tenant = await db.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError("Tenant not found")
        return tenant

    @staticmethod
    def get_tenants_query(include_inactive: bool = False):
        query = select(Tenant)
        if not include_inactive:
            query = query.where(Tenant.is_active.is_(True))
        return query

    @staticmethod
    async def list_tenants(
        db: AsyncSession, paginator: Paginator, include_inactive: bool = False
    ) -> Page:
        query = TenantService.get_tenants_query(include_inactive)
        return await paginator.paginate(db, query)

    @staticmethod
    async def update_tenant(
        db: AsyncSession, tenant_id: uuid.UUID, tenant_update: TenantUpdate
    ) -> Tenant:
        tenant = await TenantService.get_tenant(db, tenant_id)

        if tenant_update.name is not None and tenant_update.name != tenant.name:
            query = select(Tenant).where(Tenant.name == tenant_update.name)
            result = await db.execute(query)
            if result.scalar_one_or_none():
                raise ValueError("Tenant with this name already exists")
            tenant.name = tenant_update.name

        if tenant_update.is_active is not None:
            tenant.is_active = tenant_update.is_active
            if tenant_update.is_active:
                tenant.deleted_at = None
            else:
                tenant.deleted_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(tenant)
        return tenant

    @staticmethod
    async def soft_delete_tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
        from app.celery.tasks import cascade_soft_delete_tenant

        tenant = await TenantService.get_tenant(db, tenant_id)

        if not tenant.is_active:
            raise ValueError("Tenant is already deleted")

        tenant.is_active = False
        tenant.deleted_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(tenant)

        cascade_soft_delete_tenant.delay(str(tenant_id))

        return tenant
