from typing import TYPE_CHECKING
import uuid
from decimal import Decimal
from sqlalchemy import (
    String,
    Numeric,
    ForeignKey,
    CheckConstraint,
    Index,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel
from app.models.enums import AccountType

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.transaction import Transaction 

class Account(BaseModel):
    __tablename__ = "accounts"
    
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
    
    account_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        index=True
    )
    
    account_type: Mapped[AccountType] = mapped_column(
        SQLEnum(AccountType, name="account_type_enum", create_constraint=True),
        nullable=False,
        default=AccountType.SAVINGS,
        index=True
    )
    
    balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        default=Decimal("0.00")
    )
    
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR"
    )
    
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="accounts",
        lazy="selectin"
    )
    
    user: Mapped["User"] = relationship(
        "User",
        back_populates="accounts",
        lazy="selectin"
    )
    
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    __table_args__ = (
        CheckConstraint("balance >= 0", name="check_balance_non_negative"),
        Index("ix_accounts_tenant_user_type", "tenant_id", "user_id", "account_type", unique=True),
    )
    
    def __repr__(self) -> str:
        return f"<Account(id={self.id}, type={self.account_type})>"