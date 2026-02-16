from typing import Optional, List
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.loan import Loan
from app.models.loan_type import LoanType
from app.models.interest_rule import InterestRule
from app.models.account import Account
from app.models.user import User
from app.models.enums import LoanStatus, UserRole, RuleType
from app.schemas.loan import LoanCreate, LoanApprovalDecision


# LOAN CONFIGURATION CONSTANTS
MAX_LOAN_AMOUNT = Decimal("10000000.00")  # ₹1 crore
MIN_LOAN_AMOUNT = Decimal("10000.00")  # ₹10,000


class LoanService:
    
    @staticmethod
    def calculate_emi(
        principal_paisa: int,
        annual_interest_rate: Decimal,
        tenure_months: int
    ) -> int:
        """
        Calculate EMI (Equated Monthly Installment) using the standard formula:
        EMI = [P x R x (1+R)^N] / [(1+R)^N-1]
        
        Where:
        P = Principal loan amount (in paisa)
        R = Monthly interest rate (annual rate / 12 / 100)
        N = Tenure in months
        
        Returns EMI in paisa (integer)
        """
        if tenure_months == 0:
            return principal_paisa
        
        # Convert annual interest rate to monthly rate
        monthly_rate = annual_interest_rate / Decimal("12") / Decimal("100")
        
        if monthly_rate == 0:
            # If interest rate is 0, EMI is simply principal / tenure
            return int(principal_paisa / tenure_months)
        
        # Calculate (1 + R)^N
        one_plus_r = Decimal("1") + monthly_rate
        one_plus_r_power_n = one_plus_r ** tenure_months
        
        # EMI formula
        emi = (Decimal(principal_paisa) * monthly_rate * one_plus_r_power_n) / (one_plus_r_power_n - Decimal("1"))
        
        return int(emi)
    
    @staticmethod
    async def create_loan_application(
        db: AsyncSession,
        loan_in: LoanCreate,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> Loan:
        # Validate principal amount limits
        if loan_in.principal_amount < MIN_LOAN_AMOUNT:
            raise ValueError(f"Loan amount must be at least ₹{MIN_LOAN_AMOUNT:,.2f}")
        
        if loan_in.principal_amount > MAX_LOAN_AMOUNT:
            raise ValueError(f"Loan amount cannot exceed ₹{MAX_LOAN_AMOUNT:,.2f}")
        
        # Validate loan type exists and belongs to tenant
        loan_type = await db.get(LoanType, loan_in.loan_type_id)
        if not loan_type:
            raise ValueError("Loan type not found")
        
        if loan_type.tenant_id != tenant_id:
            raise ValueError("Loan type does not belong to your tenant")
        
        if not loan_type.is_active:
            raise ValueError("Cannot apply for loan with inactive loan type")
        
        # Fetch interest rate from INTEREST_RULES table
        interest_rule_query = select(InterestRule).where(
            and_(
                InterestRule.loan_type_id == loan_in.loan_type_id,
                InterestRule.rule_type == RuleType.LOAN,
                InterestRule.is_active == True
            )
        )
        interest_rule_result = await db.execute(interest_rule_query)
        interest_rule = interest_rule_result.scalar_one_or_none()
        
        if not interest_rule:
            raise ValueError(f"No interest rule configured for loan type '{loan_type.name}'. Please contact admin.")
        
        # Store interest rate as snapshot (preserves contract integrity)
        interest_rate_snapshot = interest_rule.interest_rate
        
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
        
        # Convert principal to paisa
        principal_paisa = int(loan_in.principal_amount * 100)
        
        # Calculate EMI
        emi_paisa = LoanService.calculate_emi(
            principal_paisa=principal_paisa,
            annual_interest_rate=interest_rate_snapshot,
            tenure_months=loan_in.tenure_months
        )
        
        # Create loan application
        new_loan = Loan(
            tenant_id=tenant_id,
            user_id=user_id,
            account_id=loan_in.account_id,
            loan_type_id=loan_in.loan_type_id,
            principal_amount=principal_paisa,
            interest_rate=interest_rate_snapshot,  # Snapshot from interest rule
            tenure_months=loan_in.tenure_months,
            remaining_principal=principal_paisa,  # Initially equal to principal
            emi_amount=emi_paisa,
            loan_purpose=loan_in.loan_purpose,
            status=LoanStatus.APPLIED,
            applied_at=datetime.now(timezone.utc)
        )
        
        db.add(new_loan)
        await db.commit()
        await db.refresh(new_loan)
        
        # Import notification service
        from app.services.notification_service import NotificationService
        from app.models.enums import NotificationType
        
        # Get the user details for notification message
        user = await db.get(User, user_id)
        
        # Send notification to USER confirming application
        await NotificationService.create_notification(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            notification_type=NotificationType.LOAN_APPLIED,
            message=f"Your loan application for ₹{loan_in.principal_amount:,.2f} has been submitted successfully. EMI: ₹{emi_paisa / 100:,.2f}/month for {loan_in.tenure_months} months.",
            reference_id=new_loan.id,
            reference_type="loan",
            send_websocket=True
        )
        
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
        loan = await db.get(Loan, loan_id)
        if not loan:
            raise ValueError("Loan not found")
        
        if loan.tenant_id != tenant_id:
            raise ValueError("Cannot process loan from different tenant")
        
        if loan.status != LoanStatus.APPLIED:
            raise ValueError(f"Cannot process loan with status {loan.status.value}")
        
        # Import required models and enums
        from app.models.transaction import Transaction
        from app.models.enums import TransactionType, TransactionStatus, ReferenceType, NotificationType
        from app.services.notification_service import NotificationService
        
        # Store transaction ID for notifications (if approval)
        loan_transaction_id = None
        account_number = None
        new_balance = None
        
        if decision.decision == "APPROVED":
            # Update loan status
            loan.status = LoanStatus.APPROVED
            loan.decided_by = admin_id
            loan.decided_at = datetime.now(timezone.utc)
            
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
            if not account:
                raise ValueError("Account not found for loan disbursement")
            
            account.balance += loan.principal_amount
            
            # Flush to get transaction ID
            await db.flush()
            loan_transaction_id = loan_transaction.id
            account_number = account.account_number
            new_balance = account.balance
            
        else:  # REJECTED
            # Update loan status
            loan.status = LoanStatus.REJECTED
            loan.decided_by = admin_id
            loan.decided_at = datetime.now(timezone.utc)
            loan.rejection_reason = decision.rejection_reason
        
        # Commit all database changes atomically
        await db.commit()
        await db.refresh(loan)
        
        # Send notifications AFTER successful commit
        if decision.decision == "APPROVED":
            # Send notification to USER about loan approval
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
                message=f"Loan amount of ₹{loan.principal_amount / 100:,.2f} has been credited to your account {account_number}. New balance: ₹{new_balance / 100:,.2f}",
                reference_id=loan_transaction_id,
                reference_type="transaction",
                send_websocket=True
            )
            
        else:  # REJECTED
            # Send notification to USER about loan rejection
            rejection_message = f"Your loan application for ₹{loan.principal_amount / 100:,.2f} has been rejected."
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
        
        return loan
    
    @staticmethod
    async def get_loan_by_id(
        db: AsyncSession,
        loan_id: uuid.UUID
    ) -> Optional[Loan]:
        return await db.get(Loan, loan_id)
    
    @staticmethod
    async def list_user_loans(
        db: AsyncSession,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        include_inactive: bool = False
    ) -> List[Loan]:
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