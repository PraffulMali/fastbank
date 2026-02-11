from typing import TYPE_CHECKING
import uuid
from sqlalchemy import (
    String,
    Text,
    Boolean,
    ForeignKey,
    Index,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel
from app.models.enums import NotificationType

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.tenant import Tenant


class Notification(BaseModel):
    __tablename__ = "notifications"
    
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
    
    notification_type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType, name="notification_type_enum", create_constraint=True),
        nullable=False,
        index=True
    )
    
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True
    )
    
    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )
    
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        lazy="selectin"
    )
    
    user: Mapped["User"] = relationship(
        "User",
        back_populates="notifications",
        lazy="selectin"
    )
    
    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type={self.notification_type}, user_id={self.user_id})>"