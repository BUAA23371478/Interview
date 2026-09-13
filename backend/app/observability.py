"""
可观测层：请求级 Token/成本计量 + 全链路 span 追踪。

解决「面试官问『你怎么知道哪个环节慢、哪一步烧钱』答不上来」的问题。

设计要点：
  - `Meter` 挂在 contextvar 上，天然按请求隔离，多租户并发下不会互相污染；
  - LLM 客户端把 API 返回的 usage 回填进当前 Meter（真实计量，而非估算）；
  - `span()` 以异步上下文管理器形式包裹每个 Agent 调用，记录 耗时/token/成本/状态；
  - 所有 span 最终落到 state["trace"]，可持久化、可出看板、可做性能回归。
"""
from __future__ import annotations

import contextvars
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger

# ── 模型计价表（元/百万 token），仅用于成本估算与积分换算 ────────────────
PRICING: Dict[str, Dict[str, float]] = {
    "deepseek-chat": {"in": 1.0, "out": 2.0},
    "deepseek-reasoner": {"in": 4.0, "out": 16.0},
    "deepseek-v4-flash": {"in": 0.5, "out": 1.5},
    "qwen-plus": {"in": 0.8, "out": 2.0},
    "qwen-turbo": {"in": 0.3, "out": 0.6},
    "gpt-4o-mini": {"in": 1.1, "out": 4.4},
}
DEFAULT_PRICE = {"in": 1.0, "out": 2.0}


def price_of(model: str) -> Dict[str, float]:
    for key, val in PRICING.items():
        if key in (model or ""):
            return val
    return DEFAULT_PRICE


def cost_yuan(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = price_of(model)
    return (prompt_tokens * p["in"] + completion_tokens * p["out"]) / 1_000_000


class Meter:
    """请求级计量器：累计 token、成本、调用次数。"""

    def __init__(self) -> None:
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost = 0.0
        self.by_model: Dict[str, Dict[str, float]] = {}

    def record(self, model: str, prompt_tokens: int = 0,
               completion_tokens: int = 0, cost: Optional[float] = None) -> None:
        self.calls += 1
        self.prompt_tokens += max(0, prompt_tokens)
        self.completion_tokens += max(0, completion_tokens)
        self.cost += cost if cost is not None else cost_yuan(
            model, prompt_tokens, completion_tokens)
        item = self.by_model.setdefault(model or "unknown", {"calls": 0, "in": 0, "out": 0})
        item["calls"] += 1
        item["in"] += prompt_tokens
        item["out"] += completion_tokens

    def snapshot(self) -> Dict[str, Any]:
        return {
            "llm_calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "cost_yuan": round(self.cost, 6),
            "by_model": self.by_model,
        }


_meter_ctx: contextvars.ContextVar[Optional[Meter]] = contextvars.ContextVar("meter_ctx", default=None)


def new_meter() -> Meter:
    m = Meter()
    _meter_ctx.set(m)
    return m


def current_meter() -> Optional[Meter]:
    return _meter_ctx.get()


def record_usage(model: str, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
    """由 LLM 客户端调用，把真实 usage 记入当前请求的计量器。"""
    meter = _meter_ctx.get()
    if meter is not None:
        meter.record(model, prompt_tokens, completion_tokens)


# ── span 追踪 ────────────────────────────────────────────────────────
@asynccontextmanager
async def span(state: Optional[Dict[str, Any]], name: str,
               **meta: Any) -> AsyncGenerator[Dict[str, Any], None]:
    """记录一个执行步骤的耗时与 token 消耗。

    用法：
        async with span(state, "jd_analyzer") as sp:
            await jd_analyzer.run(state)
            sp["meta"]["chars"] = len(jd_text)
    """
    t0 = time.perf_counter()
    meter = current_meter()
    before = (meter.calls, meter.prompt_tokens + meter.completion_tokens) if meter else (0, 0)
    sp: Dict[str, Any] = {"name": name, "meta": dict(meta), "status": "ok"}
    try:
        yield sp
    except Exception as e:  # noqa: BLE001
        sp["status"] = "error"
        sp["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        sp["dur_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if meter is not None:
            calls_after, tokens_after = meter.calls, meter.prompt_tokens + meter.completion_tokens
            sp["llm_calls"] = calls_after - before[0]
            sp["tokens"] = tokens_after - before[1]
        if state is not None:
            state.setdefault("trace", []).append(sp)


def summarize(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """聚合一次请求的 trace：总耗时、分步耗时、token 与成本。"""
    if not state:
        return {}
    trace: List[Dict[str, Any]] = state.get("trace", []) or []
    meter = current_meter()
    by_step = [
        {"step": s.get("name"), "dur_ms": s.get("dur_ms"), "tokens": s.get("tokens", 0),
         "status": s.get("status")}
        for s in trace
    ]
    return {
        "steps": by_step,
        "total_step_ms": round(sum(s.get("dur_ms", 0) or 0 for s in trace), 1),
        "llm": meter.snapshot() if meter else {},
        "errors": [s for s in trace if s.get("status") == "error"],
    }


def log_summary(state: Optional[Dict[str, Any]], label: str = "request") -> None:
    info = summarize(state)
    if not info:
        return
    logger.info("[trace] {} 步骤 {} 个 / 累计 {}ms / LLM {} 次 / {} tokens / ¥{}",
                label, len(info["steps"]), info["total_step_ms"],
                info["llm"].get("llm_calls", 0), info["llm"].get("total_tokens", 0),
                info["llm"].get("cost_yuan", 0))
    for s in sorted(info["steps"], key=lambda x: -(x["dur_ms"] or 0))[:5]:
        logger.info("[trace]   {:<20} {:>8.1f}ms  {} tokens  {}",
                    s["step"], s["dur_ms"] or 0, s["tokens"], s["status"])
