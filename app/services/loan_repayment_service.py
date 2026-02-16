from typing import Optional, Tuple
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

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
    UserRole,
)
from app.services.notification_service import NotificationService
from app.services.email_service import EmailService
import logging

logger = logging.getLogger(__name__)


class LoanRepaymentService:

    @staticmethod
    def calculate_emi_split(
        emi_amount: int,
        remaining_principal: int,
        annual_interest_rate: Decimal,
        tenure_months: int,
    ) -> Tuple[int, int]:
        monthly_rate = annual_interest_rate / Decimal("12") / Decimal("100")
        interest_component = int(Decimal(remaining_principal) * monthly_rate)

        principal_component = emi_amount - interest_component

        if principal_component > remaining_principal:
            principal_component = remaining_principal
            interest_component = emi_amount - principal_component

        return (principal_component, interest_component)

    @staticmethod
    async def process_emi_deduction(db: AsyncSession, loan: Loan) -> Tuple[bool, str]:
        account = await db.get(Account, loan.account_id)
        if not account:
            return (False, f"Account not found for loan {loan.id}")

        user = await db.get(User, loan.user_id)
        if not user:
            return (False, f"User not found for loan {loan.id}")

        if account.balance < loan.emi_amount:
            shortfall = loan.emi_amount - account.balance
            logger.warning(
                f"Insufficient funds for EMI deduction. "
                f"Loan: {loan.id}, User: {user.email}, "
                f"Required: {loan.emi_amount / 100}, Available: {account.balance / 100}"
            )
            return (
                False,
                f"Insufficient funds. Required: ₹{loan.emi_amount / 100:,.2f}, Available: ₹{account.balance / 100:,.2f}",
            )

        principal_component, interest_component = (
            LoanRepaymentService.calculate_emi_split(
                emi_amount=loan.emi_amount,
                remaining_principal=loan.remaining_principal,
                annual_interest_rate=loan.interest_rate,
                tenure_months=loan.tenure_months,
            )
        )

        emi_transaction = Transaction(
            tenant_id=loan.tenant_id,
            account_id=loan.account_id,
            reference_id=loan.id,
            transaction_type=TransactionType.DEBIT,
            reference_type=ReferenceType.LOAN,
            amount=loan.emi_amount,
            status=TransactionStatus.SUCCESS,
        )

        db.add(emi_transaction)

        account.balance -= loan.emi_amount

        loan.remaining_principal -= principal_component

        if loan.remaining_principal < 0:
            loan.remaining_principal = 0

        await db.flush()

        repayment = LoanRepayment(
            tenant_id=loan.tenant_id,
            loan_id=loan.id,
            transaction_id=emi_transaction.id,
            amount_paid=loan.emi_amount,
            principal_component=principal_component,
            interest_component=interest_component,
            payment_date=datetime.now(timezone.utc),
            status=TransactionStatus.SUCCESS,
        )

        db.add(repayment)
        await db.flush()

        logger.info(
            f"EMI deducted successfully. "
            f"Loan: {loan.id}, User: {user.email}, "
            f"Amount: {loan.emi_amount / 100}, "
            f"Principal: {principal_component / 100}, "
            f"Interest: {interest_component / 100}, "
            f"Remaining: {loan.remaining_principal / 100}"
        )

        return (True, f"EMI of ₹{loan.emi_amount / 100:,.2f} deducted successfully")

    @staticmethod
    async def process_monthly_emis(db: AsyncSession) -> dict:
        query = select(Loan).where(
            and_(
                Loan.status == LoanStatus.APPROVED,
                Loan.is_active == True,
                Loan.remaining_principal > 0,
            )
        )

        result = await db.execute(query)
        loans = list(result.scalars().all())

        stats = {
            "total_loans": len(loans),
            "successful": 0,
            "failed": 0,
            "total_amount_collected": 0,
            "errors": [],
        }

        logger.info(f"Processing monthly EMIs for {len(loans)} loans")

        for loan in loans:
            try:
                account = await db.get(Account, loan.account_id)
                if not account:
                    raise Exception(f"Account not found for loan {loan.id}")

                user = await db.get(User, loan.user_id)
                if not user:
                    raise Exception(f"User not found for loan {loan.id}")

                if account.balance < loan.emi_amount:
                    shortfall = loan.emi_amount - account.balance

                    await NotificationService.create_notification(
                        db=db,
                        tenant_id=loan.tenant_id,
                        user_id=loan.user_id,
                        notification_type=NotificationType.SYSTEM_ALERT,
                        message=f"EMI payment of ₹{loan.emi_amount / 100:,.2f} failed due to insufficient funds. Current balance: ₹{account.balance / 100:,.2f}. Shortfall: ₹{shortfall / 100:,.2f}",
                        reference_id=loan.id,
                        reference_type="loan",
                        send_websocket=True,
                    )

                    await EmailService.send_emi_failure_email(
                        to_email=user.email,
                        user_name=user.full_name,
                        loan_amount=loan.principal_amount / 100,
                        emi_amount=loan.emi_amount / 100,
                        account_balance=account.balance / 100,
                        due_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    )

                    admin_query = select(User).where(
                        and_(
                            User.tenant_id == loan.tenant_id,
                            User.role == UserRole.ADMIN,
                            User.is_active == True,
                        )
                    )
                    admin_result = await db.execute(admin_query)
                    admins = list(admin_result.scalars().all())

                    for admin in admins:
                        await NotificationService.create_notification(
                            db=db,
                            tenant_id=loan.tenant_id,
                            user_id=admin.id,
                            notification_type=NotificationType.SYSTEM_ALERT,
                            message=f"EMI payment failed for {user.full_name} - Loan ID: {loan.id}. Amount: ₹{loan.emi_amount / 100:,.2f}. Shortfall: ₹{shortfall / 100:,.2f}",
                            reference_id=loan.id,
                            reference_type="loan",
                            send_websocket=True,
                        )

                    logger.warning(
                        f"Insufficient funds for EMI deduction. "
                        f"Loan: {loan.id}, User: {user.email}, "
                        f"Required: {loan.emi_amount / 100}, Available: {account.balance / 100}"
                    )

                    raise Exception(
                        f"Insufficient funds. Required: ₹{loan.emi_amount / 100:,.2f}, Available: ₹{account.balance / 100:,.2f}"
                    )

                principal_component, interest_component = (
                    LoanRepaymentService.calculate_emi_split(
                        emi_amount=loan.emi_amount,
                        remaining_principal=loan.remaining_principal,
                        annual_interest_rate=loan.interest_rate,
                        tenure_months=loan.tenure_months,
                    )
                )

                transaction_id = None
                emi_amount = loan.emi_amount
                remaining_principal_after = None

                async with db.begin_nested():
                    emi_transaction = Transaction(
                        tenant_id=loan.tenant_id,
                        account_id=loan.account_id,
                        reference_id=loan.id,
                        transaction_type=TransactionType.DEBIT,
                        reference_type=ReferenceType.LOAN,
                        amount=loan.emi_amount,
                        status=TransactionStatus.SUCCESS,
                    )

                    db.add(emi_transaction)

                    account.balance -= loan.emi_amount

                    loan.remaining_principal -= principal_component

                    if loan.remaining_principal < 0:
                        loan.remaining_principal = 0

                    await db.flush()

                    transaction_id = emi_transaction.id
                    remaining_principal_after = loan.remaining_principal

                    repayment = LoanRepayment(
                        tenant_id=loan.tenant_id,
                        loan_id=loan.id,
                        transaction_id=emi_transaction.id,
                        amount_paid=loan.emi_amount,
                        principal_component=principal_component,
                        interest_component=interest_component,
                        payment_date=datetime.now(timezone.utc),
                        status=TransactionStatus.SUCCESS,
                    )

                    db.add(repayment)
                    await db.flush()

                await db.refresh(loan)
                await db.refresh(account)

                await NotificationService.create_notification(
                    db=db,
                    tenant_id=loan.tenant_id,
                    user_id=loan.user_id,
                    notification_type=NotificationType.TRANSACTION_SUCCESS,
                    message=f"EMI payment of ₹{emi_amount / 100:,.2f} deducted successfully. Principal: ₹{principal_component / 100:,.2f}, Interest: ₹{interest_component / 100:,.2f}. Remaining principal: ₹{remaining_principal_after / 100:,.2f}",
                    reference_id=transaction_id,
                    reference_type="transaction",
                    send_websocket=True,
                )

                logger.info(
                    f"EMI deducted successfully. "
                    f"Loan: {loan.id}, User: {user.email}, "
                    f"Amount: {emi_amount / 100}, "
                    f"Principal: {principal_component / 100}, "
                    f"Interest: {interest_component / 100}, "
                    f"Remaining: {remaining_principal_after / 100}"
                )

                stats["successful"] += 1
                stats["total_amount_collected"] += emi_amount

            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append({"loan_id": str(loan.id), "message": str(e)})
                logger.error(f"Failed to process EMI for loan {loan.id}: {str(e)}")

        logger.info(
            f"Monthly EMI processing complete. "
            f"Total: {stats['total_loans']}, "
            f"Successful: {stats['successful']}, "
            f"Failed: {stats['failed']}, "
            f"Amount Collected: ₹{stats['total_amount_collected'] / 100:,.2f}"
        )

        return stats
