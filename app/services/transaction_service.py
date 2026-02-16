from typing import Optional, Tuple
import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
import asyncio

from app.models.transaction import Transaction
from app.models.account import Account
from app.models.user import User
from app.models.enums import (
    TransactionType,
    TransactionStatus,
    ReferenceType,
    UserRole,
    NotificationType,
)
from app.schemas.transaction import (
    TransferRequest,
    DepositRequest,
    TransactionDetailResponse,
    CounterpartyInfo,
)
from app.utils.pagination import Paginator, Page
from app.tasks.background_tasks import TransactionBackgroundTasks
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class TransactionService:

    @staticmethod
    async def initiate_transfer(
        db: AsyncSession, transfer_request: TransferRequest, current_user: User
    ) -> Tuple[Transaction, Transaction, uuid.UUID]:
        source_query = select(Account).where(
            and_(
                Account.account_number == transfer_request.source_account_number,
                Account.is_active == True,
            )
        )
        source_result = await db.execute(source_query)
        source_account = source_result.scalar_one_or_none()

        if not source_account:
            raise ValueError("Source account not found or inactive")

        if source_account.user_id != current_user.id:
            raise PermissionError("You can only transfer from your own accounts")

        amount_in_paise = int(transfer_request.amount * 100)

        if source_account.balance < amount_in_paise:
            balance_in_rupees = source_account.balance / 100
            raise ValueError(f"Insufficient balance. Available: ₹{balance_in_rupees}")

        dest_query = select(Account).where(
            and_(
                Account.account_number == transfer_request.destination_account_number,
                Account.is_active == True,
            )
        )
        dest_result = await db.execute(dest_query)
        dest_account = dest_result.scalar_one_or_none()

        if not dest_account:
            raise ValueError("Destination account not found or inactive")

        if source_account.id == dest_account.id:
            raise ValueError("Cannot transfer to the same account")

        reference_id = uuid.uuid4()

        debit_transaction = Transaction(
            tenant_id=source_account.tenant_id,
            account_id=source_account.id,
            account=source_account,
            reference_id=reference_id,
            transaction_type=TransactionType.DEBIT,
            reference_type=ReferenceType.TRANSFER,
            amount=amount_in_paise,
            status=TransactionStatus.PENDING,
        )

        credit_transaction = Transaction(
            tenant_id=dest_account.tenant_id,
            account_id=dest_account.id,
            account=dest_account,
            reference_id=reference_id,
            transaction_type=TransactionType.CREDIT,
            reference_type=ReferenceType.TRANSFER,
            amount=amount_in_paise,
            status=TransactionStatus.PENDING,
        )

        db.add(debit_transaction)
        db.add(credit_transaction)

        await db.commit()
        await db.refresh(debit_transaction)
        await db.refresh(credit_transaction)

        asyncio.create_task(TransactionBackgroundTasks.process_transfer(reference_id))

        return debit_transaction, credit_transaction, reference_id

    @staticmethod
    async def deposit(
        db: AsyncSession, deposit_request: DepositRequest, current_user: User
    ) -> Transaction:
        account_query = select(Account).where(
            and_(Account.id == deposit_request.account_id, Account.is_active == True)
        )
        account_result = await db.execute(account_query)
        account = account_result.scalar_one_or_none()

        if not account:
            raise ValueError("Account not found or inactive")

        if account.user_id != current_user.id:
            raise PermissionError("You can only deposit into your own accounts")

        amount_in_paise = int(deposit_request.amount * 100)

        reference_id = uuid.uuid4()

        transaction = Transaction(
            tenant_id=account.tenant_id,
            account_id=account.id,
            account=account,
            reference_id=reference_id,
            transaction_type=TransactionType.CREDIT,
            reference_type=ReferenceType.CASH,
            amount=amount_in_paise,
            status=TransactionStatus.SUCCESS,
        )

        account.balance += amount_in_paise

        db.add(transaction)
        await db.commit()
        await db.refresh(transaction)

        try:
            await NotificationService.create_notification(
                db=db,
                tenant_id=transaction.tenant_id,
                user_id=account.user_id,
                notification_type=NotificationType.TRANSACTION_SUCCESS,
                message=f"Successfully deposited ₹{deposit_request.amount} into account {account.account_number}. New balance: ₹{account.balance / 100}",
                reference_id=transaction.id,
                reference_type="transaction",
            )
        except Exception as e:
            logger.error(f"Failed to send notification for deposit: {e}")

        return transaction

    @staticmethod
    async def get_transaction_by_id(
        db: AsyncSession, transaction_id: uuid.UUID
    ) -> Optional[Transaction]:
        return await db.get(Transaction, transaction_id)

    @staticmethod
    async def get_transaction_detail_with_counterparty(
        db: AsyncSession, transaction_id: uuid.UUID
    ) -> Optional[TransactionDetailResponse]:
        transaction = await db.get(Transaction, transaction_id)
        if not transaction:
            return None

        account = await db.get(Account, transaction.account_id)
        if not account:
            return None

        counterparty = None

        if transaction.reference_type == ReferenceType.TRANSFER:
            opposite_type = (
                TransactionType.CREDIT
                if transaction.transaction_type == TransactionType.DEBIT
                else TransactionType.DEBIT
            )

            counterparty_query = select(Transaction).where(
                and_(
                    Transaction.reference_id == transaction.reference_id,
                    Transaction.transaction_type == opposite_type,
                )
            )
            counterparty_result = await db.execute(counterparty_query)
            counterparty_txn = counterparty_result.scalar_one_or_none()

            if counterparty_txn:
                counterparty_account = await db.get(
                    Account, counterparty_txn.account_id
                )
                if counterparty_account:
                    counterparty_user = await db.get(User, counterparty_account.user_id)
                    if counterparty_user:
                        counterparty = CounterpartyInfo(
                            tenant_id=counterparty_account.tenant_id,
                            account_number=counterparty_account.account_number,
                            user_name=counterparty_user.full_name,
                        )

        return TransactionDetailResponse(
            id=transaction.id,
            tenant_id=transaction.tenant_id,
            account_id=transaction.account_id,
            account_number=account.account_number,
            reference_id=transaction.reference_id,
            transaction_type=transaction.transaction_type.value,
            reference_type=transaction.reference_type.value,
            amount=transaction.amount,
            status=transaction.status.value,
            created_at=transaction.created_at,
            updated_at=transaction.updated_at,
            counterparty=counterparty,
        )

    @staticmethod
    def get_user_transactions_query(user: User):
        account_ids_subquery = select(Account.id).where(
            and_(Account.user_id == user.id, Account.is_active == True)
        )

        return (
            select(Transaction)
            .where(Transaction.account_id.in_(account_ids_subquery))
            .order_by(Transaction.created_at.desc())
        )

    @staticmethod
    def get_tenant_transactions_query(tenant_id: uuid.UUID):
        return (
            select(Transaction)
            .where(Transaction.tenant_id == tenant_id)
            .order_by(Transaction.created_at.desc())
        )

    @staticmethod
    async def list_transactions(
        db: AsyncSession, current_user: User, paginator: Paginator
    ) -> Page:
        if current_user.role == UserRole.USER:
            query = TransactionService.get_user_transactions_query(current_user)
        elif current_user.role == UserRole.ADMIN:
            query = TransactionService.get_tenant_transactions_query(
                current_user.tenant_id
            )
        else:
            raise PermissionError("Invalid role for transaction access")

        page_result = await paginator.paginate(db, query)

        enriched_items = []
        for txn in page_result.items:
            account = await db.get(Account, txn.account_id)
            if account:
                enriched_items.append(
                    {
                        "id": txn.id,
                        "account_id": txn.account_id,
                        "account_number": account.account_number,
                        "transaction_type": txn.transaction_type.value,
                        "reference_type": txn.reference_type.value,
                        "amount": txn.amount,
                        "status": txn.status.value,
                        "created_at": txn.created_at,
                        "updated_at": txn.updated_at,
                    }
                )

        return Page(
            total=page_result.total,
            page=page_result.page,
            page_size=page_result.page_size,
            total_pages=page_result.total_pages,
            has_next=page_result.has_next,
            has_previous=page_result.has_previous,
            items=enriched_items,
        )

    @staticmethod
    async def verify_transaction_access(
        db: AsyncSession, transaction_id: uuid.UUID, current_user: User
    ) -> Transaction:
        transaction = await db.get(Transaction, transaction_id)
        if not transaction:
            raise ValueError("Transaction not found")

        if current_user.role == UserRole.USER:
            account = await db.get(Account, transaction.account_id)
            if not account or account.user_id != current_user.id:
                raise PermissionError("You can only view your own transactions")

        elif current_user.role == UserRole.ADMIN:
            if transaction.tenant_id != current_user.tenant_id:
                raise PermissionError("You can only view transactions in your tenant")

        else:
            raise PermissionError("Invalid role for transaction access")

        return transaction
