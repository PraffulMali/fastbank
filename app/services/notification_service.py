from typing import List, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import datetime

from app.models.notification import Notification
from app.models.enums import NotificationType
from app.models.user import User
from app.utils.pagination import Paginator, Page
from app.utils.websocket_manager import get_websocket_manager


class NotificationService:

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        message: str,
        reference_id: Optional[uuid.UUID] = None,
        reference_type: Optional[str] = None,
        send_websocket: bool = True,
    ) -> Notification:
        notification = Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            notification_type=notification_type,
            message=message,
            reference_id=reference_id,
            reference_type=reference_type,
            is_read=False,
        )

        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        if send_websocket:
            await NotificationService.send_websocket_notification(notification)

        return notification

    @staticmethod
    async def send_websocket_notification(notification: Notification):
        manager = get_websocket_manager()

        message = {
            "type": "notification",
            "data": {
                "id": str(notification.id),
                "notification_type": notification.notification_type.value,
                "message": notification.message,
                "reference_id": (
                    str(notification.reference_id)
                    if notification.reference_id
                    else None
                ),
                "reference_type": notification.reference_type,
                "is_read": notification.is_read,
                "created_at": notification.created_at.isoformat(),
            },
        }

        await manager.send_personal_message(message, notification.user_id)

    @staticmethod
    async def get_user_notifications(
        db: AsyncSession,
        user_id: uuid.UUID,
        paginator: Paginator,
        unread_only: bool = False,
    ) -> Page:
        query = select(Notification).where(Notification.user_id == user_id)

        if unread_only:
            query = query.where(Notification.is_read == False)

        query = query.order_by(Notification.created_at.desc())

        return await paginator.paginate(db, query)

    @staticmethod
    async def get_unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
        query = (
            select(func.count())
            .select_from(Notification)
            .where(and_(Notification.user_id == user_id, Notification.is_read == False))
        )
        result = await db.execute(query)
        return result.scalar_one()

    @staticmethod
    async def mark_as_read(
        db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[Notification]:
        notification = await db.get(Notification, notification_id)

        if not notification:
            return None

        if notification.user_id != user_id:
            raise PermissionError("Cannot mark another user's notification as read")

        notification.is_read = True
        await db.commit()
        await db.refresh(notification)

        return notification

    @staticmethod
    async def mark_all_as_read(db: AsyncSession, user_id: uuid.UUID) -> int:
        from sqlalchemy import update

        stmt = (
            update(Notification)
            .where(and_(Notification.user_id == user_id, Notification.is_read == False))
            .values(is_read=True)
        )

        result = await db.execute(stmt)
        await db.commit()

        return result.rowcount

    @staticmethod
    async def delete_notification(
        db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        notification = await db.get(Notification, notification_id)

        if not notification:
            return False

        if notification.user_id != user_id:
            raise PermissionError("Cannot delete another user's notification")

        notification.is_active = False
        notification.deleted_at = datetime.now()

        await db.commit()

        return True
