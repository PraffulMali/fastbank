import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.tenant import Tenant
from app.models.user import User
from app.models.account import Account
from app.models.loan import Loan
from app.models.transaction import Transaction
from app.models.notification import Notification
from app.models.user_identity import UserIdentity
from app.models.loan_repayment import LoanRepayment
from app.models.account_type import AccountType
from app.models.loan_type import LoanType
from app.models.interest_rule import InterestRule

logger = logging.getLogger(__name__)


class CascadeDeleteService:
    @staticmethod
    async def cascade_soft_delete_tenant(
        db: AsyncSession, tenant_id: uuid.UUID
    ) -> dict:
        tenant = await db.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError("Tenant not found")

        if not tenant.is_active:
            logger.info(
                f"Tenant {tenant_id} already deleted, continuing with cascade delete of children"
            )

        stats = {
            "tenant_id": str(tenant_id),
            "users": 0,
            "user_identities": 0,
            "accounts": 0,
            "loans": 0,
            "loan_repayments": 0,
            "transactions": 0,
            "notifications": 0,
            "account_types": 0,
            "loan_types": 0,
            "interest_rules": 0,
        }

        now = datetime.now(timezone.utc)

        logger.info(f"Cascade Delete Started - Entity=Tenant | TenantID={tenant_id}")

        loan_repayments_query = select(LoanRepayment).where(
            and_(
                LoanRepayment.tenant_id == tenant_id,
                LoanRepayment.is_active == True,
            )
        )
        loan_repayments_result = await db.execute(loan_repayments_query)
        loan_repayments = loan_repayments_result.scalars().all()

        for loan_repayment in loan_repayments:
            loan_repayment.is_active = False
            loan_repayment.deleted_at = now
            stats["loan_repayments"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=LoanRepayments | Count={stats['loan_repayments']}"
        )

        transactions_query = select(Transaction).where(
            and_(Transaction.tenant_id == tenant_id, Transaction.is_active == True)
        )
        transactions_result = await db.execute(transactions_query)
        transactions = transactions_result.scalars().all()

        for transaction in transactions:
            transaction.is_active = False
            transaction.deleted_at = now
            stats["transactions"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=Transactions | Count={stats['transactions']}"
        )

        loans_query = select(Loan).where(
            and_(Loan.tenant_id == tenant_id, Loan.is_active == True)
        )
        loans_result = await db.execute(loans_query)
        loans = loans_result.scalars().all()

        for loan in loans:
            loan.is_active = False
            loan.deleted_at = now
            stats["loans"] += 1

        logger.info(f"Cascade Delete Progress - Entity=Loans | Count={stats['loans']}")

        accounts_query = select(Account).where(
            and_(Account.tenant_id == tenant_id, Account.is_active == True)
        )
        accounts_result = await db.execute(accounts_query)
        accounts = accounts_result.scalars().all()

        for account in accounts:
            account.is_active = False
            account.deleted_at = now
            stats["accounts"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=Accounts | Count={stats['accounts']}"
        )

        notifications_query = select(Notification).where(
            and_(Notification.tenant_id == tenant_id, Notification.is_active == True)
        )
        notifications_result = await db.execute(notifications_query)
        notifications = notifications_result.scalars().all()

        for notification in notifications:
            notification.is_active = False
            notification.deleted_at = now
            stats["notifications"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=Notifications | Count={stats['notifications']}"
        )

        user_identities_query = select(UserIdentity).where(
            and_(UserIdentity.tenant_id == tenant_id, UserIdentity.is_active == True)
        )
        user_identities_result = await db.execute(user_identities_query)
        user_identities = user_identities_result.scalars().all()

        for user_identity in user_identities:
            user_identity.is_active = False
            user_identity.deleted_at = now
            stats["user_identities"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=UserIdentities | Count={stats['user_identities']}"
        )

        users_query = select(User).where(
            and_(User.tenant_id == tenant_id, User.is_active == True)
        )
        users_result = await db.execute(users_query)
        users = users_result.scalars().all()

        for user in users:
            user.is_active = False
            user.deleted_at = now
            stats["users"] += 1

        logger.info(f"Cascade Delete Progress - Entity=Users | Count={stats['users']}")

        interest_rules_query = select(InterestRule).where(
            and_(InterestRule.tenant_id == tenant_id, InterestRule.is_active == True)
        )
        interest_rules_result = await db.execute(interest_rules_query)
        interest_rules = interest_rules_result.scalars().all()

        for interest_rule in interest_rules:
            interest_rule.is_active = False
            interest_rule.deleted_at = now
            stats["interest_rules"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=InterestRules | Count={stats['interest_rules']}"
        )

        account_types_query = select(AccountType).where(
            and_(AccountType.tenant_id == tenant_id, AccountType.is_active == True)
        )
        account_types_result = await db.execute(account_types_query)
        account_types = account_types_result.scalars().all()

        for account_type in account_types:
            account_type.is_active = False
            account_type.deleted_at = now
            stats["account_types"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=AccountTypes | Count={stats['account_types']}"
        )

        loan_types_query = select(LoanType).where(
            and_(LoanType.tenant_id == tenant_id, LoanType.is_active == True)
        )
        loan_types_result = await db.execute(loan_types_query)
        loan_types = loan_types_result.scalars().all()

        for loan_type in loan_types:
            loan_type.is_active = False
            loan_type.deleted_at = now
            stats["loan_types"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=LoanTypes | Count={stats['loan_types']}"
        )

        tenant.is_active = False
        tenant.deleted_at = now

        logger.info(f"Cascade Delete Completed - Entity=Tenant | TenantID={tenant_id}")

        return stats

    @staticmethod
    async def cascade_soft_delete_user(db: AsyncSession, user_id: uuid.UUID) -> dict:
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        if not user.is_active:
            logger.info(
                f"User {user_id} already deleted, continuing with cascade delete of children"
            )

        stats = {
            "user_id": str(user_id),
            "user_identity": 0,
            "accounts": 0,
            "loans": 0,
            "loan_repayments": 0,
            "transactions": 0,
            "notifications": 0,
        }

        now = datetime.now(timezone.utc)

        logger.info(f"Cascade Delete Started - Entity=User | UserID={user_id}")

        loans_query = select(Loan).where(
            and_(Loan.user_id == user_id, Loan.is_active == True)
        )
        loans_result = await db.execute(loans_query)
        loans = loans_result.scalars().all()
        loan_ids = [loan.id for loan in loans]

        if loan_ids:
            loan_repayments_query = select(LoanRepayment).where(
                and_(
                    LoanRepayment.loan_id.in_(loan_ids),
                    LoanRepayment.is_active == True,
                )
            )
            loan_repayments_result = await db.execute(loan_repayments_query)
            loan_repayments = loan_repayments_result.scalars().all()

            for loan_repayment in loan_repayments:
                loan_repayment.is_active = False
                loan_repayment.deleted_at = now
                stats["loan_repayments"] += 1

            logger.info(
                f"Cascade Delete Progress - Entity=LoanRepayments | Count={stats['loan_repayments']}"
            )

        for loan in loans:
            loan.is_active = False
            loan.deleted_at = now
            stats["loans"] += 1

        logger.info(f"Cascade Delete Progress - Entity=Loans | Count={stats['loans']}")

        accounts_query = select(Account).where(
            and_(Account.user_id == user_id, Account.is_active == True)
        )
        accounts_result = await db.execute(accounts_query)
        accounts = accounts_result.scalars().all()
        account_ids = [account.id for account in accounts]

        if account_ids:
            transactions_query = select(Transaction).where(
                and_(
                    Transaction.account_id.in_(account_ids),
                    Transaction.is_active == True,
                )
            )
            transactions_result = await db.execute(transactions_query)
            transactions = transactions_result.scalars().all()

            for transaction in transactions:
                transaction.is_active = False
                transaction.deleted_at = now
                stats["transactions"] += 1

            logger.info(
                f"Cascade Delete Progress - Entity=Transactions | Count={stats['transactions']}"
            )

        for account in accounts:
            account.is_active = False
            account.deleted_at = now
            stats["accounts"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=Accounts | Count={stats['accounts']}"
        )

        notifications_query = select(Notification).where(
            and_(Notification.user_id == user_id, Notification.is_active == True)
        )
        notifications_result = await db.execute(notifications_query)
        notifications = notifications_result.scalars().all()

        for notification in notifications:
            notification.is_active = False
            notification.deleted_at = now
            stats["notifications"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=Notifications | Count={stats['notifications']}"
        )

        user_identity_query = select(UserIdentity).where(
            and_(UserIdentity.user_id == user_id, UserIdentity.is_active == True)
        )
        user_identity_result = await db.execute(user_identity_query)
        user_identity = user_identity_result.scalar_one_or_none()

        if user_identity:
            user_identity.is_active = False
            user_identity.deleted_at = now
            stats["user_identity"] += 1

        logger.info(
            f"Cascade Delete Progress - Entity=UserIdentity | Count={stats['user_identity']}"
        )

        user.is_active = False
        user.deleted_at = now

        logger.info(f"Cascade Delete Completed - Entity=User | UserID={user_id}")

        return stats
