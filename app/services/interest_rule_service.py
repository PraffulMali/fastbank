from typing import Optional
import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from datetime import datetime, timezone

from app.models.interest_rule import InterestRule
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.notification import Notification
from app.models.account_type import AccountType
from app.models.loan_type import LoanType
from app.models.enums import (
    RuleType,
    TransactionType,
    ReferenceType,
    TransactionStatus,
    NotificationType,
)
from app.schemas.interest_rule import InterestRuleCreate, InterestRuleUpdate
from app.utils.pagination import Paginator, Page


class InterestRuleService:

    @staticmethod
    async def create_interest_rule(
        db: AsyncSession, rule_in: InterestRuleCreate, tenant_id: uuid.UUID
    ) -> InterestRule:
        if rule_in.rule_type == "ACCOUNT":
            account_type = await db.get(AccountType, rule_in.account_type_id)
            if not account_type:
                raise ValueError("Account type not found")
            if account_type.tenant_id != tenant_id:
                raise ValueError("Account type does not belong to your tenant")
            if not account_type.is_active:
                raise ValueError("Cannot create rule for inactive account type")

            min_a = int(rule_in.min_balance * 100)
            max_a = int(rule_in.max_balance * 100) if rule_in.max_balance is not None else None

            conditions = [
                InterestRule.account_type_id == rule_in.account_type_id,
                InterestRule.is_active == True,
            ]
            if max_a is not None:
                conditions.append(InterestRule.min_balance <= max_a)
            conditions.append(
                or_(
                    InterestRule.max_balance.is_(None),
                    InterestRule.max_balance >= min_a
                )
            )

            overlap_query = select(InterestRule).where(and_(*conditions))
            result = await db.execute(overlap_query)
            if result.scalars().first():
                raise ValueError(
                    "Balance range overlaps with existing interest rule for this account type"
                )

        elif rule_in.rule_type == "LOAN":
            loan_type = await db.get(LoanType, rule_in.loan_type_id)
            if not loan_type:
                raise ValueError("Loan type not found")
            if loan_type.tenant_id != tenant_id:
                raise ValueError("Loan type does not belong to your tenant")
            if not loan_type.is_active:
                raise ValueError("Cannot create rule for inactive loan type")

            existing_query = select(InterestRule).where(
                and_(
                    InterestRule.loan_type_id == rule_in.loan_type_id,
                    InterestRule.is_active == True,
                )
            )
            result = await db.execute(existing_query)
            if result.scalars().first():
                raise ValueError(
                    "Interest rule already exists for this loan type. Update existing rule instead."
                )

        min_balance_paise = (
            int(rule_in.min_balance * 100) if rule_in.min_balance is not None else None
        )
        max_balance_paise = (
            int(rule_in.max_balance * 100) if rule_in.max_balance is not None else None
        )

        new_rule = InterestRule(
            tenant_id=tenant_id,
            rule_type=RuleType(rule_in.rule_type),
            account_type_id=rule_in.account_type_id,
            loan_type_id=rule_in.loan_type_id,
            min_balance=min_balance_paise,
            max_balance=max_balance_paise,
            interest_rate=rule_in.interest_rate,
            is_active=True,
        )

        db.add(new_rule)
        await db.commit()
        await db.refresh(new_rule)

        return new_rule

    @staticmethod
    async def get_interest_rule_by_id(
        db: AsyncSession, rule_id: uuid.UUID
    ) -> Optional[InterestRule]:
        return await db.get(InterestRule, rule_id)

    @staticmethod
    async def list_interest_rules(
        db: AsyncSession, tenant_id: uuid.UUID, paginator: Paginator
    ) -> Page:
        query = select(InterestRule).where(InterestRule.tenant_id == tenant_id)

        query = query.order_by(InterestRule.created_at.desc())

        return await paginator.paginate(db, query)

    @staticmethod
    async def update_interest_rule(
        db: AsyncSession,
        rule_id: uuid.UUID,
        rule_update: InterestRuleUpdate,
        tenant_id: uuid.UUID,
    ) -> Optional[InterestRule]:
        rule = await db.get(InterestRule, rule_id)
        if not rule:
            return None

        if rule.tenant_id != tenant_id:
            raise PermissionError("Cannot update interest rule from different tenant")

        update_data = rule_update.model_dump(exclude_unset=True)

        if rule.rule_type == RuleType.LOAN:
            if "min_balance" in update_data or "max_balance" in update_data:
                raise ValueError("Cannot update balance limits for LOAN rules")

        if "interest_rate" in update_data:
            rule.interest_rate = update_data["interest_rate"]
        
        if rule.rule_type == RuleType.ACCOUNT:
            if "min_balance" in update_data:
                 val = update_data["min_balance"]
                 rule.min_balance = int(val * 100) if val is not None else None
            
            if "max_balance" in update_data:
                val = update_data["max_balance"]
                rule.max_balance = int(val * 100) if val is not None else None

            min_val = rule.min_balance if rule.min_balance is not None else 0
            if rule.max_balance is not None:
                if rule.max_balance <= min_val:
                     raise ValueError("max_balance must be greater than min_balance")

            
            conditions = [
                InterestRule.id != rule.id,
                InterestRule.account_type_id == rule.account_type_id,
                InterestRule.is_active == True,
            ]
            
            if rule.max_balance is not None:
                conditions.append(InterestRule.min_balance <= rule.max_balance)
            
            conditions.append(
                or_(
                    InterestRule.max_balance.is_(None),
                    InterestRule.max_balance >= min_val
                )
            )
            
            overlap_query = select(InterestRule).where(and_(*conditions))
            result = await db.execute(overlap_query)
            if result.scalars().first():
                raise ValueError(
                    "Updated balance range overlaps with another existing interest rule"
                )

        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def delete_interest_rule(
        db: AsyncSession, rule_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> None:
        rule = await db.get(InterestRule, rule_id)
        if not rule:
            raise ValueError("Interest rule not found")

        if rule.tenant_id != tenant_id:
            raise PermissionError("Cannot delete interest rule from different tenant")

        await db.delete(rule)
        await db.commit()

    @staticmethod
    async def get_interest_rule_detail(
        db: AsyncSession, rule_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Optional[InterestRule]:
        rule = await db.get(InterestRule, rule_id)
        if not rule or rule.tenant_id != tenant_id:
            return None

        return rule

    @staticmethod
    async def process_monthly_interest_accrual(db: AsyncSession) -> dict:
        stats = {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "total_interest": Decimal(0),
            "failures": []
        }

        rules_query = select(InterestRule).where(
            and_(
                InterestRule.rule_type == RuleType.ACCOUNT,
                InterestRule.is_active == True,
            )
        )
        result = await db.execute(rules_query)
        rules = result.scalars().all()

        processed_account_ids = set()

        for rule in rules:
            stmt = select(Account).where(
                and_(
                    Account.tenant_id == rule.tenant_id,
                    Account.account_type_id == rule.account_type_id,
                    Account.is_active == True,
                    Account.balance > 0,
                )
            )

            if rule.min_balance is not None:
                stmt = stmt.where(Account.balance >= rule.min_balance)
            if rule.max_balance is not None:
                stmt = stmt.where(Account.balance <= rule.max_balance)

            acc_result = await db.execute(stmt)
            accounts = acc_result.scalars().all()

            for account in accounts:
                if account.id in processed_account_ids:
                    continue

                processed_account_ids.add(account.id)
                stats["processed"] += 1
                try:
                    async with db.begin_nested():

                        rate = rule.interest_rate

                        interest_amount_decimal = (
                            Decimal(account.balance) * (rate / Decimal(100))
                        ) / Decimal(12)
                        interest_amount_paise = int(interest_amount_decimal)

                        if interest_amount_paise > 0:
                            txn_id = uuid.uuid4()
                            acc_txn_ref = uuid.uuid4()
                            transaction = Transaction(
                                id=txn_id,
                                tenant_id=account.tenant_id,
                                account_id=account.id,
                                reference_id=acc_txn_ref,
                                transaction_type=TransactionType.CREDIT,
                                reference_type=ReferenceType.SYSTEM,
                                amount=interest_amount_paise,
                                status=TransactionStatus.SUCCESS,
                                created_at=datetime.now(timezone.utc),
                                updated_at=datetime.now(timezone.utc),
                            )
                            db.add(transaction)

                            account.balance += interest_amount_paise

                            interest_in_rupees = Decimal(interest_amount_paise) / 100
                            notification = Notification(
                                tenant_id=account.tenant_id,
                                user_id=account.user_id,
                                notification_type=NotificationType.TRANSACTION_SUCCESS,
                                message=f"Interest credited: ₹{interest_in_rupees:.2f}",
                                reference_id=txn_id,
                                reference_type="transaction",
                                is_read=False,
                                created_at=datetime.now(timezone.utc),
                                updated_at=datetime.now(timezone.utc),
                                is_active=True,
                            )
                            db.add(notification)

                            stats["success"] += 1
                            stats["total_interest"] += interest_amount_decimal

                except Exception as e:
                    stats["failed"] += 1

                    stats["failures"].append({
                        "account_id": account.id,
                        "tenant_id": account.tenant_id,
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

                    continue

        return stats
