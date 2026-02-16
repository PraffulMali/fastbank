from typing import Dict, List, Set
import uuid
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    
    def __init__(self):
        # user_id -> list of WebSocket connections
        self.active_connections: Dict[uuid.UUID, List[WebSocket]] = {}
        # admin_user_ids for quick admin broadcast
        self.admin_users: Set[uuid.UUID] = set()
    
    async def connect(self, websocket: WebSocket, user_id: uuid.UUID, is_admin: bool = False):
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        
        self.active_connections[user_id].append(websocket)
        
        if is_admin:
            self.admin_users.add(user_id)
        
        logger.info(f"User {user_id} connected. Total connections: {len(self.active_connections[user_id])}")
    
    def disconnect(self, websocket: WebSocket, user_id: uuid.UUID):
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
        for admin_id in list(self.admin_users):
            await self.send_personal_message(message, admin_id)
    
    async def broadcast_to_all(self, message: dict):
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)


# Global singleton instance
manager = ConnectionManager()


def get_websocket_manager() -> ConnectionManager:
    return manager