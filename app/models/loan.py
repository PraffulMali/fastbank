from typing import TYPE_CHECKING
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    String,
    Numeric,
    Integer,
    BigInteger,
    ForeignKey,
    CheckConstraint,
    Index,
    Enum as SQLEnum,
    DateTime,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.models.base import BaseModel
from app.models.enums import LoanStatus

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.account import Account


class Loan(BaseModel):
    __tablename__ = "loans"
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    
    principal_amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )
    
    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False
    )
    
    tenure_months: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    
    status: Mapped[LoanStatus] = mapped_column(
        SQLEnum(LoanStatus, name="loan_status_enum", create_constraint=True),
        nullable=False,
        default=LoanStatus.APPLIED,
        index=True
    )
    
    loan_purpose: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Reason for loan application"
    )
    
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="loans",
        lazy="selectin"
    )
    
    user: Mapped["User"] = relationship(
        "User",
        back_populates="loans",
        foreign_keys=[user_id],
        lazy="selectin"
    )
    
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="loans",
        lazy="selectin"
    )
    
    approver: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[approved_by],
        lazy="selectin"
    )
    
    __table_args__ = (
        CheckConstraint("principal_amount > 0", name="check_principal_positive"),
        CheckConstraint("interest_rate >= 0 AND interest_rate <= 100", name="check_interest_valid"),
        CheckConstraint("tenure_months > 0", name="check_tenure_positive")
    )
    
    def __repr__(self) -> str:
        return f"<Loan(id={self.id}, user_id={self.user_id}, status={self.status})>"