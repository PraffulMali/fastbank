from typing import Dict, List
import uuid
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:

    def __init__(self):
        self.active_connections: Dict[uuid.UUID, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: uuid.UUID):
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        self.active_connections[user_id].append(websocket)

        logger.info(
            f"WebSocket Connected - Status=Joined | "
            f"UserID={user_id} | "
            f"ConnectionCount={len(self.active_connections[user_id])}"
        )

    def disconnect(self, websocket: WebSocket, user_id: uuid.UUID):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
                logger.info(
                    f"WebSocket Disconnected - Status=Left | "
                    f"UserID={user_id} | "
                    f"RemainingConnections={len(self.active_connections[user_id])}"
                )

            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: uuid.UUID):
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(
                        f"WebSocket Send Error - UserID={user_id} | Error={str(e)}"
                    )
                    disconnected.append(connection)

            for dead_connection in disconnected:
                self.disconnect(dead_connection, user_id)


manager = ConnectionManager()


def get_websocket_manager() -> ConnectionManager:
    return manager
