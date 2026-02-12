from typing import Dict, List, Set
import uuid
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time notifications.
    
    Features:
    - Multiple connections per user (different devices/tabs)
    - Broadcast to specific users
    - Broadcast to all admins
    - Connection cleanup on disconnect
    """
    
    def __init__(self):
        # user_id -> list of WebSocket connections
        self.active_connections: Dict[uuid.UUID, List[WebSocket]] = {}
        # admin_user_ids for quick admin broadcast
        self.admin_users: Set[uuid.UUID] = set()
    
    async def connect(self, websocket: WebSocket, user_id: uuid.UUID, is_admin: bool = False):
        """
        Connect a new WebSocket for a user.
        A user can have multiple connections (different tabs/devices).
        """
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        
        self.active_connections[user_id].append(websocket)
        
        if is_admin:
            self.admin_users.add(user_id)
        
        logger.info(f"User {user_id} connected. Total connections: {len(self.active_connections[user_id])}")
    
    def disconnect(self, websocket: WebSocket, user_id: uuid.UUID):
        """
        Remove a WebSocket connection for a user.
        If no more connections exist for the user, remove the user entry.
        """
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
                logger.info(f"User {user_id} disconnected. Remaining connections: {len(self.active_connections[user_id])}")
            
            # Clean up if no connections left
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                if user_id in self.admin_users:
                    self.admin_users.discard(user_id)
    
    async def send_personal_message(self, message: dict, user_id: uuid.UUID):
        """
        Send a message to all connections of a specific user.
        """
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to user {user_id}: {e}")
                    disconnected.append(connection)
            
            # Clean up dead connections
            for dead_connection in disconnected:
                self.disconnect(dead_connection, user_id)
    
    async def broadcast_to_admins(self, message: dict):
        """
        Broadcast a message to all admin users.
        """
        for admin_id in list(self.admin_users):
            await self.send_personal_message(message, admin_id)
    
    async def broadcast_to_all(self, message: dict):
        """
        Broadcast a message to all connected users.
        """
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)


# Global singleton instance
manager = ConnectionManager()


def get_websocket_manager() -> ConnectionManager:
    """Get the global WebSocket manager instance."""
    return manager