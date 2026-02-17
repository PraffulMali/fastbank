from typing import Tuple, Optional
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import BackgroundTasks
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
    NotificationType,
)
from app.services.notification_service import NotificationService
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class AdvanceLoanRepaymentService:

    @staticmethod
    def calculate_accrued_interest(
        remaining_principal: int, annual_interest_rate: Decimal
    ) -> int:
        """
        Calculate accrued interest for one month.

        Formula: Interest = Principal × (Annual Rate / 12 / 100)

        Args:
            remaining_principal: Remaining principal in paisa
            annual_interest_rate: Annual interest rate

        Returns:
            Interest amount in paisa
        """
        monthly_rate = annual_interest_rate / Decimal("12") / Decimal("100")
        interest = int(Decimal(remaining_principal) * monthly_rate)
        return interest

    @staticmethod
    def allocate_payment(
        payment_amount: int, remaining_principal: int, annual_interest_rate: Decimal
    ) -> Tuple[int, int, int]:
        interest_component = AdvanceLoanRepaymentService.calculate_accrued_interest(
            remaining_principal, annual_interest_rate
        )

        if payment_amount <= interest_component:
            return (payment_amount, 0, remaining_principal)

        principal_component = payment_amount - interest_component

        if principal_component > remaining_principal:
            principal_component = remaining_principal
            interest_component = payment_amount - principal_component

        remaining_after = remaining_principal - principal_component

        return (interest_component, principal_component, remaining_after)

    @staticmethod
    def recalculate_tenure(
        remaining_principal: int, emi_amount: int, annual_interest_rate: Decimal
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

        min_emi = remaining_principal * monthly_rate
        if emi_amount <= min_emi:
            logger.warning(
                f"Tenure Recalculation Warning - Reason=EMIBelowInterest | "
                f"EMIAmount={emi_amount} | "
                f"MinRequiredEMI={min_emi}"
            )
            return None

        try:
            numerator = math.log(1 - (remaining_principal * monthly_rate / emi_amount))
            denominator = math.log(1 + monthly_rate)
            new_tenure = -numerator / denominator

            return math.ceil(new_tenure)
        except (ValueError, ZeroDivisionError) as e:
            logger.error(f"Tenure Calculation Error - Error={str(e)}")
            return None

    @staticmethod
    async def process_advance_repayment(
        db: AsyncSession,
        loan_id: uuid.UUID,
        payment_amount_rupees: Decimal,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        background_tasks: BackgroundTasks,
    ) -> Tuple[bool, str, Optional[dict]]:
        try:
            loan = await db.get(Loan, loan_id)
            if not loan:
                return (False, "Loan not found", None)

            if loan.tenant_id != tenant_id or loan.user_id != user_id:
                return (False, "Unauthorized access to loan", None)

            if loan.status != LoanStatus.APPROVED:
                return (
                    False,
                    f"Loan is not in APPROVED status (current: {loan.status.value})",
                    None,
                )

            if loan.remaining_principal <= 0:
                return (False, "Loan already fully repaid", None)

            payment_amount_paisa = int(payment_amount_rupees * 100)

            if payment_amount_paisa <= 0:
                return (False, "Payment amount must be greater than zero", None)

            account = await db.get(Account, loan.account_id)
            if not account:
                return (False, "Account not found", None)

            if account.balance < payment_amount_paisa:
                shortfall = payment_amount_paisa - account.balance

                await NotificationService.create_notification(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    notification_type=NotificationType.TRANSACTION_FAILED,
                    message=f"Advance loan repayment of ₹{payment_amount_rupees:,.2f} failed due to insufficient funds. Current balance: ₹{account.balance / 100:,.2f}. Shortfall: ₹{shortfall / 100:,.2f}",
                    reference_id=loan_id,
                    reference_type="loan",
                    send_websocket=True,
                )

                user = await db.get(User, user_id)
                if user:
                    background_tasks.add_task(
                        EmailService.send_advance_repayment_failure_email,
                        to_email=user.email,
                        user_name=user.full_name,
                        payment_amount=float(payment_amount_rupees),
                        account_balance=float(account.balance) / 100,
                    )

                return (
                    False,
                    f"Insufficient funds. Required: ₹{payment_amount_rupees:,.2f}, Available: ₹{account.balance / 100:,.2f}",
                    None,
                )

            interest_component, principal_component, remaining_after = (
                AdvanceLoanRepaymentService.allocate_payment(
                    payment_amount=payment_amount_paisa,
                    remaining_principal=loan.remaining_principal,
                    annual_interest_rate=loan.interest_rate,
                )
            )

            is_foreclosure = remaining_after == 0
            new_status = (
                LoanStatus.FORECLOSED if is_foreclosure else LoanStatus.APPROVED
            )
            new_tenure = 0 if is_foreclosure else loan.tenure_months

            if not is_foreclosure:
                calculated_tenure = AdvanceLoanRepaymentService.recalculate_tenure(
                    remaining_principal=remaining_after,
                    emi_amount=loan.emi_amount,
                    annual_interest_rate=loan.interest_rate,
                )

                if calculated_tenure is not None:
                    new_tenure = calculated_tenure
                else:
                    logger.warning(
                        f"Tenure Recalculation Skipped - Status=Failed | LoanID={loan_id}"
                    )
                    new_tenure = loan.tenure_months

            transaction_id = None
            old_remaining = loan.remaining_principal

            async with db.begin_nested():
                repayment_transaction = Transaction(
                    tenant_id=tenant_id,
                    account_id=loan.account_id,
                    reference_id=loan_id,
                    transaction_type=TransactionType.DEBIT,
                    reference_type=ReferenceType.LOAN,
                    amount=payment_amount_paisa,
                    status=TransactionStatus.SUCCESS,
                )

                db.add(repayment_transaction)

                account.balance -= payment_amount_paisa

                loan.remaining_principal = remaining_after
                loan.tenure_months = new_tenure
                loan.status = new_status

                await db.flush()
                transaction_id = repayment_transaction.id

                repayment = LoanRepayment(
                    tenant_id=tenant_id,
                    loan_id=loan_id,
                    transaction_id=transaction_id,
                    amount_paid=payment_amount_paisa,
                    principal_component=principal_component,
                    interest_component=interest_component,
                    payment_date=datetime.now(timezone.utc),
                    status=TransactionStatus.SUCCESS,
                )

                db.add(repayment)
                await db.flush()

            await db.commit()

            await db.refresh(loan)
            await db.refresh(account)

            if is_foreclosure:
                message = f"Congratulations! Your loan has been fully repaid. Payment of ₹{payment_amount_rupees:,.2f} (Principal: ₹{principal_component / 100:,.2f}, Interest: ₹{interest_component / 100:,.2f}) has been processed. Your loan is now FORECLOSED."
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
                send_websocket=True,
            )

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
                "transaction_id": str(transaction_id),
            }

            logger.info(
                f"Advance Repayment Processed - Status=Success | "
                f"LoanID={loan_id} | "
                f"Amount={payment_amount_rupees} | "
                f"PrincipalComponent={principal_component / 100} | "
                f"InterestComponent={interest_component / 100} | "
                f"Foreclosure={is_foreclosure}"
            )

            return (True, "Advance repayment processed successfully", details)

        except Exception as e:
            logger.error(f"Advance Repayment Error - LoanID={loan_id} | Error={str(e)}")
            await db.rollback()
            return (False, f"Error: {str(e)}", None)
