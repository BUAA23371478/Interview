from __future__ import annotations

import asyncio
import json as _json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SSEConnection:
    user_id: int
    queue: asyncio.Queue[Any | None] = field(default_factory=asyncio.Queue)


class SSEManager:
    def __init__(self) -> None:
        self._connections: dict[str, SSEConnection] = {}

    def create_connection(self, session_key: str, user_id: int) -> SSEConnection:
        connection = SSEConnection(user_id=user_id)
        self._connections[session_key] = connection
        return connection

    def remove_connection(self, session_key: str) -> None:
        connection = self._connections.pop(session_key, None)
        if connection:
            connection.queue.put_nowait(None)

    async def send_event(self, session_key: str, event_type: str, data: str) -> None:
        """data 应为 JSON 字符串。"""
        connection = self._connections.get(session_key)
        if connection:
            await connection.queue.put({"event": event_type, "data": data})

    async def stream_events(self, session_key: str) -> AsyncGenerator[dict[str, Any], None]:
        connection = self._connections.get(session_key)
        if not connection:
            yield {"event": "error", "data": _json.dumps({"message": "Session not found"}, ensure_ascii=False)}
            return

        while True:
            try:
                event = await asyncio.wait_for(connection.queue.get(), timeout=30)
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": _json.dumps({"message": "keepalive"}, ensure_ascii=False)}
                continue

            if event is None:
                break
            yield event

    def get_active_sessions(self) -> list[str]:
        return list(self._connections.keys())


sse_manager = SSEManager()
