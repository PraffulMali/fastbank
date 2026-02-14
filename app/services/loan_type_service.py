from typing import Optional
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.loan_type import LoanType
from app.models.loan import Loan
from app.models.interest_rule import InterestRule
from app.schemas.loan_type import LoanTypeCreate, LoanTypeUpdate
from app.utils.pagination import Paginator, Page


class LoanTypeService:
    
    @staticmethod
    async def create_loan_type(
        db: AsyncSession,
        loan_type_in: LoanTypeCreate,
        tenant_id: uuid.UUID
    ) -> LoanType:
        """
        Create a new loan type for a tenant.
        Validates that name is unique within the tenant.
        """
        # Check for duplicate name within tenant
        existing_query = select(LoanType).where(
            and_(
                LoanType.tenant_id == tenant_id,
                LoanType.name == loan_type_in.name,
                LoanType.is_active == True
            )
        )
        result = await db.execute(existing_query)
        if result.scalar_one_or_none():
            raise ValueError(f"Loan type '{loan_type_in.name}' already exists in this tenant")
        
        # Create loan type
        new_loan_type = LoanType(
            tenant_id=tenant_id,
            name=loan_type_in.name,
            is_active=True
        )
        
        db.add(new_loan_type)
        await db.commit()
        await db.refresh(new_loan_type)
        
        return new_loan_type
    
    @staticmethod
    async def get_loan_type_by_id(
        db: AsyncSession,
        loan_type_id: uuid.UUID
    ) -> Optional[LoanType]:
        """Get loan type by ID"""
        return await db.get(LoanType, loan_type_id)
    
    @staticmethod
    async def list_loan_types(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        paginator: Paginator,
        include_inactive: bool = False
    ) -> Page:
        """
        List all loan types for a tenant.
        By default, only active types are shown.
        """
        query = select(LoanType).where(LoanType.tenant_id == tenant_id)
        
        if not include_inactive:
            query = query.where(LoanType.is_active == True)
        
        query = query.order_by(LoanType.created_at.desc())
        
        return await paginator.paginate(db, query)
    
    @staticmethod
    async def update_loan_type(
        db: AsyncSession,
        loan_type_id: uuid.UUID,
        loan_type_update: LoanTypeUpdate,
        tenant_id: uuid.UUID
    ) -> Optional[LoanType]:
        """
        Update loan type.
        Validates tenant ownership.
        """
        loan_type = await db.get(LoanType, loan_type_id)
        if not loan_type:
            return None
        
        # Verify ownership
        if loan_type.tenant_id != tenant_id:
            raise PermissionError("Cannot update loan type from different tenant")
        
        # Update name if provided
        if loan_type_update.name is not None:
            # Check for duplicate name
            duplicate_query = select(LoanType).where(
                and_(
                    LoanType.tenant_id == tenant_id,
                    LoanType.name == loan_type_update.name,
                    LoanType.id != loan_type_id,
                    LoanType.is_active == True
                )
            )
            result = await db.execute(duplicate_query)
            if result.scalar_one_or_none():
                raise ValueError(f"Loan type '{loan_type_update.name}' already exists")
            
            loan_type.name = loan_type_update.name
        
        # Update is_active if provided
        if loan_type_update.is_active is not None:
            loan_type.is_active = loan_type_update.is_active
            if loan_type_update.is_active:
                loan_type.deleted_at = None
            else:
                loan_type.deleted_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(loan_type)
        return loan_type
    
    @staticmethod
    async def delete_loan_type(
        db: AsyncSession,
        loan_type_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> None:
        """
        Hard delete a loan type with protection.
        Checks if:
        1. Any loans reference this loan type
        2. Any interest rules reference this loan type
        Raises ValueError if either exist.
        """
        loan_type = await db.get(LoanType, loan_type_id)
        if not loan_type:
            raise ValueError("Loan type not found")
        
        # Verify ownership
        if loan_type.tenant_id != tenant_id:
            raise PermissionError("Cannot delete loan type from different tenant")
        
        # Check if any loans use this loan type
        loans_query = select(func.count()).select_from(Loan).where(
            Loan.loan_type_id == loan_type_id
        )
        result = await db.execute(loans_query)
        loans_count = result.scalar_one()
        
        if loans_count > 0:
            raise ValueError(
                f"Cannot delete loan type: {loans_count} loan(s) are using it. "
                "Set loan type to inactive instead."
            )
        
        # Check if any interest rules use this loan type
        rules_query = select(func.count()).select_from(InterestRule).where(
            InterestRule.loan_type_id == loan_type_id
        )
        result = await db.execute(rules_query)
        rules_count = result.scalar_one()
        
        if rules_count > 0:
            raise ValueError(
                f"Cannot delete loan type: {rules_count} interest rule(s) are using it. "
                "Delete the interest rules first or set loan type to inactive."
            )
        
        # Safe to delete
        await db.delete(loan_type)
        await db.commit()
    
    @staticmethod
    async def get_loan_type_with_rate(
        db: AsyncSession,
        loan_type_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> Optional[dict]:
        """
        Get loan type with its interest rate.
        Returns dict with loan type info and interest rate from interest_rules.
        """
        loan_type = await db.get(LoanType, loan_type_id)
        if not loan_type or loan_type.tenant_id != tenant_id:
            return None
        
        # Get interest rate for this loan type
        rate_query = select(InterestRule).where(
            and_(
                InterestRule.loan_type_id == loan_type_id,
                InterestRule.is_active == True
            )
        ).limit(1)
        
        result = await db.execute(rate_query)
        interest_rule = result.scalar_one_or_none()
        
        return {
            "id": loan_type.id,
            "tenant_id": loan_type.tenant_id,
            "name": loan_type.name,
            "is_active": loan_type.is_active,
            "created_at": loan_type.created_at,
            "interest_rate": float(interest_rule.interest_rate) if interest_rule else None
        }