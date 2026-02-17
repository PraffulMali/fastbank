from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.loan_type import (
    LoanTypeCreate,
    LoanTypeUpdate,
    LoanTypeResponse,
    LoanTypeWithRateResponse,
)
from app.services.loan_type_service import LoanTypeService
from app.dependencies import require_tenant_admin, require_tenant_member
from app.utils.pagination import Paginator, Page

router = APIRouter(prefix="/loan-types", tags=["Loan Types"])


@router.post("/", response_model=LoanTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_loan_type(
    loan_type_in: LoanTypeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):

    try:
        loan_type = await LoanTypeService.create_loan_type(
            db, loan_type_in, current_user.tenant_id
        )
        return loan_type
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=Page[LoanTypeResponse])
async def list_loan_types(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_member)],
    paginator: Paginator = Depends(),
    include_inactive: bool = False,
):

    return await LoanTypeService.list_loan_types(
        db, current_user.tenant_id, paginator, include_inactive
    )


@router.get("/{loan_type_id}", response_model=LoanTypeWithRateResponse)
async def get_loan_type(
    loan_type_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_member)],
):

    loan_type = await LoanTypeService.get_loan_type_with_rate(
        db, loan_type_id, current_user.tenant_id
    )

    if not loan_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Loan type not found"
        )

    return loan_type


@router.patch("/{loan_type_id}", response_model=LoanTypeResponse)
async def update_loan_type(
    loan_type_id: uuid.UUID,
    loan_type_update: LoanTypeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):

    try:
        loan_type = await LoanTypeService.update_loan_type(
            db, loan_type_id, loan_type_update, current_user.tenant_id
        )

        if not loan_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Loan type not found"
            )

        return loan_type

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/{loan_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loan_type(
    loan_type_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):

    try:
        await LoanTypeService.delete_loan_type(db, loan_type_id, current_user.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
