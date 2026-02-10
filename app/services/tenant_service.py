from typing import List, Optional
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.tenant import Tenant
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
        await db.commit()
        await db.refresh(new_tenant)
        return new_tenant

    @staticmethod
    async def get_tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Optional[Tenant]:
        return await db.get(Tenant, tenant_id)

    @staticmethod
    def get_tenants_query():
        """Get base query for listing tenants"""
        return select(Tenant)

    @staticmethod
    async def list_tenants(
        db: AsyncSession,
        paginator: Paginator
    ) -> Page:
        """List tenants with pagination, centralizing query construction in service layer"""
        query = TenantService.get_tenants_query()
        return await paginator.paginate(db, query)

    @staticmethod
    async def update_tenant(
        db: AsyncSession, 
        tenant_id: uuid.UUID, 
        tenant_update: TenantUpdate
    ) -> Optional[Tenant]:
        tenant = await db.get(Tenant, tenant_id)
        if not tenant:
            return None
            
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
    async def soft_delete_tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Optional[Tenant]:
        tenant = await db.get(Tenant, tenant_id)
        if not tenant:
            return None
        
        if not tenant.is_active:
            raise ValueError("Tenant is already deleted")
            
        tenant.is_active = False
        tenant.deleted_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(tenant)
        return tenant

