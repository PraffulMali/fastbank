from typing import TYPE_CHECKING
import uuid
from datetime import date, datetime
from sqlalchemy import (
    String,
    Date,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class UserIdentity(BaseModel):
    __tablename__ = "user_identities"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    pan_number: Mapped[str] = mapped_column(String(10), nullable=False)

    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="India")

    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant", back_populates="user_identities", lazy="selectin"
    )

    user: Mapped["User"] = relationship(
        "User", back_populates="user_identity", foreign_keys=[user_id], lazy="selectin"
    )

    verifier: Mapped["User | None"] = relationship(
        "User", foreign_keys=[verified_by], lazy="selectin"
    )

    __table_args__ = (
        Index(
            "ix_user_identities_phone_tenant", "phone_number", "tenant_id", unique=True
        ),
        Index("ix_user_identities_pan_tenant", "pan_number", "tenant_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<UserIdentity(id={self.id}, user_id={self.user_id})>"
