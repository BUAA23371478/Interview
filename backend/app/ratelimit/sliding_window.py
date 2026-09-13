"""
Redis 滑动窗口限流（Lua 原子实现）。

为什么用滑动窗口而不是 token bucket
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- 滑动窗口实现简单：固定窗口计数器在边界处可能 2x 突发（前一秒尾 + 后一秒头各放满）
- 滑动窗口日志（sliding-window-log）精确但内存大（每请求一条记录）
- 滑动窗口计数（sliding-window-counter）折中：当前窗口 + 前一窗口加权，O(1) 内存
  本实现即采用此方案——生产足够精确，又不需要 per-request 存储。

三档桶
~~~~
- 全局桶：保护服务端不被流量打爆（100 QPS 默认）
- 每用户桶：防止单个用户占用所有配额（10 QPS 默认）
- 每 IP 桶：恶意 IP 兜底（20 QPS 默认）

Lua 脚本意义：把「读 → 累加 → 判定 → 回写」做成一次原子操作，
避免多 worker 之间 check-then-act 出现竞态。
"""
from __future__ import annotations

from typing import Optional

from loguru import logger

from app.config import settings
from app.redis_client import redis_client


# Lua 脚本：滑动窗口计数
# key: 桶名；limit: 阈值；window_ms: 窗口长度（毫秒）
# 读两个窗口的计数，按时间比例加权，与 limit 比较
_LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local now_ms = tonumber(ARGV[2])
local window_ms = tonumber(ARGV[3])

local cur_key = key .. ':' .. math.floor(now_ms / window_ms)
local prev_key = key .. ':' .. (math.floor(now_ms / window_ms) - 1)

local cur = tonumber(redis.call('GET', cur_key) or '0')
local prev = tonumber(redis.call('GET', prev_key) or '0')

local weight = (now_ms % window_ms) / window_ms
local weighted = math.floor(cur + prev * weight)

if weighted >= limit then
    return {0, weighted, limit}
end

redis.call('INCR', cur_key)
redis.call('PEXPIRE', cur_key, window_ms * 2)
return {1, weighted + 1, limit}
"""


class SlidingWindowLimiter:
    """滑动窗口限流器。"""

    def __init__(self) -> None:
        self._enabled = True
        self._script_sha: Optional[str] = None
        self._script_src = _LUA_SLIDING_WINDOW

    async def _load_script(self) -> Optional[str]:
        if self._script_sha is not None:
            return self._script_sha
        try:
            client = await redis_client._ensure()
            self._script_sha = await client.script_load(self._script_src)
            return self._script_sha
        except Exception as e:  # noqa: BLE001
            logger.warning("限流 Lua 脚本加载失败: {}", e)
            return None

    async def acquire(self, *, scope: str, key: str, limit: int,
                      window_ms: int = 1000) -> tuple[bool, int, int]:
        if not self._enabled:
            return True, 0, limit
        bucket = f"rl:{scope}:{key}"
        now_ms = int(_now_ms())
        sha = await self._load_script()
        if sha is None:
            return True, 0, limit
        try:
            client = await redis_client._ensure()
            res = await client.evalsha(sha, 1, bucket, limit, now_ms, window_ms)
            allowed = bool(int(res[0])) if res else True
            current = int(res[1]) if res and len(res) > 1 else 0
            return allowed, current, limit
        except Exception as e:  # noqa: BLE001
            logger.warning("限流检查失败（降级放行）: {}", e)
            return True, 0, limit


def _now_ms() -> int:
    import time
    return time.time() * 1000


limiter = SlidingWindowLimiter()


async def enforce_rate_limit(*, scope: str, key: str, limit: Optional[int] = None,
                             window_ms: int = 1000):
    """强制限流（FastAPI 依赖层调用）。"""
    from fastapi import HTTPException
    if limit is None:
        limit = settings.rate_limit_default
    allowed, current, lim = await limiter.acquire(
        scope=scope, key=key, limit=limit, window_ms=window_ms)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"限流：scope={scope} key={key} current={current} limit={lim}",
            headers={"Retry-After": str(window_ms // 1000)},
        )