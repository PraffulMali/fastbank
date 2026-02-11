from typing import Annotated
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from jose import JWTError, jwt
import logging

from app.config.settings import settings
from app.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.utils.websocket_manager import get_websocket_manager
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_user_from_token(token: str, db: AsyncSession) -> User:
    """
    Validate WebSocket token and get user.
    Similar to get_current_user but for WebSocket connections.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str: str = payload.get("sub")
        
        if user_id_str is None:
            raise ValueError("Invalid token")
        
        user_id = uuid.UUID(user_id_str)
        
        # Get user from database
        user = await db.get(User, user_id)
        
        if user is None:
            raise ValueError("User not found")
        
        if not user.is_active:
            raise ValueError("User account is inactive")
        
        if not user.is_email_verified:
            raise ValueError("Email not verified")
        
        return user
        
    except (JWTError, ValueError) as e:
        raise ValueError(f"Invalid token: {e}")


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token for authentication"),
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time notifications.
    
    Usage:
    - Connect with: ws://localhost:8000/ws?token=<access_token>
    - Receives real-time notifications
    - Sends heartbeat every 30 seconds
    
    Message Format (from server):
    {
        "type": "notification",
        "data": {
            "id": "uuid",
            "notification_type": "TRANSACTION_SUCCESS",
            "message": "...",
            "reference_id": "uuid",
            "reference_type": "transaction",
            "is_read": false,
            "created_at": "2024-01-01T00:00:00"
        }
    }
    
    Or for status updates:
    {
        "type": "transaction_status",
        "data": {
            "transaction_id": "uuid",
            "status": "SUCCESS",
            "message": "Transaction completed successfully"
        }
    }
    
    Or heartbeat:
    {
        "type": "heartbeat",
        "timestamp": "2024-01-01T00:00:00"
    }
    """
    user = None
    manager = get_websocket_manager()
    
    try:
        # Validate token and get user
        user = await get_user_from_token(token, db)
        
        # Determine if user is admin
        is_admin = user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
        
        # Connect to WebSocket manager
        await manager.connect(websocket, user.id, is_admin)
        
        logger.info(f"WebSocket connected: User {user.id} ({user.email})")
        
        # Send connection success message
        await websocket.send_json({
            "type": "connected",
            "message": f"Connected successfully as {user.email}",
            "user_id": str(user.id),
            "role": user.role.value
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            # Wait for messages from client (e.g., heartbeat responses)
            data = await websocket.receive_json()
            
            # Handle client messages (optional - for heartbeat confirmation, etc.)
            if data.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": data.get("timestamp")
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: User {user.id if user else 'Unknown'}")
        if user:
            manager.disconnect(websocket, user.id)
    
    except ValueError as e:
        logger.error(f"WebSocket authentication error: {e}")
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))
        except:
            pass
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if user:
            manager.disconnect(websocket, user.id)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except:
            pass