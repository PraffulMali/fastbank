"""
Advance Loan Repayment Service
Handles borrower-initiated advance loan repayments with interest calculation,
principal allocation, tenure recalculation, and foreclosure logic.
"""
from typing import Tuple, Optional
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging
import math

from app.models.loan import Loan
from app.models.loan_repayment import LoanRepayment
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.models.enums import (
    LoanStatus,
    TransactionType,
    TransactionStatus,
    ReferenceType,
    NotificationType
)
from app.services.notification_service import NotificationService
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class AdvanceLoanRepaymentService:
    
    @staticmethod
    def calculate_accrued_interest(
        remaining_principal: int,
        annual_interest_rate: Decimal
    ) -> int:
        """
        Calculate accrued interest for one month.
        
        Formula: Interest = Principal × (Annual Rate / 12 / 100)
        
        Args:
            remaining_principal: Remaining principal in paisa
            annual_interest_rate: Annual interest rate (e.g., 12.00 for 12%)
            
        Returns:
            Interest amount in paisa
        """
        monthly_rate = annual_interest_rate / Decimal("12") / Decimal("100")
        interest = int(Decimal(remaining_principal) * monthly_rate)
        return interest
    
    @staticmethod
    def allocate_payment(
        payment_amount: int,
        remaining_principal: int,
        annual_interest_rate: Decimal
    ) -> Tuple[int, int, int]:
        """
        Allocate payment amount to interest first, then principal.
        
        Args:
            payment_amount: Total payment amount in paisa
            remaining_principal: Current remaining principal in paisa
            annual_interest_rate: Annual interest rate
            
        Returns:
            Tuple of (interest_component, principal_component, remaining_after_payment)
        """
        # Calculate accrued interest
        interest_component = AdvanceLoanRepaymentService.calculate_accrued_interest(
            remaining_principal, annual_interest_rate
        )
        
        # Allocate to interest first
        if payment_amount <= interest_component:
            # Payment only covers interest (or less)
            return (payment_amount, 0, remaining_principal)
        
        # Payment covers interest and some/all principal
        principal_component = payment_amount - interest_component
        
        # Ensure we don't pay more principal than what's remaining
        if principal_component > remaining_principal:
            principal_component = remaining_principal
            # Recalculate interest component (in case of overpayment)
            interest_component = payment_amount - principal_component
        
        remaining_after = remaining_principal - principal_component
        
        return (interest_component, principal_component, remaining_after)
    
    @staticmethod
    def recalculate_tenure(
        remaining_principal: int,
        emi_amount: int,
        annual_interest_rate: Decimal
    ) -> Optional[int]:
        """
        Recalculate remaining tenure after advance payment using amortization formula.
        
        Formula: n = -log(1 - (P × r / EMI)) / log(1 + r)
        Where:
        - n = number of months
        - P = remaining principal
        - r = monthly interest rate
        - EMI = monthly payment
        
        Args:
            remaining_principal: Remaining principal in paisa
            emi_amount: Monthly EMI in paisa
            annual_interest_rate: Annual interest rate
            
        Returns:
            New tenure in months, or None if loan should be foreclosed
        """
        if remaining_principal <= 0:
            return 0
        
        monthly_rate = float(annual_interest_rate) / 12 / 100
        
        # Check if EMI > P × r (required for formula to work)
        min_emi = remaining_principal * monthly_rate
        if emi_amount <= min_emi:
            logger.warning(
                f"EMI ({emi_amount}) is not greater than P × r ({min_emi}). "
                f"Cannot recalculate tenure. Loan should be restructured."
            )
            return None
        
        # Calculate new tenure
        try:
            numerator = math.log(1 - (remaining_principal * monthly_rate / emi_amount))
            denominator = math.log(1 + monthly_rate)
            new_tenure = -numerator / denominator
            
            # Round up to nearest month
            return math.ceil(new_tenure)
        except (ValueError, ZeroDivisionError) as e:
            logger.error(f"Error calculating tenure: {str(e)}")
            return None
    
    @staticmethod
    async def process_advance_repayment(
        db: AsyncSession,
        loan_id: uuid.UUID,
        payment_amount_rupees: Decimal,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Process an advance loan repayment.
        
        Flow:
        1. Validate loan eligibility (APPROVED status, remaining principal > 0)
        2. Convert payment amount to paisa
        3. Check account balance
        4. Calculate accrued interest
        5. Allocate payment: interest first, then principal
        6. Determine if foreclosure (full payoff)
        7. If not foreclosure, recalculate tenure
        8. Atomically:
           - Create DEBIT transaction
           - Update account balance
           - Update loan (remaining_principal, tenure, status)
           - Create repayment record
        9. Send notifications
        
        Args:
            db: Database session
            loan_id: Loan ID
            payment_amount_rupees: Payment amount in rupees
            user_id: User making the payment
            tenant_id: Tenant ID
            
        Returns:
            Tuple of (success: bool, message: str, details: Optional[dict])
        """
        try:
            # 1. Fetch and validate loan
            loan = await db.get(Loan, loan_id)
            if not loan:
                return (False, "Loan not found", None)
            
            if loan.tenant_id != tenant_id or loan.user_id != user_id:
                return (False, "Unauthorized access to loan", None)
            
            if loan.status != LoanStatus.APPROVED:
                return (False, f"Loan is not in APPROVED status (current: {loan.status.value})", None)
            
            if loan.remaining_principal <= 0:
                return (False, "Loan already fully repaid", None)
            
            # 2. Convert payment to paisa
            payment_amount_paisa = int(payment_amount_rupees * 100)
            
            if payment_amount_paisa <= 0:
                return (False, "Payment amount must be greater than zero", None)
            
            # 3. Get account and check balance
            account = await db.get(Account, loan.account_id)
            if not account:
                return (False, "Account not found", None)
            
            if account.balance < payment_amount_paisa:
                shortfall = payment_amount_paisa - account.balance
                
                # Send failure notification
                await NotificationService.create_notification(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    notification_type=NotificationType.TRANSACTION_FAILED,
                    message=f"Advance loan repayment of ₹{payment_amount_rupees:,.2f} failed due to insufficient funds. Current balance: ₹{account.balance / 100:,.2f}. Shortfall: ₹{shortfall / 100:,.2f}",
                    reference_id=loan_id,
                    reference_type="loan",
                    send_websocket=True
                )
                
                # Send failure email
                user = await db.get(User, user_id)
                if user:
                    await EmailService.send_email(
                        to_email=user.email,
                        subject="Advance Loan Repayment Failed - Insufficient Funds",
                        body=f"""Dear {user.full_name},

Your advance loan repayment of ₹{payment_amount_rupees:,.2f} could not be processed due to insufficient funds.

Current balance: ₹{account.balance / 100:,.2f}
Required amount: ₹{payment_amount_rupees:,.2f}
Shortfall: ₹{shortfall / 100:,.2f}

Please ensure sufficient funds are available and try again.

Best regards,
FastBank Team"""
                    )
                
                return (False, f"Insufficient funds. Required: ₹{payment_amount_rupees:,.2f}, Available: ₹{account.balance / 100:,.2f}", None)
            
            # 4 & 5. Calculate interest and allocate payment
            interest_component, principal_component, remaining_after = AdvanceLoanRepaymentService.allocate_payment(
                payment_amount=payment_amount_paisa,
                remaining_principal=loan.remaining_principal,
                annual_interest_rate=loan.interest_rate
            )
            
            # 6. Determine if foreclosure
            is_foreclosure = (remaining_after == 0)
            new_status = LoanStatus.FORECLOSED if is_foreclosure else LoanStatus.APPROVED
            new_tenure = 0 if is_foreclosure else loan.tenure_months
            
            # 7. Recalculate tenure if not foreclosure
            if not is_foreclosure:
                calculated_tenure = AdvanceLoanRepaymentService.recalculate_tenure(
                    remaining_principal=remaining_after,
                    emi_amount=loan.emi_amount,
                    annual_interest_rate=loan.interest_rate
                )
                
                if calculated_tenure is not None:
                    new_tenure = calculated_tenure
                else:
                    # Cannot recalculate tenure - might need loan restructuring
                    logger.warning(f"Cannot recalculate tenure for loan {loan_id}. Keeping original tenure.")
                    new_tenure = loan.tenure_months
            
            # Store values for notifications
            transaction_id = None
            old_remaining = loan.remaining_principal
            
            # 8. ATOMIC TRANSACTION BLOCK
            async with db.begin_nested():
                # Create DEBIT transaction
                repayment_transaction = Transaction(
                    tenant_id=tenant_id,
                    account_id=loan.account_id,
                    reference_id=loan_id,
                    transaction_type=TransactionType.DEBIT,
                    reference_type=ReferenceType.LOAN,
                    amount=payment_amount_paisa,
                    status=TransactionStatus.SUCCESS
                )
                
                db.add(repayment_transaction)
                
                # Update account balance
                account.balance -= payment_amount_paisa
                
                # Update loan
                loan.remaining_principal = remaining_after
                loan.tenure_months = new_tenure
                loan.status = new_status
                
                # Flush to get transaction ID
                await db.flush()
                transaction_id = repayment_transaction.id
                
                # Create repayment record
                repayment = LoanRepayment(
                    tenant_id=tenant_id,
                    loan_id=loan_id,
                    transaction_id=transaction_id,
                    amount_paid=payment_amount_paisa,
                    principal_component=principal_component,
                    interest_component=interest_component,
                    payment_date=datetime.now(timezone.utc),
                    status=TransactionStatus.SUCCESS
                )
                
                db.add(repayment)
                await db.flush()
            
            # Commit outer transaction
            await db.commit()
            
            # Refresh objects
            await db.refresh(loan)
            await db.refresh(account)
            
            # 9. Send success notification
            if is_foreclosure:
                message = f"🎉 Congratulations! Your loan has been fully repaid. Payment of ₹{payment_amount_rupees:,.2f} (Principal: ₹{principal_component / 100:,.2f}, Interest: ₹{interest_component / 100:,.2f}) has been processed. Your loan is now FORECLOSED."
            else:
                message = f"Advance repayment of ₹{payment_amount_rupees:,.2f} processed successfully. Principal: ₹{principal_component / 100:,.2f}, Interest: ₹{interest_component / 100:,.2f}. Remaining principal: ₹{remaining_after / 100:,.2f}. New tenure: {new_tenure} months."
            
            await NotificationService.create_notification(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                notification_type=NotificationType.TRANSACTION_SUCCESS,
                message=message,
                reference_id=transaction_id,
                reference_type="transaction",
                send_websocket=True
            )
            
            # Prepare details for response
            details = {
                "payment_amount": payment_amount_rupees,
                "interest_component": interest_component / 100,
                "principal_component": principal_component / 100,
                "old_remaining_principal": old_remaining / 100,
                "new_remaining_principal": remaining_after / 100,
                "old_tenure": loan.tenure_months if not is_foreclosure else None,
                "new_tenure": new_tenure,
                "is_foreclosure": is_foreclosure,
                "loan_status": new_status.value,
                "transaction_id": str(transaction_id)
            }
            
            logger.info(
                f"Advance repayment processed. Loan: {loan_id}, "
                f"Amount: ₹{payment_amount_rupees}, "
                f"Principal: ₹{principal_component / 100}, "
                f"Interest: ₹{interest_component / 100}, "
                f"Foreclosure: {is_foreclosure}"
            )
            
            return (True, "Advance repayment processed successfully", details)
            
        except Exception as e:
            logger.error(f"Error processing advance repayment for loan {loan_id}: {str(e)}")
            await db.rollback()
            return (False, f"Error: {str(e)}", None)
