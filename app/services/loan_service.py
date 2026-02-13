from typing import Optional, List
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.models.loan import Loan
from app.models.account import Account
from app.models.user import User
from app.models.enums import LoanStatus, UserRole
from app.schemas.loan import LoanCreate, LoanApprovalDecision


# LOAN CONFIGURATION CONSTANTS
# TODO: Move these to tenant settings table or config later
DEFAULT_LOAN_INTEREST_RATE = Decimal("12.00")  # 12% annual interest rate
MAX_LOAN_AMOUNT = Decimal("10000000.00")  # ₹1 crore
MIN_LOAN_AMOUNT = Decimal("10000.00")  # ₹10,000


class LoanService:
    
    @staticmethod
    async def create_loan_application(
        db: AsyncSession,
        loan_in: LoanCreate,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> Loan:
        """
        Create a new loan application by USER.
        Interest rate is set automatically from constant.
        Validates:
        - Account belongs to user and tenant
        - Account is active
        - User doesn't have pending loan for same account
        - Principal amount is within limits
        """
        # Validate principal amount limits
        if loan_in.principal_amount < MIN_LOAN_AMOUNT:
            raise ValueError(f"Loan amount must be at least ₹{MIN_LOAN_AMOUNT:,.2f}")
        
        if loan_in.principal_amount > MAX_LOAN_AMOUNT:
            raise ValueError(f"Loan amount cannot exceed ₹{MAX_LOAN_AMOUNT:,.2f}")
        
        # Validate account exists and belongs to user
        account = await db.get(Account, loan_in.account_id)
        if not account:
            raise ValueError("Account not found")
        
        if account.user_id != user_id:
            raise ValueError("Account does not belong to you")
        
        if account.tenant_id != tenant_id:
            raise ValueError("Account does not belong to your tenant")
        
        if not account.is_active:
            raise ValueError("Cannot apply for loan on inactive account")
        
        # Check for existing pending/approved loans on this account
        existing_query = select(Loan).where(
            and_(
                Loan.account_id == loan_in.account_id,
                Loan.user_id == user_id,
                Loan.status.in_([LoanStatus.APPLIED, LoanStatus.APPROVED]),
                Loan.is_active == True
            )
        )
        result = await db.execute(existing_query)
        existing_loan = result.scalar_one_or_none()
        
        if existing_loan:
            raise ValueError(f"You already have a {existing_loan.status.value} loan for this account")
        
        # Create loan application with system-defined interest rate
        new_loan = Loan(
            tenant_id=tenant_id,
            user_id=user_id,
            account_id=loan_in.account_id,
            principal_amount=int(loan_in.principal_amount * 100),
            interest_rate=DEFAULT_LOAN_INTEREST_RATE,  # System sets this, not user
            tenure_months=loan_in.tenure_months,
            loan_purpose=loan_in.loan_purpose,
            status=LoanStatus.APPLIED,
            applied_at=datetime.now(timezone.utc)
        )
        
        db.add(new_loan)
        await db.commit()
        await db.refresh(new_loan)
        
        # Send notification to ADMIN about new loan application
        # Get the user details for notification message
        user = await db.get(User, user_id)
        
        # Get all admin users in this tenant
        admin_query = select(User).where(
            and_(
                User.tenant_id == tenant_id,
                User.role == UserRole.ADMIN,
                User.is_active == True
            )
        )
        admin_result = await db.execute(admin_query)
        admins = list(admin_result.scalars().all())
        
        # Import notification service
        from app.services.notification_service import NotificationService
        from app.models.enums import NotificationType
        
        # Send notification to each admin
        for admin in admins:
            await NotificationService.create_notification(
                db=db,
                tenant_id=tenant_id,
                user_id=admin.id,
                notification_type=NotificationType.LOAN_APPLIED,
                message=f"New loan application from {user.full_name} for ₹{loan_in.principal_amount:,.2f}. Purpose: {loan_in.loan_purpose[:50]}{'...' if len(loan_in.loan_purpose) > 50 else ''}",
                reference_id=new_loan.id,
                reference_type="loan",
                send_websocket=True
            )
        
        return new_loan
    
    @staticmethod
    async def approve_or_reject_loan(
        db: AsyncSession,
        loan_id: uuid.UUID,
        decision: LoanApprovalDecision,
        admin_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> Loan:
        """
        Approve or reject a loan application by ADMIN.
        Admin reviews loan_purpose and other details before deciding.
        If approved:
        - Updates loan status to APPROVED
        - TODO: Create transaction to credit user account
        - TODO: Send notification to user
        - TODO (WebSocket): Push real-time update to user
        """
        loan = await db.get(Loan, loan_id)
        if not loan:
            raise ValueError("Loan not found")
        
        if loan.tenant_id != tenant_id:
            raise ValueError("Cannot process loan from different tenant")
        
        if loan.status != LoanStatus.APPLIED:
            raise ValueError(f"Cannot process loan with status {loan.status.value}")
        
        # Update loan status
        if decision.decision == "APPROVED":
            loan.status = LoanStatus.APPROVED
            
            # Create transaction to credit user's account
            from app.models.transaction import Transaction
            from app.models.enums import TransactionType, TransactionStatus, ReferenceType
            
            # Create CREDIT transaction for loan disbursement
            loan_transaction = Transaction(
                tenant_id=tenant_id,
                account_id=loan.account_id,
                reference_id=loan.id,
                transaction_type=TransactionType.CREDIT,
                reference_type=ReferenceType.LOAN,
                amount=loan.principal_amount,
                status=TransactionStatus.SUCCESS  # Loan disbursement is immediate
            )
            
            db.add(loan_transaction)
            
            # Update account balance
            account = await db.get(Account, loan.account_id)
            if account:
                account.balance += loan.principal_amount
            
            # Send notification to USER about loan approval
            from app.services.notification_service import NotificationService
            from app.models.enums import NotificationType
            
            await NotificationService.create_notification(
                db=db,
                tenant_id=loan.tenant_id,
                user_id=loan.user_id,
                notification_type=NotificationType.LOAN_APPROVED,
                message=f"Your loan of ₹{loan.principal_amount / 100:,.2f} has been approved!",
                reference_id=loan.id,
                reference_type="loan",
                send_websocket=True
            )
            
            # Send loan disbursement notification
            await NotificationService.create_notification(
                db=db,
                tenant_id=loan.tenant_id,
                user_id=loan.user_id,
                notification_type=NotificationType.LOAN_DISBURSED,
                message=f"Loan amount of ₹{loan.principal_amount / 100:,.2f} has been credited to your account {account.account_number}. New balance: ₹{account.balance / 100:,.2f}",
                reference_id=loan_transaction.id,
                reference_type="transaction",
                send_websocket=True
            )
            
        else:  # REJECTED
            loan.status = LoanStatus.REJECTED
            
            # Send notification to USER about loan rejection
            from app.services.notification_service import NotificationService
            from app.models.enums import NotificationType
            
            rejection_message = f"Your loan application has been rejected."
            if decision.rejection_reason:
                rejection_message += f" Reason: {decision.rejection_reason}"
            
            await NotificationService.create_notification(
                db=db,
                tenant_id=loan.tenant_id,
                user_id=loan.user_id,
                notification_type=NotificationType.LOAN_REJECTED,
                message=rejection_message,
                reference_id=loan.id,
                reference_type="loan",
                send_websocket=True
            )
        
        loan.approved_by = admin_id
        loan.decided_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(loan)
        
        return loan
    
    @staticmethod
    async def get_loan_by_id(
        db: AsyncSession,
        loan_id: uuid.UUID
    ) -> Optional[Loan]:
        """Get loan by ID"""
        return await db.get(Loan, loan_id)
    
    @staticmethod
    async def list_user_loans(
        db: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        include_inactive: bool = False
    ) -> List[Loan]:
        """List all loans for a specific user"""
        query = select(Loan).where(
            and_(
                Loan.user_id == user_id,
                Loan.tenant_id == tenant_id
            )
        )
        
        if not include_inactive:
            query = query.where(Loan.is_active == True)
        
        query = query.order_by(Loan.applied_at.desc())
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def list_tenant_loans(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        status: Optional[LoanStatus] = None
    ) -> List[Loan]:
        """
        List all loans in tenant (for ADMIN).
        Optionally filter by status.
        """
        query = select(Loan).where(Loan.tenant_id == tenant_id)
        
        if status:
            query = query.where(Loan.status == status)
        
        query = query.order_by(Loan.applied_at.desc())
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def soft_delete_loan(
        db: AsyncSession,
        loan_id: uuid.UUID
    ) -> Optional[Loan]:
        """
        Soft delete a loan (ADMIN only).
        Only APPLIED or REJECTED loans can be deleted.
        """
        loan = await db.get(Loan, loan_id)
        if not loan:
            return None
        
        if not loan.is_active:
            raise ValueError("Loan is already deleted")
        
        if loan.status not in [LoanStatus.APPLIED, LoanStatus.REJECTED]:
            raise ValueError(f"Cannot delete loan with status {loan.status.value}")
        
        loan.is_active = False
        loan.deleted_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(loan)
        return loan