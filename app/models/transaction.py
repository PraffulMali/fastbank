from typing import TYPE_CHECKING
import uuid
from decimal import Decimal
from sqlalchemy import (
    String,
    Numeric,
    BigInteger,
    ForeignKey,
    CheckConstraint,
    Index,
    Enum as SQLEnum,

)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel
from app.models.enums import TransactionType, TransactionStatus, ReferenceType

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.account import Account


class Transaction(BaseModel):
    __tablename__ = "transactions"
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True
    )
    
    transaction_type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType, name="transaction_type_enum", create_constraint=True),
        nullable=False,
        index=True
    )
    
    reference_type: Mapped[ReferenceType] = mapped_column(
        SQLEnum(ReferenceType, name="reference_type_enum", create_constraint=True),
        nullable=False,
        index=True
    )
    
    amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )
    
    status: Mapped[TransactionStatus] = mapped_column(
        SQLEnum(TransactionStatus, name="transaction_status_enum", create_constraint=True),
        nullable=False,
        default=TransactionStatus.PENDING,
        index=True
    )
    
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="transactions",
        lazy="selectin"
    )
    
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="transactions",
        lazy="selectin"
    )
    
    __table_args__ = (
        CheckConstraint("amount > 0", name="check_amount_positive"),
    )
    
    @property
    def account_number(self) -> str:
        return self.account.account_number if self.account else None

    
    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, type={self.transaction_type}, amount={self.amount})>"