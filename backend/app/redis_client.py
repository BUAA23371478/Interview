"""
Redis 连接管理（生产级）。

设计要点
--------
1. **连接池**：高并发场景下每次新建连接的开销不可忽略。
   redis.asyncio 提供 `ConnectionPool`，单例复用。
2. **Sentinel 支持**：生产环境 Redis 通常跑 Sentinel（HA），
   配置 `REDIS_SENTINELS=host1:port1,host2:port2` 自动启用。
3. **降级到内存**：连接失败时降级到内存 dict（仅 dev 用），不影响业务可用性。
4. **异步优先**：全程 redis.asyncio，不阻塞事件循环。

Sentinel vs 单点
~~~~~~~~~~~~~~
- 单点（默认）：`REDIS_HOST:REDIS_PORT` 直连
- Sentinel：`REDIS_SENTINELS=10.0.0.1:26379,10.0.0.2:26379` + `REDIS_MASTER=master`
  自动发现主节点并连接，从故障中自动恢复。
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

from loguru import logger

from app.config import settings


class _MemoryRedis:
    """Redis 不可用时的内存降级实现。仅支持最常用的 KV + TTL。

    注意：进程内 dict，多实例部署**不会**跨进程共享，仅保证单进程可用性。
    """
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._exp: dict[str, float] = {}

    async def get(self, key: str) -> Optional[bytes]:
        self._gc(key)
        v = self._data.get(key)
        return v if v is None else (v.encode() if isinstance(v, str) else v)

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        self._data[key] = value.decode() if isinstance(value, bytes) else value
        if ex is not None:
            self._exp[key] = asyncio.get_event_loop().time() + ex
        return True

    async def eval(self, _script: str, _numkeys: int, *args: Any) -> Any:
        # 内存版不支持 Lua；rate_limit 在 Redis 不可用时退化（见下文）。
        return None

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def _gc(self, key: str) -> None:
        if key in self._exp and asyncio.get_event_loop().time() > self._exp[key]:
            self._data.pop(key, None)
            self._exp.pop(key, None)


class RedisClient:
    """统一的 Redis 访问入口。"""

    def __init__(self) -> None:
        self._client: Any = None
        self._lock = asyncio.Lock()
        self._sentinel_mode = False
        self._init_attempted = False

    async def _ensure(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is not None:
                return self._client
            if self._init_attempted:
                return self._client
            self._init_attempted = True
            self._client = await self._build()
            return self._client

    async def _build(self) -> Any:
        # Sentinel 模式
        sentinels = (getattr(settings, "redis_sentinels", "") or "").strip()
        master_name = (getattr(settings, "redis_master", "master") or "master").strip()
        if sentinels:
            try:
                import redis.asyncio as redis_asyncio
                nodes = []
                for s in sentinels.split(","):
                    host, _, port = s.strip().partition(":")
                    if host and port:
                        nodes.append((host, int(port)))
                if nodes:
                    from redis.asyncio.sentinel import Sentinel
                    sentinel = Sentinel(nodes, password=settings.redis_password,
                                        socket_timeout=2.0)
                    client = sentinel.master_for(master_name,
                                                  password=settings.redis_password,
                                                  db=settings.redis_db,
                                                  decode_responses=False)
                    await client.ping()
                    self._sentinel_mode = True
                    logger.info("Redis 通过 Sentinel 连接（master={}）", master_name)
                    return client
            except Exception as e:  # noqa: BLE001
                logger.warning("Sentinel 连接失败，降级为单点模式: {}", e)
        # 单点模式
        try:
            import redis.asyncio as redis_asyncio
            pool = redis_asyncio.ConnectionPool(
                host=settings.redis_host, port=settings.redis_port,
                password=settings.redis_password, db=settings.redis_db,
                max_connections=50, decode_responses=False,
                socket_connect_timeout=2.0, socket_timeout=5.0,
            )
            client = redis_asyncio.Redis(connection_pool=pool)
            await client.ping()
            logger.info("Redis 单点连接 {}:{}", settings.redis_host, settings.redis_port)
            return client
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis 连接失败，降级为内存 dict: {}", e)
            return _MemoryRedis()

    async def get(self, key: str) -> Optional[bytes]:
        return await (await self._ensure()).get(key)

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        return bool(await (await self._ensure()).set(key, value, ex=ex))

    async def eval(self, script: str, numkeys: int, *args: Any) -> Any:
        return await (await self._ensure()).eval(script, numkeys, *args)

    async def ping(self) -> bool:
        try:
            return bool(await (await self._ensure()).ping())
        except Exception:  # noqa: BLE001
            return False

    @property
    def sentinel_mode(self) -> bool:
        return self._sentinel_mode

    async def close(self) -> None:
        if self._client is not None and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass


redis_client = RedisClient()


# ── 与旧代码兼容：同步阻塞 Redis 接口（短期会话使用）──────────────
def sync_redis() -> Any:
    """同步 Redis 实例，给非异步代码（短期会话）使用。

    失败时返回 None，调用方应自行降级到内存 dict。
    """
    try:
        import redis as redis_mod
        return redis_mod.Redis(
            host=settings.redis_host, port=settings.redis_port,
            password=settings.redis_password, db=settings.redis_db,
            socket_connect_timeout=2.0, socket_timeout=5.0,
            health_check_interval=30,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("同步 Redis 初始化失败: {}", e)
        return None