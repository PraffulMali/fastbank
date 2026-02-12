import uuid
import asyncio
import logging
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.transaction import Transaction
from app.models.account import Account
from app.models.user import User
from app.models.enums import TransactionStatus, TransactionType
from app.models.enums import NotificationType
from app.services.notification_service import NotificationService
from app.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class TransactionBackgroundTasks:
    """
    Background tasks for processing transactions.
    
    Features:
    - Atomic balance updates
    - Status tracking (PENDING → SUCCESS/FAILED)
    - WebSocket notifications
    - Persistent notifications
    - Error handling and rollback
    """
    
    @staticmethod
    async def process_transfer(reference_id: uuid.UUID):
        """
        Background task to process a pending transfer.
        
        Steps:
        1. Fetch both transactions by reference_id
        2. Verify both are PENDING
        3. Atomically update balances
        4. Update both statuses to SUCCESS
        5. Send notifications to both users
        
        In case of error:
        - Update both statuses to FAILED
        - Send failure notifications
        - No balance changes
        """
        async with AsyncSessionLocal() as db:
            try:
                # Simulate processing delay
                await asyncio.sleep(5)

                # ✅ START ATOMIC TRANSACTION
                async with db.begin():

                    # Fetch transactions
                    query = select(Transaction).where(
                        Transaction.reference_id == reference_id
                    )
                    result = await db.execute(query)
                    transactions = list(result.scalars().all())

                    if len(transactions) != 2:
                        logger.error(f"Transfer {reference_id}: Expected 2 transactions")
                        return

                    # Identify transactions
                    debit_txn = next(
                        txn for txn in transactions
                        if txn.transaction_type == TransactionType.DEBIT
                    )

                    credit_txn = next(
                        txn for txn in transactions
                        if txn.transaction_type == TransactionType.CREDIT
                    )

                    # Validate states
                    if (
                        debit_txn.status != TransactionStatus.PENDING
                        or credit_txn.status != TransactionStatus.PENDING
                    ):
                        logger.warning(f"Transfer {reference_id}: Not PENDING")
                        return

                    # ✅ LOCK ACCOUNT ROWS 🔥 CRITICAL FIX
                    debit_account = (
                        await db.execute(
                            select(Account)
                            .where(Account.id == debit_txn.account_id)
                            .with_for_update()
                        )
                    ).scalar_one()

                    credit_account = (
                        await db.execute(
                            select(Account)
                            .where(Account.id == credit_txn.account_id)
                            .with_for_update()
                        )
                    ).scalar_one()

                    if not debit_account or not credit_account:
                        logger.error(f"Transfer {reference_id}: Account not found")

                        debit_txn.status = TransactionStatus.FAILED
                        credit_txn.status = TransactionStatus.FAILED
                        return

                    # Balance check
                    if debit_account.balance < debit_txn.amount:
                        logger.error(f"Transfer {reference_id}: Insufficient balance")

                        debit_txn.status = TransactionStatus.FAILED
                        credit_txn.status = TransactionStatus.FAILED
                        return

                    # ✅ SAFE ATOMIC UPDATE
                    debit_account.balance -= debit_txn.amount
                    credit_account.balance += credit_txn.amount

                    debit_txn.status = TransactionStatus.SUCCESS
                    credit_txn.status = TransactionStatus.SUCCESS

                # ✅ AUTO COMMIT happens here

                logger.info(f"Transfer {reference_id}: SUCCESS")

                # Refresh updated objects
                await db.refresh(debit_txn)
                await db.refresh(credit_txn)
                await db.refresh(debit_account)
                await db.refresh(credit_account)

                # Send notifications (outside transaction)
                await TransactionBackgroundTasks._send_transaction_notifications(
                    db, debit_txn, credit_txn, debit_account, credit_account
                )

            except Exception as e:
                logger.error(f"Transfer {reference_id}: Error - {e}")

                # ✅ No manual rollback needed if error occurs inside db.begin()
                # But safe to call defensively
                await db.rollback()

                # Try marking FAILED (new transaction)
                try:
                    async with db.begin():

                        query = select(Transaction).where(
                            Transaction.reference_id == reference_id
                        )
                        result = await db.execute(query)
                        transactions = list(result.scalars().all())

                        if len(transactions) == 2:
                            debit_txn = next(
                                txn for txn in transactions
                                if txn.transaction_type == TransactionType.DEBIT
                            )

                            credit_txn = next(
                                txn for txn in transactions
                                if txn.transaction_type == TransactionType.CREDIT
                            )

                            debit_txn.status = TransactionStatus.FAILED
                            credit_txn.status = TransactionStatus.FAILED

                except Exception as nested_error:
                    logger.error(f"Transfer {reference_id}: Failed to mark FAILED - {nested_error}")

    
    @staticmethod
    async def _mark_transfer_failed(
        db: AsyncSession,
        debit_txn: Transaction,
        credit_txn: Transaction,
        reason: str
    ):
        """
        Mark both transactions as FAILED and send notifications.
        """
        debit_txn.status = TransactionStatus.FAILED
        credit_txn.status = TransactionStatus.FAILED
        
        await db.commit()
        await db.refresh(debit_txn)
        await db.refresh(credit_txn)
        
        logger.info(f"Transfer {debit_txn.reference_id}: FAILED - {reason}")
        
        # Get accounts to fetch user info
        debit_account = await db.get(Account, debit_txn.account_id)
        
        if debit_account:
            # Send failure notification to sender
            await NotificationService.create_notification(
                db=db,
                tenant_id=debit_txn.tenant_id,
                user_id=debit_account.user_id,
                notification_type=NotificationType.TRANSACTION_FAILED,
                message=f"Transfer of ₹{debit_txn.amount / 100} failed. Reason: {reason}",
                reference_id=debit_txn.id,
                reference_type="transaction"
            )
    
    @staticmethod
    async def _send_transaction_notifications(
        db: AsyncSession,
        debit_txn: Transaction,
        credit_txn: Transaction,
        debit_account: Account,
        credit_account: Account
    ):
        """
        Send success notifications to both sender and receiver.
        Also send admin notification for high-value transactions.
        """
        # Notification to sender (debit)
        try:
            await NotificationService.create_notification(
                db=db,
                tenant_id=debit_txn.tenant_id,
                user_id=debit_account.user_id,
                notification_type=NotificationType.TRANSACTION_SUCCESS,
                message=f"Successfully transferred ₹{debit_txn.amount / 100} to account {credit_account.account_number}. New balance: ₹{debit_account.balance / 100}",
                reference_id=debit_txn.id,
                reference_type="transaction"
            )
        except Exception as e:
            logger.error(f"Failed to send success notification to sender {debit_account.user_id}: {e}")
        
        # Notification to receiver (credit)
        try:
            await NotificationService.create_notification(
                db=db,
                tenant_id=credit_txn.tenant_id,
                user_id=credit_account.user_id,
                notification_type=NotificationType.TRANSACTION_SUCCESS,
                message=f"Received ₹{credit_txn.amount / 100} from account {debit_account.account_number}. New balance: ₹{credit_account.balance / 100}",
                reference_id=credit_txn.id,
                reference_type="transaction"
            )
        except Exception as e:
            logger.error(f"Failed to send success notification to receiver {credit_account.user_id}: {e}")
        
        # High-value transaction alert to admins (e.g., > 100,000 Rupees = 10,000,000 Paise)
        if debit_txn.amount > 100000 * 100:
            try:
                # Get all admin users in both tenants
                admin_query = select(User).where(
                    and_(
                        User.role.in_(["ADMIN"]),
                        User.tenant_id.in_([debit_txn.tenant_id, credit_txn.tenant_id]),
                        User.is_active == True
                    )
                )
                result = await db.execute(admin_query)
                admins = list(result.scalars().all())
                
                for admin in admins:
                    try:
                        await NotificationService.create_notification(
                            db=db,
                            tenant_id=admin.tenant_id,
                            user_id=admin.id,
                            notification_type=NotificationType.HIGH_VALUE_TRANSACTION,
                            message=f"High-value transfer of ₹{debit_txn.amount / 100} from {debit_account.account_number} to {credit_account.account_number}",
                            reference_id=debit_txn.id,
                            reference_type="transaction"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send high-value notification to admin {admin.id}: {e}")
            except Exception as e:
                logger.error(f"Failed to process high-value notifications: {e}")