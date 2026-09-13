"""
SSE 事件流：SSEManager（事件缓冲 + 断线回放）+ Emitter（事件/分块推送）。

为什么这样设计（v1.1 可靠性改造）
------------------------------------
两阶段连接模式（先执行逻辑产生内容，再挂载长连接消费事件）天然存在一个
**事件丢失窗口**：逻辑阶段产生的事件如果在客户端 `connect()` 之前 emit，
旧实现里 `manager.get()` 返回 None → `emit()` 直接 return False，事件被静默丢弃，
前端只会看到空白，且后端日志无任何异常（P0 缺陷：SSE 静默丢事件）。

改造后把「事件」的存储与「连接」解耦：

- 每个会话有一个 **单调递增的 seq** + **环形缓冲（deque）**，event 先落缓冲再谈消费。
  无论此刻有没有客户端连着，事件都不会丢。
- 每条 SSE 消息带 `id: <seq>`。浏览器断线重连会自动带 `Last-Event-ID` 请求头，
  服务端据此**回放**该 seq 之后的所有事件 → 断线不丢进度、不重复推送。
- 消费端以「缓冲」为唯一事实来源，`wakeup` Event 只负责唤醒，避免
  「缓冲 + 队列」双份数据导致的重放/重复投递竞态。
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any, AsyncGenerator, Deque, Dict, Optional

from loguru import logger

from app.config import settings


class SSEConnection:
    """一个会话的事件通道（生命周期独立于客户端连接）。"""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self.seq: int = 0                     # 已产生的事件序号，单调递增
        self.buffer: Deque[dict] = deque(maxlen=settings.sse_replay_buffer)
        self.wakeup = asyncio.Event()
        self.closed = False
        self.done = False                     # 业务侧标记「本会话事件已全部产生完」
        self.last_active = time.monotonic()

    # -- 内部：产生一条事件（永远先落缓冲）--
    def push(self, event: str, data: Dict[str, Any]) -> dict:
        self.seq += 1
        item = {"id": self.seq, "event": event, "data": data}
        self.buffer.append(item)
        self.last_active = time.monotonic()
        self.wakeup.set()
        return item

    def replay_after(self, last_event_id: int) -> list:
        """取出 seq > last_event_id 的所有缓存事件。"""
        return [e for e in self.buffer if e["id"] > last_event_id]


class SSEManager:
    """管理会话事件通道。"""

    def __init__(self) -> None:
        self._connections: Dict[str, SSEConnection] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_key: str, user_id: int,
                      resume: bool = True) -> SSEConnection:
        """获取/创建会话通道。

        resume=True 时**复用**已有通道（保留缓冲与 seq），这样「逻辑先行、
        连接后到」的场景可以靠回放补齐历史事件；resume=False 用于显式重开会话。
        """
        async with self._lock:
            conn = self._connections.get(session_key)
            if conn is None or (not resume and conn.closed):
                conn = SSEConnection(user_id)
                self._connections[session_key] = conn
            elif resume and conn.closed:
                # 通道已被业务侧关闭：重开一个空通道（不再回放旧会话事件）
                conn = SSEConnection(user_id)
                self._connections[session_key] = conn
            conn.last_active = time.monotonic()
            return conn

    def ensure(self, session_key: str, user_id: int = 0) -> SSEConnection:
        """同步获取/创建通道。

        关键点：**业务逻辑先跑、客户端后连**的会话必须先有通道承接事件，
        因此 emit 路径用 ensure 而不是 get —— 通道与客户端连接彻底解耦。
        （asyncio 单线程，dict 直接读写无竞态。）
        """
        conn = self._connections.get(session_key)
        if conn is None or conn.closed:
            conn = SSEConnection(user_id)
            self._connections[session_key] = conn
        return conn

    def get(self, session_key: str) -> Optional[SSEConnection]:
        return self._connections.get(session_key)

    def mark_done(self, session_key: str) -> None:
        """标记会话事件已全部产生完，通知消费端在排空缓冲后正常收尾。"""
        conn = self._connections.get(session_key)
        if conn:
            conn.done = True
            conn.wakeup.set()

    async def remove(self, session_key: str) -> None:
        """关闭并销毁通道（会话结束）。"""
        async with self._lock:
            conn = self._connections.pop(session_key, None)
        if conn:
            conn.closed = True
            conn.done = True
            conn.wakeup.set()

    async def sweep(self, idle_seconds: int = 600) -> int:
        """回收长时间无活动的通道，避免 _connections 无限增长。"""
        now = time.monotonic()
        async with self._lock:
            dead = [k for k, c in self._connections.items()
                    if c.closed or (now - c.last_active) > idle_seconds]
            for k in dead:
                self._connections.pop(k, None)
        if dead:
            logger.debug("回收空闲 SSE 通道 {} 个", len(dead))
        return len(dead)

    async def stream_events(self, session_key: str, conn: Optional[SSEConnection] = None,
                            last_event_id: int = 0) -> AsyncGenerator[dict, None]:
        """消费通道事件：先回放 last_event_id 之后的历史，再实时跟随。

        以环形缓冲为唯一事实来源；wakeup Event 仅用于唤醒等待。
        """
        conn = conn or self.get(session_key)
        if conn is None:
            yield {"event": "error", "data": {"message": "连接不存在"}}
            return

        cursor = last_event_id
        # 首轮：回放历史事件（断线重连场景）
        for item in conn.replay_after(cursor):
            cursor = item["id"]
            yield item

        while not conn.closed:
            # 缓冲里还有没消费的（可能是回放期间/上一次等待期间新产生的）
            pending = conn.replay_after(cursor)
            if pending:
                for item in pending:
                    cursor = item["id"]
                    yield item
                continue

            if conn.done:
                break

            conn.wakeup.clear()
            try:
                await asyncio.wait_for(conn.wakeup.wait(),
                                       timeout=settings.sse_heartbeat)
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": {"message": "keepalive"}}
                continue
            if conn.closed:
                break
        # 收尾：把关闭前残留的事件吐干净
        for item in conn.replay_after(cursor):
            yield item


class SSEmitter:
    """向指定会话推送事件。"""

    def __init__(self, manager: SSEManager) -> None:
        self.manager = manager

    async def emit(self, session_key: str, event: str, data: Dict[str, Any]) -> bool:
        """推送一条事件。

        返回 True 表示事件已进入会话缓冲（不代表客户端已收到）。
        与旧实现的关键差异：**没有客户端连接时也会自动建通道并缓冲**，不再静默丢弃。
        """
        conn = self.manager.ensure(session_key)
        conn.push(event, data)
        return True

    async def emit_chunks(self, session_key: str, text: str,
                          start_event: str, chunk_event: str, done_event: str,
                          chunk_size: int = 80) -> bool:
        """按块推送文本流，返回是否成功。"""
        conn = self.manager.ensure(session_key)
        conn.push(start_event, {})
        for i in range(0, len(text), chunk_size):
            conn.push(chunk_event, {"content": text[i:i + chunk_size]})
            await asyncio.sleep(0)
        conn.push(done_event, {})
        return True

    async def emit_stream(self, session_key: str, stream: AsyncGenerator[str, None],
                          start_event: str, chunk_event: str, done_event: str) -> str:
        """从异步生成器逐块推送流式文本，返回完整文本。"""
        conn = self.manager.ensure(session_key)
        conn.push(start_event, {})
        text = ""
        async for c in stream:
            text += c
            conn.push(chunk_event, {"content": c})
        conn.push(done_event, {})
        return text


sse_manager = SSEManager()
sse_emitter = SSEmitter(sse_manager)


def parse_last_event_id(raw: Optional[str]) -> int:
    """解析 Last-Event-ID 请求头（容错：非法值当 0）。"""
    if not raw:
        return 0
    try:
        return max(int(str(raw).strip()), 0)
    except (TypeError, ValueError):
        return 0


def sse_format(event: str, data: Dict[str, Any], event_id: Optional[int] = None) -> str:
    """把事件格式化为 SSE 文本（带 id 供断线回放）。"""
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"
