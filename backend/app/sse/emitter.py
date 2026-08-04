"""
SSE 事件流：SSEManager（连接队列 + 心跳）+ Emitter（事件/分块推送）。

两阶段连接模式：
- 阶段一：请求处理时先执行逻辑产生内容
- 阶段二：挂载长连接，从队列消费事件（可被外部 POST 驱动）
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, Optional

from loguru import logger


class SSEConnection:
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self.queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()
        self.closed = False


class SSEManager:
    """管理会话连接。"""

    def __init__(self) -> None:
        self._connections: Dict[str, SSEConnection] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_key: str, user_id: int) -> SSEConnection:
        async with self._lock:
            conn = self._connections.get(session_key)
            if conn is None or conn.closed:
                conn = SSEConnection(user_id)
                self._connections[session_key] = conn
            return conn

    def get(self, session_key: str) -> Optional[SSEConnection]:
        return self._connections.get(session_key)

    async def remove(self, session_key: str) -> None:
        conn = self._connections.pop(session_key, None)
        if conn:
            conn.closed = True
            await conn.queue.put(None)  # 发送哨兵终止

    async def stream_events(self, session_key: str, conn: Optional[SSEConnection] = None) -> AsyncGenerator[dict, None]:
        """消费连接队列，产出 SSE 事件。"""
        conn = conn or self.get(session_key)
        if conn is None:
            yield {"event": "error", "data": {"message": "连接不存在"}}
            return
        while not conn.closed:
            try:
                event = await asyncio.wait_for(conn.queue.get(), timeout=30)
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": {"message": "keepalive"}}
                continue
            if event is None:
                break
            yield event


class SSEmitter:
    """向指定连接推送事件。"""

    def __init__(self, manager: SSEManager) -> None:
        self.manager = manager

    async def emit(self, session_key: str, event: str, data: Dict[str, Any]) -> bool:
        conn = self.manager.get(session_key)
        if conn is None or conn.closed:
            return False
        await conn.queue.put({"event": event, "data": data})
        return True

    async def emit_chunks(self, session_key: str, text: str,
                          start_event: str, chunk_event: str, done_event: str,
                          chunk_size: int = 80) -> bool:
        """按块推送文本流，返回是否成功。"""
        conn = self.manager.get(session_key)
        if conn is None or conn.closed:
            return False
        await conn.queue.put({"event": start_event, "data": {}})
        for i in range(0, len(text), chunk_size):
            await conn.queue.put({"event": chunk_event, "data": {"content": text[i:i + chunk_size]}})
            await asyncio.sleep(0)
        await conn.queue.put({"event": done_event, "data": {}})
        return True

    async def emit_stream(self, session_key: str, stream: AsyncGenerator[str, None],
                          start_event: str, chunk_event: str, done_event: str) -> str:
        """从异步生成器逐块推送流式文本，返回完整文本。"""
        conn = self.manager.get(session_key)
        if conn is None or conn.closed:
            text = ""
            async for c in stream:
                text += c
            return text
        await conn.queue.put({"event": start_event, "data": {}})
        text = ""
        async for c in stream:
            text += c
            await conn.queue.put({"event": chunk_event, "data": {"content": c}})
        await conn.queue.put({"event": done_event, "data": {}})
        return text


sse_manager = SSEManager()
sse_emitter = SSEmitter(sse_manager)


def sse_format(event: str, data: Dict[str, Any]) -> str:
    """把事件格式化为 SSE 文本。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
