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
from app.models.enums import RuleType, TransactionType, ReferenceType, TransactionStatus, NotificationType
from app.schemas.interest_rule import InterestRuleCreate, InterestRuleUpdate
from app.utils.pagination import Paginator, Page


class InterestRuleService:
    
    @staticmethod
    async def create_interest_rule(
        db: AsyncSession,
        rule_in: InterestRuleCreate,
        tenant_id: uuid.UUID
    ) -> InterestRule:
        """
        Create a new interest rule.
        Validation already done in schema.
        Additional validation: verify that account_type/loan_type exists and belongs to tenant.
        """
        # Verify account_type or loan_type exists and belongs to tenant
        if rule_in.rule_type == "ACCOUNT":
            account_type = await db.get(AccountType, rule_in.account_type_id)
            if not account_type:
                raise ValueError("Account type not found")
            if account_type.tenant_id != tenant_id:
                raise ValueError("Account type does not belong to your tenant")
            if not account_type.is_active:
                raise ValueError("Cannot create rule for inactive account type")
            
            # Check for overlapping balance ranges
            overlap_query = select(InterestRule).where(
                and_(
                    InterestRule.account_type_id == rule_in.account_type_id,
                    InterestRule.is_active == True,
                    or_(
                        # New rule's min_balance falls within existing range
                        and_(
                            InterestRule.min_balance <= int(rule_in.min_balance * 100),
                            or_(
                                InterestRule.max_balance.is_(None),
                                InterestRule.max_balance >= int(rule_in.min_balance * 100)
                            )
                        ),
                        # New rule's max_balance falls within existing range (if not None)
                        and_(
                            rule_in.max_balance is not None,  # Python check
                            InterestRule.min_balance <= int(rule_in.max_balance * 100),
                            or_(
                                InterestRule.max_balance.is_(None),
                                InterestRule.max_balance >= int(rule_in.max_balance * 100)
                            )
                        ),
                        # New rule completely encompasses existing range
                        and_(
                            InterestRule.min_balance >= int(rule_in.min_balance * 100),
                            rule_in.max_balance is None  # Python check
                        )
                    )
                )
            )
            result = await db.execute(overlap_query)
            if result.scalar_one_or_none():
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
            
            # Check if loan type already has an interest rule
            existing_query = select(InterestRule).where(
                and_(
                    InterestRule.loan_type_id == rule_in.loan_type_id,
                    InterestRule.is_active == True
                )
            )
            result = await db.execute(existing_query)
            if result.scalar_one_or_none():
                raise ValueError(
                    "Interest rule already exists for this loan type. Update existing rule instead."
                )
        
        # Convert rupees to paise for storage
        min_balance_paise = int(rule_in.min_balance * 100) if rule_in.min_balance is not None else None
        max_balance_paise = int(rule_in.max_balance * 100) if rule_in.max_balance is not None else None
        
        # Create interest rule
        new_rule = InterestRule(
            tenant_id=tenant_id,
            rule_type=RuleType(rule_in.rule_type),
            account_type_id=rule_in.account_type_id,
            loan_type_id=rule_in.loan_type_id,
            min_balance=min_balance_paise,
            max_balance=max_balance_paise,
            interest_rate=rule_in.interest_rate,
            is_active=True
        )
        
        db.add(new_rule)
        await db.commit()
        await db.refresh(new_rule)
        
        return new_rule
    
    @staticmethod
    async def get_interest_rule_by_id(
        db: AsyncSession,
        rule_id: uuid.UUID
    ) -> Optional[InterestRule]:
        """Get interest rule by ID"""
        return await db.get(InterestRule, rule_id)
    
    @staticmethod
    async def list_interest_rules(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        paginator: Paginator
    ) -> Page:
        """
        List interest rules without filters.
        """
        query = select(InterestRule).where(InterestRule.tenant_id == tenant_id)
        
        query = query.order_by(InterestRule.created_at.desc())
        
        return await paginator.paginate(db, query)
    
    @staticmethod
    async def update_interest_rule(
        db: AsyncSession,
        rule_id: uuid.UUID,
        rule_update: InterestRuleUpdate,
        tenant_id: uuid.UUID
    ) -> Optional[InterestRule]:
        """
        Update interest rule - only interest_rate can be updated.
        """
        rule = await db.get(InterestRule, rule_id)
        if not rule:
            return None
        
        # Verify ownership
        if rule.tenant_id != tenant_id:
            raise PermissionError("Cannot update interest rule from different tenant")
        
        # Update interest rate
        rule.interest_rate = rule_update.interest_rate
        
        await db.commit()
        await db.refresh(rule)
        return rule
    
    @staticmethod
    async def delete_interest_rule(
        db: AsyncSession,
        rule_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> None:
        """
        Hard delete an interest rule.
        No protection needed since rules are configuration, not transactional data.
        """
        rule = await db.get(InterestRule, rule_id)
        if not rule:
            raise ValueError("Interest rule not found")
        
        # Verify ownership
        if rule.tenant_id != tenant_id:
            raise PermissionError("Cannot delete interest rule from different tenant")
        
        # Delete rule
        await db.delete(rule)
        await db.commit()
    
    @staticmethod
    async def get_interest_rule_detail(
        db: AsyncSession,
        rule_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> Optional[dict]:
        """
        Get interest rule with related account type or loan type name.
        """
        rule = await db.get(InterestRule, rule_id)
        if not rule or rule.tenant_id != tenant_id:
            return None
        
        account_type_name = None
        loan_type_name = None
        
        if rule.account_type_id:
            account_type = await db.get(AccountType, rule.account_type_id)
            account_type_name = account_type.name if account_type else None
        
        if rule.loan_type_id:
            loan_type = await db.get(LoanType, rule.loan_type_id)
            loan_type_name = loan_type.name if loan_type else None
        
        return {
            "id": rule.id,
            "tenant_id": rule.tenant_id,
            "rule_type": rule.rule_type.value,
            "account_type_id": rule.account_type_id,
            "account_type_name": account_type_name,
            "loan_type_id": rule.loan_type_id,
            "loan_type_name": loan_type_name,
            "min_balance": float(rule.min_balance) / 100 if rule.min_balance else None,
            "max_balance": float(rule.max_balance) / 100 if rule.max_balance else None,
            "interest_rate": float(rule.interest_rate),
            "is_active": rule.is_active,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at
        }
    
    @staticmethod
    async def process_monthly_interest_accrual(db: AsyncSession) -> dict:
        """
        Process monthly interest accrual for all accounts with active interest rules.
        """
        stats = {
            "processed": 0, 
            "success": 0, 
            "failed": 0, 
            "total_interest": Decimal(0)
        }
        
        # 1. Get all active ACCOUNT rules
        rules_query = select(InterestRule).where(
            and_(
                InterestRule.rule_type == RuleType.ACCOUNT,
                InterestRule.is_active == True
            )
        )
        result = await db.execute(rules_query)
        rules = result.scalars().all()
        
        for rule in rules:
            # 2. Find eligible accounts for this rule
            stmt = select(Account).where(
                and_(
                    Account.tenant_id == rule.tenant_id,
                    Account.account_type_id == rule.account_type_id,
                    Account.is_active == True,
                    Account.balance > 0
                )
            )
            
            if rule.min_balance is not None:
                stmt = stmt.where(Account.balance >= rule.min_balance)
            if rule.max_balance is not None:
                stmt = stmt.where(Account.balance <= rule.max_balance)
                
            acc_result = await db.execute(stmt)
            accounts = acc_result.scalars().all()
            
            for account in accounts:
                stats["processed"] += 1
                try:
                    # Atomic transaction per account using savepoint
                    async with db.begin_nested():
                        # Calculate interest (Annual rate -> Monthly)
                        # interest_rate is percentage (e.g. 5.00 for 5%)
                        # Formula: balance * (rate/100) / 12
                        
                        rate = rule.interest_rate  # Decimal
                        # balance is in paise (int)
                        # Result should be int (paise)
                        
                        interest_amount_decimal = (Decimal(account.balance) * (rate / Decimal(100))) / Decimal(12)
                        interest_amount_paise = int(interest_amount_decimal)
                        
                        if interest_amount_paise > 0:
                            # Create system transaction
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
                                updated_at=datetime.now(timezone.utc)
                            )
                            db.add(transaction)
                            
                            # Update account balance
                            account.balance += interest_amount_paise
                            
                            # Create notification (part of transaction)
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
                                is_active=True
                            )
                            db.add(notification)
                            
                            stats["success"] += 1
                            stats["total_interest"] += interest_amount_decimal
                            
                except Exception as e:
                    stats["failed"] += 1
                    # Log error but continue processing other accounts
                    # db.begin_nested() automatically rolls back on exception
                    continue
                    
        return stats