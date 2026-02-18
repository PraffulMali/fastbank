from typing import Annotated, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.interest_rule import (
    InterestRuleCreate,
    InterestRuleUpdate,
    InterestRuleResponse,
)
from app.services.interest_rule_service import InterestRuleService
from app.dependencies import require_tenant_admin, require_tenant_member
from app.utils.pagination import Paginator, Page

router = APIRouter(prefix="/interest-rules", tags=["Interest Rules"])


@router.post(
    "/", response_model=InterestRuleResponse, status_code=status.HTTP_201_CREATED
)
async def create_interest_rule(
    rule_in: InterestRuleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):

    try:
        rule = await InterestRuleService.create_interest_rule(
            db, rule_in, current_user.tenant_id
        )
        return rule
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=Page[InterestRuleResponse])
async def list_interest_rules(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_member)],
    paginator: Paginator = Depends(),
    include_inactive: Optional[bool] = Query(
        None, description="Include inactive interest rules"
    ),
):

    if include_inactive is None:
        include_inactive = current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

    return await InterestRuleService.list_interest_rules(
        db, current_user.tenant_id, paginator, include_inactive
    )


@router.get("/{rule_id}", response_model=InterestRuleResponse)
async def get_interest_rule(
    rule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_member)],
):

    try:
        return await InterestRuleService.get_interest_rule_detail(
            db, rule_id, current_user.tenant_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{rule_id}", response_model=InterestRuleResponse)
async def update_interest_rule(
    rule_id: uuid.UUID,
    rule_update: InterestRuleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):

    try:
        return await InterestRuleService.update_interest_rule(
            db, rule_id, rule_update, current_user.tenant_id
        )

    except ValueError as e:
        if str(e) == "Interest rule not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interest_rule(
    rule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):

    try:
        await InterestRuleService.delete_interest_rule(
            db, rule_id, current_user.tenant_id
        )
    except ValueError as e:
        if str(e) == "Interest rule not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
