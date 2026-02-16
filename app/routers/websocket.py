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
from app.dependencies import verify_token_and_get_user

router = APIRouter()
logger = logging.getLogger(__name__)




@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token for authentication"),
    db: AsyncSession = Depends(get_db)
):
    # Accept the connection first to allow sending WebSocket close codes (like 1008)
    await websocket.accept()
    
    user = None
    manager = get_websocket_manager()
    
    try:
        # Validate token and get user
        user = await verify_token_and_get_user(token, db)
        
        # Determine if user is admin
        # Determine if user is admin
        # is_admin = user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
        
        # Connect to WebSocket manager
        await manager.connect(websocket, user.id)
        
        logger.info(f"WebSocket connected: User {user.id} ({user.email})")
        
        # Send connection success message
        await websocket.send_json({
            "type": "connected",
            "message": f"Connected successfully as {user.email}",
            "user_id": str(user.id),
            "role": user.role.value
        })
        
        # Keep connection alive and handle incoming messages
        # while True:
        #     # Wait for messages from client (e.g., heartbeat responses)
        #     data = await websocket.receive_json()
            
        #     # Handle client messages (optional - for heartbeat confirmation, etc.)
        #     if data.get("type") == "ping":
        #         await websocket.send_json({
        #             "type": "pong",
        #             "timestamp": data.get("timestamp")
        #         })

        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: User {user.id if user else 'Unknown'}")
        if user:
            manager.disconnect(websocket, user.id)
    
    except (ValueError, HTTPException) as e:
        detail = str(e.detail) if hasattr(e, "detail") else str(e)
        logger.error(f"WebSocket authentication error: {detail}")
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=detail[:120])
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