from typing import TYPE_CHECKING
import uuid
from decimal import Decimal
from sqlalchemy import ForeignKey, Enum as SQLEnum, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import RuleType

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.account_type import AccountType
    from app.models.loan_type import LoanType


class InterestRule(BaseModel):
    __tablename__ = "interest_rules"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    rule_type: Mapped[RuleType] = mapped_column(
        SQLEnum(RuleType, name="rule_type_enum", create_constraint=True),
        nullable=False,
        index=True
    )

    account_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account_types.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    loan_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loan_types.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    min_balance: Mapped[int | None] = mapped_column(
        Numeric(20, 0),  
        nullable=True
    )

    max_balance: Mapped[int | None] = mapped_column(
        Numeric(20, 0),  
        nullable=True
    )

    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="interest_rules",
        lazy="selectin"
    )

    account_type: Mapped["AccountType | None"] = relationship(
        "AccountType",
        back_populates="interest_rules",
        lazy="selectin"
    )

    loan_type: Mapped["LoanType | None"] = relationship(
        "LoanType",
        back_populates="interest_rules",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<InterestRule(id={self.id}, type={self.rule_type}, rate={self.interest_rate})>"