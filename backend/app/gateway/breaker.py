"""模型级熔断器（Circuit Breaker）。

为什么重试之外还需要熔断
------------------------
重试解决的是「偶发抖动」，熔断解决的是「持续不可用」。
如果没有熔断：某个 provider 宕机时，每个请求都要先等它超时、再重试 3 次
（60s 超时 × 3 ≈ 180s），才轮得到备用模型。用户侧表现为「整场面试卡住」，
而且这台宕机的 provider 会被持续打爆，恢复后又要承受积压流量。

三态机
------
    CLOSED  ──连续失败达阈值──▶  OPEN  ──冷却时间到──▶  HALF_OPEN
      ▲                                                    │
      └──────────── 探测成功 ───────────────────────────────┘
                    探测失败 → 回到 OPEN（冷却时间指数增长）

- CLOSED：正常调用；
- OPEN：**直接跳过该模型**，不再浪费一次超时等待，秒级切到备用模型；
- HALF_OPEN：放行少量探测请求，成功即恢复，失败则继续熔断（冷却时间翻倍，上限封顶）。

与「降级链」的关系：熔断决定「这一档还值不值得试」，降级链决定「不行就换谁」。
两者叠加后，单 provider 故障对用户的影响从「等满超时」降为「直接换模型」。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from loguru import logger

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


@dataclass
class _State:
    status: str = CLOSED
    consecutive_failures: int = 0
    opened_at: float = 0.0
    cooldown: float = 0.0
    probes_in_flight: int = 0
    total_calls: int = 0
    total_rejected: int = 0
    total_failures: int = 0


@dataclass
class BreakerStats:
    failures: int = 0
    rejections: int = 0


class CircuitBreaker:
    """按模型 id 隔离的熔断器集合。"""

    def __init__(self, *, failure_threshold: int = 3, cooldown: float = 30.0,
                 max_cooldown: float = 300.0, probes: int = 1) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.base_cooldown = max(1.0, cooldown)
        self.max_cooldown = max(self.base_cooldown, max_cooldown)
        self.probes = max(1, probes)
        self._states: Dict[str, _State] = {}

    # ── 查询状态 ──────────────────────────────────────────────────
    def allow(self, key: str) -> Tuple[bool, str]:
        """是否放行本次调用，返回 (放行?, 原因)。"""
        st = self._states.get(key)
        if st is None or st.status == CLOSED:
            return True, CLOSED
        if st.status == OPEN:
            if time.monotonic() - st.opened_at >= st.cooldown:
                st.status = HALF_OPEN
                st.probes_in_flight = 0
                logger.info("熔断器 {} 进入半开，放行探测请求", key)
            else:
                st.total_rejected += 1
                return False, OPEN
        # HALF_OPEN：只放行有限个探测请求
        if st.status == HALF_OPEN:
            if st.probes_in_flight >= self.probes:
                st.total_rejected += 1
                return False, HALF_OPEN
            st.probes_in_flight += 1
            return True, HALF_OPEN
        return True, st.status

    def record_success(self, key: str) -> None:
        st = self._states.get(key)
        if st is None:
            return
        st.total_calls += 1
        if st.status == HALF_OPEN:
            logger.info("熔断器 {} 探测成功，恢复为闭合", key)
        st.status = CLOSED
        st.consecutive_failures = 0
        st.cooldown = 0.0
        st.probes_in_flight = 0

    def record_failure(self, key: str) -> None:
        st = self._states.setdefault(key, _State())
        st.total_calls += 1
        st.total_failures += 1
        st.consecutive_failures += 1
        if st.status == HALF_OPEN:
            # 探测失败：继续熔断，冷却时间指数增长（避免恢复期被持续打爆）
            st.cooldown = min(self.max_cooldown, max(st.cooldown * 2, self.base_cooldown))
            st.status = OPEN
            st.opened_at = time.monotonic()
            st.probes_in_flight = 0
            logger.warning("熔断器 {} 探测失败，冷却延长至 {:.0f}s", key, st.cooldown)
            return
        if st.consecutive_failures >= self.failure_threshold:
            st.cooldown = st.cooldown or self.base_cooldown
            st.status = OPEN
            st.opened_at = time.monotonic()
            logger.warning("熔断器 {} 连续失败 {} 次，开启熔断 {:.0f}s",
                           key, st.consecutive_failures, st.cooldown)

    def reset(self, key: Optional[str] = None) -> None:
        if key is None:
            self._states.clear()
        else:
            self._states.pop(key, None)

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        """可观测快照：谁被熔断了、冷却还剩多久。"""
        now = time.monotonic()
        out: Dict[str, Dict[str, object]] = {}
        for key, st in self._states.items():
            remaining = 0.0
            if st.status == OPEN:
                remaining = max(0.0, st.cooldown - (now - st.opened_at))
            out[key] = {
                "status": st.status,
                "consecutive_failures": st.consecutive_failures,
                "cooldown_s": round(st.cooldown, 1),
                "retry_in_s": round(remaining, 1),
                "calls": st.total_calls,
                "failures": st.total_failures,
                "rejected": st.total_rejected,
            }
        return out


llm_breaker = CircuitBreaker(failure_threshold=3, cooldown=30.0, max_cooldown=300.0)
