import uuid
import asyncio
import logging
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

    @staticmethod
    async def process_transfer(reference_id: uuid.UUID):
        async with AsyncSessionLocal() as db:
            try:
                async with db.begin():

                    query = select(Transaction).where(
                        Transaction.reference_id == reference_id
                    )
                    result = await db.execute(query)
                    transactions = list(result.scalars().all())

                    if len(transactions) != 2:
                        logger.error(
                            f"Transfer Error - Reason=InvalidTransactionCount | "
                            f"ReferenceID={reference_id}"
                        )
                        return

                    debit_txn = next(
                        txn
                        for txn in transactions
                        if txn.transaction_type == TransactionType.DEBIT
                    )

                    credit_txn = next(
                        txn
                        for txn in transactions
                        if txn.transaction_type == TransactionType.CREDIT
                    )

                    if (
                        debit_txn.status != TransactionStatus.PENDING
                        or credit_txn.status != TransactionStatus.PENDING
                    ):
                        logger.warning(
                            f"Transfer Skipped - Status=Not_Pending | ReferenceID={reference_id}"
                        )
                        return

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
                        logger.error(
                            f"Transfer Error - Reason=AccountNotFound | ReferenceID={reference_id}"
                        )

                        debit_txn.status = TransactionStatus.FAILED
                        credit_txn.status = TransactionStatus.FAILED
                        return

                    if debit_account.balance < debit_txn.amount:
                        logger.error(
                            f"Transfer Error - Reason=InsufficientBalance | ReferenceID={reference_id}"
                        )

                        debit_txn.status = TransactionStatus.FAILED
                        credit_txn.status = TransactionStatus.FAILED
                        return

                    debit_account.balance -= debit_txn.amount
                    credit_account.balance += credit_txn.amount

                    debit_txn.status = TransactionStatus.SUCCESS
                    credit_txn.status = TransactionStatus.SUCCESS

                logger.info(
                    f"Transfer Success - Status=Completed | ReferenceID={reference_id}"
                )

                await db.refresh(debit_txn)
                await db.refresh(credit_txn)
                await db.refresh(debit_account)
                await db.refresh(credit_account)

                await TransactionBackgroundTasks._send_transaction_notifications(
                    db, debit_txn, credit_txn, debit_account, credit_account
                )

            except Exception as e:
                logger.error(
                    f"Transfer Error - ReferenceID={reference_id} | Error={str(e)}"
                )

                await db.rollback()

                try:
                    async with db.begin():

                        query = select(Transaction).where(
                            Transaction.reference_id == reference_id
                        )
                        result = await db.execute(query)
                        transactions = list(result.scalars().all())

                        if len(transactions) == 2:
                            debit_txn = next(
                                txn
                                for txn in transactions
                                if txn.transaction_type == TransactionType.DEBIT
                            )

                            credit_txn = next(
                                txn
                                for txn in transactions
                                if txn.transaction_type == TransactionType.CREDIT
                            )

                            debit_txn.status = TransactionStatus.FAILED
                            credit_txn.status = TransactionStatus.FAILED

                except Exception as nested_error:
                    logger.error(
                        f"Transfer Status Update Failed - Status=Fallback_Error | "
                        f"ReferenceID={reference_id} | "
                        f"Error={str(nested_error)}"
                    )

    @staticmethod
    async def _mark_transfer_failed(
        db: AsyncSession, debit_txn: Transaction, credit_txn: Transaction, reason: str
    ):
        debit_txn.status = TransactionStatus.FAILED
        credit_txn.status = TransactionStatus.FAILED

        await db.commit()
        await db.refresh(debit_txn)
        await db.refresh(credit_txn)

        logger.info(
            f"Transfer Failed - Status=Marked_Failed | ReferenceID={debit_txn.reference_id} | Reason={reason}"
        )

        debit_account = await db.get(Account, debit_txn.account_id)

        if debit_account:
            await NotificationService.create_notification(
                db=db,
                tenant_id=debit_txn.tenant_id,
                user_id=debit_account.user_id,
                notification_type=NotificationType.TRANSACTION_FAILED,
                message=f"Transfer of ₹{debit_txn.amount / 100} failed. Reason: {reason}",
                reference_id=debit_txn.id,
                reference_type="transaction",
            )

    @staticmethod
    async def _send_transaction_notifications(
        db: AsyncSession,
        debit_txn: Transaction,
        credit_txn: Transaction,
        debit_account: Account,
        credit_account: Account,
    ):
        try:
            await NotificationService.create_notification(
                db=db,
                tenant_id=debit_txn.tenant_id,
                user_id=debit_account.user_id,
                notification_type=NotificationType.TRANSACTION_SUCCESS,
                message=f"Successfully transferred ₹{debit_txn.amount / 100} to account {credit_account.account_number}. New balance: ₹{debit_account.balance / 100}",
                reference_id=debit_txn.id,
                reference_type="transaction",
            )
        except Exception as e:
            logger.error(
                f"Notification Error - Type=Success_Sender | "
                f"UserID={debit_account.user_id} | "
                f"Error={str(e)}"
            )

        try:
            await NotificationService.create_notification(
                db=db,
                tenant_id=credit_txn.tenant_id,
                user_id=credit_account.user_id,
                notification_type=NotificationType.TRANSACTION_SUCCESS,
                message=f"Received ₹{credit_txn.amount / 100} from account {debit_account.account_number}. New balance: ₹{credit_account.balance / 100}",
                reference_id=credit_txn.id,
                reference_type="transaction",
            )
        except Exception as e:
            logger.error(
                f"Notification Error - Type=Success_Receiver | "
                f"UserID={credit_account.user_id} | "
                f"Error={str(e)}"
            )

        if debit_txn.amount > 100000 * 100:
            try:
                admin_query = select(User).where(
                    and_(
                        User.role.in_(["ADMIN"]),
                        User.tenant_id.in_([debit_txn.tenant_id, credit_txn.tenant_id]),
                        User.is_active == True,
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
                            reference_type="transaction",
                        )
                    except Exception as e:
                        logger.error(
                            f"Notification Error - Type=HighValue_Admin | "
                            f"AdminID={admin.id} | "
                            f"Error={str(e)}"
                        )
            except Exception as e:
                logger.error(
                    f"Notification Batch Error - Type=HighValue | Error={str(e)}"
                )
