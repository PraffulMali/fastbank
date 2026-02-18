from typing import Annotated, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.enums import LoanStatus
from app.schemas.loan import (
    LoanCreate,
    LoanApprovalDecision,
    LoanResponse,
    LoanUserResponse,
    AdvanceLoanRepaymentRequest,
    AdvanceLoanRepaymentResponse,
    LoanRepaymentResponse,
)
from app.models.loan_repayment import LoanRepayment
from app.models.loan import Loan
from app.services.loan_service import LoanService
from app.services.advance_loan_repayment_service import AdvanceLoanRepaymentService
from app.dependencies import require_tenant_admin, require_user
from app.utils.pagination import Paginator, Page

router = APIRouter(prefix="/loans", tags=["Loans"])


@router.post("/", response_model=LoanUserResponse, status_code=status.HTTP_201_CREATED)
async def apply_for_loan(
    loan_in: LoanCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_user)],
):
    try:
        loan = await LoanService.create_loan_application(
            db, loan_in, current_user.id, current_user.tenant_id
        )

        return loan
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/me", response_model=list[LoanUserResponse])
async def get_my_loans(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_user)],
):
    loans = await LoanService.list_user_loans(
        db, current_user.id, current_user.tenant_id, include_inactive=False
    )

    return loans


@router.get("/", response_model=Page[LoanResponse])
async def list_loans(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
    status_filter: Optional[str] = Query(
        None, description="Filter by status: APPLIED, APPROVED, REJECTED"
    ),
    paginator: Paginator = Depends(),
    include_inactive: bool = Query(True, description="Include inactive loans"),
):

    query = select(Loan).where(Loan.tenant_id == current_user.tenant_id)

    if not include_inactive:
        query = query.where(Loan.is_active.is_(True))

    if status_filter:
        try:
            status_enum = LoanStatus(status_filter.upper())
            query = query.where(Loan.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: APPLIED, APPROVED, REJECTED",
            )

    query = query.order_by(Loan.applied_at.desc())

    return await paginator.paginate(db, query)


@router.get("/{loan_id}", response_model=LoanResponse)
async def get_loan(
    loan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):
    loan = await LoanService.get_loan_by_id(db, loan_id)
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found"
        )

    if loan.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view loan from different tenant",
        )

    return loan


@router.post("/{loan_id}/decision", response_model=LoanResponse)
async def process_loan_application(
    loan_id: uuid.UUID,
    decision: LoanApprovalDecision,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):
    loan = await LoanService.get_loan_by_id(db, loan_id)
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found"
        )

    if loan.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot process loan from different tenant",
        )

    try:
        updated_loan = await LoanService.approve_or_reject_loan(
            db, loan_id, decision, current_user.id, current_user.tenant_id
        )

        return updated_loan
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loan(
    loan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):
    loan = await LoanService.get_loan_by_id(db, loan_id)
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found"
        )

    if loan.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete loan from different tenant",
        )

    try:
        await LoanService.soft_delete_loan(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{loan_id}/advance-repayment", response_model=AdvanceLoanRepaymentResponse
)
async def make_advance_loan_repayment(
    loan_id: uuid.UUID,
    repayment_request: AdvanceLoanRepaymentRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_user)],
    background_tasks: BackgroundTasks,
):
    success, message, details = (
        await AdvanceLoanRepaymentService.process_advance_repayment(
            db=db,
            loan_id=loan_id,
            payment_amount_rupees=repayment_request.payment_amount,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            background_tasks=background_tasks,
        )
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return AdvanceLoanRepaymentResponse(
        success=success, message=message, **details if details else {}
    )


@router.get("/{loan_id}/repayments", response_model=Page[LoanRepaymentResponse])
async def list_loan_repayments(
    loan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
    paginator: Paginator = Depends(),
):

    loan = await LoanService.get_loan_by_id(db, loan_id)
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found"
        )

    if loan.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view repayments for loan from different tenant",
        )

    query = (
        select(LoanRepayment)
        .where(LoanRepayment.loan_id == loan_id)
        .order_by(LoanRepayment.payment_date.desc())
    )

    return await paginator.paginate(db, query)


@router.get(
    "/{loan_id}/repayments/{repayment_id}", response_model=LoanRepaymentResponse
)
async def get_loan_repayment(
    loan_id: uuid.UUID,
    repayment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
):

    loan = await LoanService.get_loan_by_id(db, loan_id)
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found"
        )

    if loan.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view repayments for loan from different tenant",
        )

    query = select(LoanRepayment).where(
        LoanRepayment.id == repayment_id, LoanRepayment.loan_id == loan_id
    )
    result = await db.execute(query)
    repayment = result.scalar_one_or_none()

    if not repayment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repayment not found"
        )

    return repayment
