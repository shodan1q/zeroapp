"""WebSocket manager for real-time dashboard updates."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total: %d", len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected. Total: %d", len(self.active_connections))

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Push an event to all connected clients.

        Parameters
        ----------
        event_type : str
            One of: pipeline_update, demand_update, build_update,
            stage_change, error, metrics_update
        data : dict
            Arbitrary payload for the event.
        """
        message = json.dumps(
            {
                "type": event_type,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data": data,
            },
            ensure_ascii=False,
            default=str,
        )
        async with self._lock:
            stale: List[WebSocket] = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(message)
                except Exception:
                    stale.append(connection)
            for ws in stale:
                self.active_connections.remove(ws)

    async def send_personal(self, websocket: WebSocket, event_type: str, data: Dict[str, Any]) -> None:
        message = json.dumps(
            {
                "type": event_type,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data": data,
            },
            ensure_ascii=False,
            default=str,
        )
        await websocket.send_text(message)


# Singleton instance
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Main WebSocket endpoint for dashboard real-time updates."""
    await manager.connect(websocket)
    try:
        # Send a welcome event
        await manager.send_personal(websocket, "connected", {"message": "Dashboard WebSocket connected"})
        # Keep connection alive; listen for client messages (ping/pong, etc.)
        while True:
            data = await websocket.receive_text()
            # Echo back pings or handle client commands
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_personal(websocket, "pong", {})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
