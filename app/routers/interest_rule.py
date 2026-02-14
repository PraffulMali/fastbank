from typing import Annotated, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.database import get_db
from app.models.user import User
from app.schemas.interest_rule import (
    InterestRuleCreate,
    InterestRuleUpdate,
    InterestRuleResponse,
    InterestRuleDetailResponse
)
from app.services.interest_rule_service import InterestRuleService
from app.models.enums import UserRole
from app.dependencies import require_admin, get_current_user
from app.utils.pagination import Paginator, Page

router = APIRouter(
    prefix="/interest-rules",
    tags=["Interest Rules"]
)


@router.post("/", response_model=InterestRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_interest_rule(
    rule_in: InterestRuleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Create a new interest rule (ADMIN only).
    
    **For ACCOUNT rules:**
    - Requires: account_type_id, min_balance, interest_rate
    - Optional: max_balance (NULL = unlimited)
    - Must NOT have: loan_type_id
    
    **For LOAN rules:**
    - Requires: loan_type_id, interest_rate
    - Must NOT have: account_type_id, min_balance, max_balance
    
    Validation is automatic - just provide the right fields!
    """
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin must belong to a tenant"
        )
    
    try:
        rule = await InterestRuleService.create_interest_rule(
            db, rule_in, current_user.tenant_id
        )
        return rule
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/", response_model=Page[InterestRuleResponse])
async def list_interest_rules(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    paginator: Paginator = Depends()
):
    """
    List all interest rules in tenant.
    - Accessible to: Tenant Admin, Tenant User
    - Not accessible to: Super Admin
    """
    if current_user.role == UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin cannot access this resource"
        )

    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must belong to a tenant"
        )
    
    return await InterestRuleService.list_interest_rules(
        db, current_user.tenant_id, paginator
    )


@router.get("/{rule_id}", response_model=InterestRuleDetailResponse)
async def get_interest_rule(
    rule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get interest rule details.
    - Accessible to: Tenant Admin, Tenant User
    - Not accessible to: Super Admin
    """
    if current_user.role == UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin cannot access this resource"
        )

    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must belong to a tenant"
        )
    
    rule = await InterestRuleService.get_interest_rule_detail(
        db, rule_id, current_user.tenant_id
    )
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interest rule not found"
        )
    
    return rule


@router.patch("/{rule_id}", response_model=InterestRuleResponse)
async def update_interest_rule(
    rule_id: uuid.UUID,
    rule_update: InterestRuleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Update interest rule (ADMIN only).
    - Only interest_rate can be updated
    - Cannot change rule_type, account_type, loan_type, or balance ranges
    - To change other fields, delete and create new rule
    """
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin must belong to a tenant"
        )
    
    try:
        rule = await InterestRuleService.update_interest_rule(
            db, rule_id, rule_update, current_user.tenant_id
        )
        
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interest rule not found"
            )
        
        return rule
    
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interest_rule(
    rule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Delete interest rule (ADMIN only) - HARD DELETE.
    - No protection checks (safe to delete)
    - Rules are configuration, not transactional data
    """
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin must belong to a tenant"
        )
    
    try:
        await InterestRuleService.delete_interest_rule(
            db, rule_id, current_user.tenant_id
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