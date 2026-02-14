from typing import TYPE_CHECKING
import uuid
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    ForeignKey,
    DateTime,
    CheckConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel
from app.models.enums import TransactionStatus  

if TYPE_CHECKING:
    from app.models.loan import Loan
    from app.models.transaction import Transaction
    from app.models.tenant import Tenant


class LoanRepayment(BaseModel):
    __tablename__ = "loan_repayments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loans.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    amount_paid: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    principal_component: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    interest_component: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    payment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )

    status: Mapped[TransactionStatus] = mapped_column(
        SQLEnum(TransactionStatus, name="repayment_status_enum", create_constraint=True),
        nullable=False,
        default=TransactionStatus.SUCCESS,
        index=True
    )


    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        lazy="selectin"
    )

    loan: Mapped["Loan"] = relationship(
        "Loan",
        lazy="selectin"
    )

    transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        lazy="selectin"
    )


    __table_args__ = (
        CheckConstraint("amount_paid > 0", name="check_amount_paid_positive"),
        CheckConstraint("principal_component >= 0", name="check_principal_component_valid"),
        CheckConstraint("interest_component >= 0", name="check_interest_component_valid"),
        CheckConstraint(
            "principal_component + interest_component = amount_paid",
            name="check_payment_split_valid"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LoanRepayment(id={self.id}, "
            f"loan_id={self.loan_id}, "
            f"amount_paid={self.amount_paid})>"
        )
