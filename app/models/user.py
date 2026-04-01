from typing import TYPE_CHECKING
import uuid
from sqlalchemy import (
    String,
    ForeignKey,
    Enum as SQLEnum,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user_identity import UserIdentity
    from app.models.account import Account
    from app.models.notification import Notification
    from app.models.loan import Loan


class User(BaseModel):
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(default=False)

    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role_enum", create_constraint=True),
        nullable=False,
        default=UserRole.USER,
        index=True,
    )

    tenant: Mapped["Tenant | None"] = relationship(
        "Tenant", back_populates="users", lazy="selectin"
    )

    user_identity: Mapped["UserIdentity | None"] = relationship(
        "UserIdentity",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="UserIdentity.user_id",
    )

    accounts: Mapped[list["Account"]] = relationship(
        "Account", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    loans: Mapped[list["Loan"]] = relationship(
        "Loan",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="Loan.user_id",
    )

    decided_loans: Mapped[list["Loan"]] = relationship(
        "Loan",
        foreign_keys="Loan.decided_by",
        back_populates="decision_maker",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "(role = 'SUPER_ADMIN' AND tenant_id IS NULL) OR "
            "(role != 'SUPER_ADMIN' AND tenant_id IS NOT NULL)",
            name="check_super_admin_no_tenant",
        ),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, tenant_id={self.tenant_id})>"
