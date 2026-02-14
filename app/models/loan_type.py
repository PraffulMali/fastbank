from typing import TYPE_CHECKING
import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.interest_rules import InterestRule


class LoanType(BaseModel):
    __tablename__ = "loan_types"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="loan_types",
        lazy="selectin"
    )

    interest_rules: Mapped[list["InterestRule"]] = relationship(
        "InterestRule",
        back_populates="loan_type",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<LoanType(id={self.id}, name={self.name})>"
