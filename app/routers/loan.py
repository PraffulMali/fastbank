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
    LoanUserResponse,
    AdvanceLoanRepaymentRequest,
    AdvanceLoanRepaymentResponse
)
from app.services.loan_service import LoanService
from app.services.advance_loan_repayment_service import AdvanceLoanRepaymentService
from app.dependencies import get_current_user, require_tenant_admin, require_user
from app.utils.pagination import Paginator, Page

router = APIRouter(
    prefix="/loans",
    tags=["Loans"]
)


@router.post("/", response_model=LoanUserResponse, status_code=status.HTTP_201_CREATED)
async def apply_for_loan(
    loan_in: LoanCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_user)]
):
    """
    Apply for a loan (USER only).
    
    Flow:
    - USER provides: account_id, loan_type_id, principal_amount, tenure_months, loan_purpose
    - System fetches interest rate from INTEREST_RULES based on loan_type_id
    - Interest rate is stored as snapshot in loan record (preserves contract integrity)
    - EMI is calculated and stored
    - Loan is initialized with status=APPLIED, remaining_principal=principal_amount
    - Notifications sent to USER (confirmation) and all ADMINs (new application alert)
    
    Restrictions:
    - Only regular users can apply for loans
    - ADMIN/SUPER_ADMIN: Cannot access this endpoint
    """
    try:
        loan = await LoanService.create_loan_application(
            db,
            loan_in,
            current_user.id,
            current_user.tenant_id
        )
        
        return loan
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/me", response_model=list[LoanUserResponse])
async def get_my_loans(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_user)]
):
    """
    Get all loan applications for current user (USER only).
    - USER: Can view their own loan history with loan_purpose and status
    - ADMIN/SUPER_ADMIN: Cannot access this endpoint
    """
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
    
    On APPROVAL:
    - All operations are atomic within a single database transaction
    - Updates loan status to APPROVED
    - Records decision metadata (decided_by, decided_at)
    - Creates CREDIT transaction for disbursement
    - Updates account balance
    - Sends notifications to user (approval + disbursement)
    
    On REJECTION:
    - Updates loan status to REJECTED
    - Stores rejection_reason (mandatory)
    - Records decision metadata (decided_by, decided_at)
    - Sends notification to user with rejection reason
    
    Critical: Uses atomic transaction boundary to ensure data consistency
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


@router.post("/{loan_id}/advance-repayment", response_model=AdvanceLoanRepaymentResponse)
async def make_advance_loan_repayment(
    loan_id: uuid.UUID,
    repayment_request: AdvanceLoanRepaymentRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_user)]
):
    """
    Make an advance loan repayment (USER only).
    
    This endpoint allows borrowers to make advance payments toward their active approved loans.
    
    **Process Flow:**
    1. Validates loan eligibility (APPROVED status, remaining principal > 0)
    2. Converts payment amount from rupees to paisa
    3. Checks account balance for sufficient funds
    4. Calculates accrued interest using monthly interest rate
    5. Allocates payment: **interest first, then principal**
    6. Reduces loan's remaining_principal by principal component only
    7. Determines if payment results in foreclosure (full payoff)
    8. Recalculates remaining tenure using amortization formula if not foreclosed
    9. Atomically executes:
       - Creates DEBIT transaction (reference_type=LOAN)
       - Updates account balance
       - Updates loan (remaining_principal, tenure, status)
       - Creates loan repayment record
    10. Sends success/failure notifications (and email on failure)
    
    **Payment Allocation:**
    - Interest Component = Remaining Principal × (Annual Rate / 12 / 100)
    - Principal Component = Payment Amount - Interest Component
    - Remaining Principal = Old Remaining Principal - Principal Component
    
    **Tenure Recalculation:**
    - Uses amortization formula: n = -log(1 - (P × r / EMI)) / log(1 + r)
    - Requires EMI > P × r for formula to work
    - If condition not met, tenure remains unchanged (loan may need restructuring)
    
    **Foreclosure:**
    - Triggered when payment clears full outstanding obligation
    - Loan status changes to FORECLOSED
    - Tenure set to 0
    
    **Failure Handling:**
    - If insufficient funds: NO financial state is modified
    - Sends notification and email to user
    - Returns detailed error message
    
    **Restrictions:**
    - Only loan owner (USER) can make advance repayments
    - Loan must be in APPROVED status
    - Loan must have remaining principal > 0
    - Account must have sufficient balance
    """
    success, message, details = await AdvanceLoanRepaymentService.process_advance_repayment(
        db=db,
        loan_id=loan_id,
        payment_amount_rupees=repayment_request.payment_amount,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    return AdvanceLoanRepaymentResponse(
        success=success,
        message=message,
        **details if details else {}
    )