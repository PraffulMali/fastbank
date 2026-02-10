from typing import Annotated, List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse
from app.services.tenant_service import TenantService
from app.dependencies import require_super_admin
from app.utils.pagination import Paginator, Page

router = APIRouter(
    prefix="/tenants",
    tags=["Tenants"],
    dependencies=[Depends(require_super_admin)]
)

@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_in: TenantCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await TenantService.create_tenant(db, tenant_in)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/", response_model=Page[TenantResponse])
async def list_tenants(
    db: Annotated[AsyncSession, Depends(get_db)],
    paginator: Paginator = Depends()
):
    query = TenantService.get_tenants_query()
    return await paginator.paginate(db, query)

@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tenant = await TenantService.get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    return tenant

@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: uuid.UUID,
    tenant_update: TenantUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        tenant = await TenantService.update_tenant(db, tenant_id, tenant_update)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        return tenant
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        tenant = await TenantService.soft_delete_tenant(db, tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
