from typing import Optional
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    """Schema for notification response"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    notification_type: str
    message: str
    reference_id: Optional[uuid.UUID] = None
    reference_type: Optional[str] = None
    is_read: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    """Schema for list of notifications"""
    notifications: list[NotificationResponse]
    total: int
    unread_count: int
    
    model_config = ConfigDict(from_attributes=True)


class UnreadCountResponse(BaseModel):
    """Schema for unread notification count"""
    unread_count: int


class MarkAsReadRequest(BaseModel):
    """Schema for marking notifications as read"""
    notification_ids: list[uuid.UUID]