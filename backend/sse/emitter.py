from __future__ import annotations

import json as _json
from collections.abc import AsyncGenerator

from backend.sse.manager import sse_manager


class SSEEmitter:
    def __init__(self, session_key: str) -> None:
        self.session_key = session_key

    async def emit(self, event_type: str, data: dict) -> None:
        """发送 SSE 事件（data 自动 JSON 序列化）。"""
        await sse_manager.send_event(self.session_key, event_type, _json.dumps(data, ensure_ascii=False))

    async def emit_text(self, event_type: str, text: str) -> None:
        await self.emit(event_type, {"content": text})

    async def emit_stream_chunks(
        self,
        event_type: str,
        chunks: AsyncGenerator[str, None],
        done_event: str | None = None,
        done_data: dict | None = None,
    ) -> str:
        content: list[str] = []
        async for chunk in chunks:
            content.append(chunk)
            await self.emit(event_type, {"content": chunk})
        if done_event:
            await self.emit(done_event, done_data or {})
        return "".join(content)
