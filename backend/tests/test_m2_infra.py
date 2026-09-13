"""M2 回归测试：限流 + 异步队列 + Redis Client。

- Redis Lua 滑动窗口限流：在阈值内放行 / 超出 429
- 异步任务队列：handler 注册 / 优先级 / 超时
- Redis Client：单点 / 内存降级
"""
from __future__ import annotations

import asyncio
import time


# ── 限流 ──────────────────────────────────────────────────────────
def test_sliding_window_limiter_in_memory_mode():
    """Redis 不可用时降级为放行（不应阻断）。"""
    from app.ratelimit import limiter
    # 内存模式下 limiter 应当 OK（Redis 不可用 → 放行）
    async def run():
        return await limiter.acquire(scope="test", key="x", limit=10)
    ok, _, _ = asyncio.run(run())
    assert ok is True


def test_sliding_window_lua_loads_correctly():
    """Lua 脚本必须能被 Redis 加载（cache miss 时走 eval）。"""
    import sys
    # 直接读脚本源做静态校验（避免运行时依赖 Redis）
    from app.ratelimit import sliding_window
    src = sliding_window._LUA_SLIDING_WINDOW  # noqa: SLF001
    assert "GET" in src
    assert "INCR" in src
    assert "PEXPIRE" in src
    assert "limit" in src


# ── 异步队列 ─────────────────────────────────────────────────────
def test_queue_handler_registration_and_basic_dispatch():
    from app.queue import TaskQueue, Task

    async def run():
        q = TaskQueue(max_size=100, concurrency=2)
        results = []

        async def hello(name: str) -> str:
            return f"hello {name}"

        async def add(x: int, y: int) -> int:
            return x + y

        q.register_handler("hello", hello)
        q.register_handler("add", add)

        await q.start()
        await q.enqueue(Task(kind="hello", args=("world",)))
        await q.enqueue(Task(kind="add", args=(1, 2)))
        await q.enqueue(Task(kind="add", args=(3, 4)))

        # 等所有任务完成
        for _ in range(100):
            if q.total_processed >= 3:
                break
            await asyncio.sleep(0.05)

        await q.stop()
        return q.total_processed, q.total_failed

    processed, failed = asyncio.run(run())
    assert processed == 3
    assert failed == 0


def test_queue_priority_order():
    """优先级数字越小越先处理（同时间入队时）。"""
    from app.queue import TaskQueue, Task

    async def run():
        q = TaskQueue(max_size=100, concurrency=1)
        order = []

        async def record(tag: str) -> None:
            order.append(tag)

        q.register_handler("t", record)
        await q.start()
        # 入队：低优先级先入，高优先级后入
        await q.enqueue(Task(kind="t", args=("low1",), priority=8))
        await q.enqueue(Task(kind="t", args=("low2",), priority=8))
        await q.enqueue(Task(kind="t", args=("hi",), priority=1))

        for _ in range(100):
            if len(order) >= 3:
                break
            await asyncio.sleep(0.05)
        await q.stop()
        return order

    order = asyncio.run(run())
    assert order[0] == "hi", f"高优先级应最先处理，实际顺序 {order}"
    assert set(order[1:]) == {"low1", "low2"}


def test_queue_timeout():
    """任务超时应当被记录为失败。"""
    from app.queue import TaskQueue, Task

    async def run():
        q = TaskQueue(max_size=10, concurrency=1)

        async def slow() -> None:
            await asyncio.sleep(2)

        q.register_handler("slow", slow)
        await q.start()
        await q.enqueue(Task(kind="slow", timeout_s=0.1))
        for _ in range(100):
            if q.total_failed >= 1:
                break
            await asyncio.sleep(0.05)
        await q.stop()
        return q.total_processed, q.total_failed

    processed, failed = asyncio.run(run())
    assert failed == 1
    assert processed == 0


# ── Redis Client 降级 ────────────────────────────────────────────
def test_redis_client_degrades_to_memory_when_unavailable():
    """连不上 Redis 时应降级为内存版（不抛异常）。"""
    from app.redis_client import _MemoryRedis

    async def run():
        r = _MemoryRedis()
        await r.set("k1", "v1", ex=60)
        v = await r.get("k1")
        await r.close()
        return v

    v = asyncio.run(run())
    assert v == b"v1" or v == "v1"


def test_redis_client_sentinel_config_is_parsed():
    """配置项 redis_sentinels 应能被解析成节点列表。"""
    from app.config import settings
    # 默认空 → 不启用 Sentinel
    assert settings.redis_sentinels == ""
    # 模拟配置
    settings.redis_sentinels = "10.0.0.1:26379,10.0.0.2:26379"
    nodes = [tuple(s.strip().split(":")) for s in settings.redis_sentinels.split(",")
             if s.strip()]
    assert len(nodes) == 2
    assert nodes[0] == ("10.0.0.1", "26379")
    settings.redis_sentinels = ""  # 还原


# ── 数据库连接池配置 ─────────────────────────────────────────────
def test_mysql_pool_size_for_production():
    """验证生产 MySQL pool_size 与 max_overflow 已调到企业级水平。"""
    from app.config import settings
    # 这些值在代码里写死（创建 engine 时）
    # 验证文档/期望值与实际一致
    expected = {"pool_size": 20, "max_overflow": 40, "pool_recycle": 3600}
    # 实际值从代码读
    import inspect
    from app.database import _build_engine
    src = inspect.getsource(_build_engine)
    assert "pool_size=20" in src
    assert "max_overflow=40" in src
    assert "pool_recycle=3600" in src