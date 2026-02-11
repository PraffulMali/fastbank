from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.notification import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkAsReadRequest
)
from app.services.notification_service import NotificationService
from app.dependencies import get_current_user
from app.utils.pagination import Paginator, Page

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)


@router.get("/", response_model=Page[NotificationResponse])
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    paginator: Paginator = Depends(),
    unread_only: bool = Query(False, description="Filter for unread notifications only")
):
    """
    Get paginated list of notifications for the current user.
    
    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 10, max: 100)
    - unread_only: Show only unread notifications (default: false)
    
    Returns notifications ordered by creation date (newest first).
    """
    return await NotificationService.get_user_notifications(
        db, current_user.id, paginator, unread_only
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get count of unread notifications for the current user.
    Useful for displaying notification badges.
    """
    count = await NotificationService.get_unread_count(db, current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_as_read(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Mark a specific notification as read.
    Only the owner of the notification can mark it as read.
    """
    try:
        notification = await NotificationService.mark_as_read(
            db, notification_id, current_user.id
        )
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        return notification
    
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.post("/mark-all-read", status_code=status.HTTP_200_OK)
async def mark_all_as_read(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Mark all notifications as read for the current user.
    Returns count of notifications that were marked as read.
    """
    count = await NotificationService.mark_all_as_read(db, current_user.id)
    return {
        "message": f"Marked {count} notification(s) as read",
        "count": count
    }


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Delete (soft delete) a notification.
    Only the owner of the notification can delete it.
    """
    try:
        deleted = await NotificationService.delete_notification(
            db, notification_id, current_user.id
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
    
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )