# app/routers/loan.py

from typing import Annotated, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.enums import UserRole, LoanStatus
from app.schemas.loan import (
    LoanCreate,
    LoanApprovalDecision,
    LoanResponse,
    LoanUserResponse
)
from app.services.loan_service import LoanService
from app.dependencies import get_current_user, require_tenant_admin
from app.utils.pagination import Paginator, Page

router = APIRouter(
    prefix="/loans",
    tags=["Loans"]
)


@router.post("/", response_model=LoanUserResponse, status_code=status.HTTP_201_CREATED)
async def apply_for_loan(
    loan_in: LoanCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Apply for a loan (USER only).
    - USER: Can apply for loan on their own account
    - Requires: account_id, principal_amount, tenure_months, loan_purpose
    - Interest rate is set automatically by the system
    - ADMIN/SUPER_ADMIN: Cannot access this endpoint
    """
    # Only regular users can apply for loans
    if current_user.role != UserRole.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only regular users can apply for loans"
        )
    
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must belong to a tenant"
        )
    
    try:
        loan = await LoanService.create_loan_application(
            db,
            loan_in,
            current_user.id,
            current_user.tenant_id
        )
        
        # TODO (WebSocket): After loan created, notify admins in real-time
        # await notify_admins_new_loan(current_user.tenant_id, loan)
        
        return loan
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/me", response_model=list[LoanUserResponse])
async def get_my_loans(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get all loan applications for current user (USER only).
    - USER: Can view their own loan history with loan_purpose and status
    - ADMIN/SUPER_ADMIN: Cannot access this endpoint
    """
    if current_user.role != UserRole.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only regular users can access this endpoint"
        )
    
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must belong to a tenant"
        )
    
    loans = await LoanService.list_user_loans(
        db,
        current_user.id,
        current_user.tenant_id,
        include_inactive=False
    )
    
    return loans


@router.get("/", response_model=Page[LoanResponse])
async def list_loans(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)],
    status_filter: Optional[str] = Query(None, description="Filter by status: APPLIED, APPROVED, REJECTED"),
    paginator: Paginator = Depends()
):
    """
    List all loans in tenant (ADMIN only).
    - ADMIN: Can view all loans in their tenant with loan_purpose to make decisions
    - Optional status filter
    - SUPER_ADMIN: Cannot access this endpoint
    """
    from sqlalchemy import select
    from app.models.loan import Loan
    
    query = select(Loan).where(Loan.tenant_id == current_user.tenant_id)
    
    if status_filter:
        try:
            status_enum = LoanStatus(status_filter.upper())
            query = query.where(Loan.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: APPLIED, APPROVED, REJECTED"
            )
    
    query = query.order_by(Loan.applied_at.desc())
    
    return await paginator.paginate(db, query)


@router.get("/{loan_id}", response_model=LoanResponse)
async def get_loan(
    loan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    """
    Get specific loan details (ADMIN only).
    - ADMIN: Can view any loan in their tenant including loan_purpose
    - SUPER_ADMIN: Cannot access this endpoint
    """
    loan = await LoanService.get_loan_by_id(db, loan_id)
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loan not found"
        )
    
    if loan.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view loan from different tenant"
        )
    
    return loan


@router.post("/{loan_id}/decision", response_model=LoanResponse)
async def process_loan_application(
    loan_id: uuid.UUID,
    decision: LoanApprovalDecision,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    """
    Approve or reject a loan application (ADMIN only).
    - ADMIN: Reviews loan_purpose and decides to approve/reject
    - On approval: loan status → APPROVED (transaction will be created later)
    - On rejection: loan status → REJECTED with mandatory rejection_reason
    - SUPER_ADMIN: Cannot access this endpoint
    """
    loan = await LoanService.get_loan_by_id(db, loan_id)
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loan not found"
        )
    
    if loan.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot process loan from different tenant"
        )
    
    try:
        updated_loan = await LoanService.approve_or_reject_loan(
            db,
            loan_id,
            decision,
            current_user.id,
            current_user.tenant_id
        )
        
        # TODO (WebSocket): After loan decision, notify user in real-time
        # if decision.decision == "APPROVED":
        #     await notify_user_loan_approved(updated_loan.user_id, updated_loan)
        # else:
        #     await notify_user_loan_rejected(updated_loan.user_id, updated_loan, decision.rejection_reason)
        
        return updated_loan
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loan(
    loan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_tenant_admin)]
):
    """
    Soft delete a loan (ADMIN only).
    - ADMIN: Can delete loans in their tenant
    - Only APPLIED or REJECTED loans can be deleted
    - SUPER_ADMIN: Cannot access this endpoint
    """
    loan = await LoanService.get_loan_by_id(db, loan_id)
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loan not found"
        )
    
    if loan.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete loan from different tenant"
        )
    
    try:
        await LoanService.soft_delete_loan(db, loan_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )