"""
可观测层：请求级 Token/成本计量 + 全链路 span 追踪 + 全局成本护栏。

解决三个「面试官一问就露馅」的问题：
  1. 哪个环节慢？        → span() 记录每步耗时，随响应返回 trace
  2. 哪一步烧钱？        → Meter 按模型累计 token 与成本，单价用真实价目表
  3. 会不会失控烧光？    → SpendLedger 硬性预算护栏，超限直接拒绝调用

设计要点：
  - `Meter` 挂在 contextvar 上，天然按请求隔离，多租户并发下不会互相污染；
  - LLM 客户端把 API 返回的 usage 回填进当前 Meter（真实计量，而非估算）；
  - usage 缺失时（部分兼容服务不返回）用 `estimate_tokens` 兜底，保证账目不为零；
  - `span()` 以异步上下文管理器形式包裹每个 Agent 调用，记录 耗时/token/成本/状态；
  - 所有 span 落到 state["trace"]，可持久化、可出看板、可做性能回归。

成本护栏 fail-closed 语义：设了上限就一定会拦住，宁可直接报错，
也不允许「静默超支」。这是与「先跑完再统计」截然不同的取向。
"""
from __future__ import annotations

import contextvars
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger

from app.config import BACKEND_DIR, settings

# ── 模型计价表（元/百万 token）────────────────────────────────────────
# 数据来源：各厂商官方价目页（2026-09 核对）。
# 注意 cache_in 价：DeepSeek 命中上下文缓存时输入价低至 1/50，
# 真实账单会明显低于「全按未命中计」，因此成本估算天然偏保守（偏高而非偏低）。
# 注意：price_of 按「子串包含」匹配，因此更具体的键必须排在更宽泛的键之前
# （例如 deepseek-v4-flash 必须先于 deepseek-flash 判断，否则会错配）。
PRICING: Dict[str, Dict[str, float]] = {
    # ── DeepSeek 官方（查证值）──
    "deepseek-v4-flash": {"in": 1.0, "out": 2.0, "cache_in": 0.02},
    "deepseek-v4-pro": {"in": 3.0, "out": 6.0, "cache_in": 0.025},
    "deepseek-flash": {"in": 1.0, "out": 2.0, "cache_in": 0.02},
    # legacy 别名（2026-07-24 起映射到 v4 系列）
    "deepseek-chat": {"in": 1.0, "out": 2.0, "cache_in": 0.02},
    "deepseek-reasoner": {"in": 1.0, "out": 2.0, "cache_in": 0.02},
    # ── 阿里云聚合端点（估算值，真实账单以后台为准）──
    "qwen3.8-flash": {"in": 0.3, "out": 1.2},
    "qwen3.8-max": {"in": 2.4, "out": 9.6},
    "qwen3.8-27b": {"in": 0.4, "out": 1.6},
    "qwen3.7-flash": {"in": 0.3, "out": 1.2},
    "qwen3.7-plus": {"in": 0.8, "out": 2.0},
    "qwen3.7-max": {"in": 2.4, "out": 9.6},
    "kimi-k3": {"in": 2.0, "out": 8.0},
    "kimi-k2.6": {"in": 1.0, "out": 4.0},
    "glm-5.3-flash": {"in": 0.5, "out": 1.5},
    "glm-5.3": {"in": 1.0, "out": 4.0},
    "glm-5.2": {"in": 0.5, "out": 2.0},
    "qwen3-embedding": {"in": 0.05, "out": 0.0},
    # ── 其它 ──
    "qwen-plus": {"in": 0.8, "out": 2.0},
    "qwen-turbo": {"in": 0.3, "out": 0.6},
    "qwen-max": {"in": 2.4, "out": 9.6},
    "moonshot-v1-8k": {"in": 12.0, "out": 12.0},
    "gpt-4o-mini": {"in": 1.1, "out": 4.4},
}
DEFAULT_PRICE = {"in": 1.0, "out": 2.0}
# 计价表里没有的模型，按「取比它贵一档」保守估算，避免低估成本
UNKNOWN_PRICE = {"in": 2.0, "out": 4.0}


def price_of(model: str) -> Dict[str, float]:
    """按模型名查单价；支持前缀匹配（如 deepseek-v4-flash-0913）。"""
    name = (model or "").lower()
    for key, val in PRICING.items():
        if key in name:
            return val
    return UNKNOWN_PRICE if name else DEFAULT_PRICE


def cost_yuan(model: str, prompt_tokens: int, completion_tokens: int,
              cached_tokens: int = 0) -> float:
    """折算人民币成本。cached_tokens 命中缓存价时按缓存单价计。"""
    p = price_of(model)
    cache_price = p.get("cache_in", p["in"])
    fresh = max(0, prompt_tokens - cached_tokens)
    return (fresh * p["in"] + cached_tokens * cache_price
            + completion_tokens * p["out"]) / 1_000_000


def estimate_tokens(text: str) -> int:
    """token 数的保守估算（usage 缺失时兜底）。

    中英混排的经验值：ASCII 约 4 字符/token，CJK 约 1.5 字符/token。
    宁可高估（宁可多记账）也不要漏记。
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return int(cjk / 1.5 + other / 4) + 8


# ── 成本护栏 ─────────────────────────────────────────────────────────
class BudgetExceeded(RuntimeError):
    """LLM 预算超限。必须在调用外部 API **之前**抛出，避免产生无法追回的成本。"""


class SpendLedger:
    """持久化成本流水账（进程内累加 + 原子写盘）。

    为什么需要它：一个 bug 触发的重试风暴，可以在几分钟内把额度跑光；
    「先花后统计」的看板拦不住任何一次调用。这里把护栏放在调用**之前**。
    """

    FLUSH_MIN_INTERVAL = 1.0   # 秒；避免高频小写入打爆磁盘

    def __init__(self, path: Path, cap_yuan: float = 0.0) -> None:
        self.path = path
        self.cap_yuan = max(0.0, cap_yuan)
        self._lock = threading.Lock()
        self._last_flush = 0.0
        self._dirty = False
        self.total = 0.0
        self.by_model: Dict[str, Dict[str, Any]] = {}
        self.entries: List[Dict[str, Any]] = []
        self.denied = 0
        self._load()

    # ── 持久化 ──
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.total = float(data.get("total", 0.0))
            self.by_model = dict(data.get("by_model", {}))
            self.entries = list(data.get("entries", []))
            self.denied = int(data.get("denied", 0))
        except Exception as e:  # noqa: BLE001
            logger.error("成本流水读取失败（将从 0 重新累计，请人工核对）: {}", e)

    def _flush(self, *, force: bool = False) -> None:
        with self._lock:
            if not self._dirty:
                return
            now = time.time()
            if not force and now - self._last_flush < self.FLUSH_MIN_INTERVAL:
                return
            self._last_flush = now
            self._dirty = False
            payload = {
                "total": round(self.total, 6),
                "cap_yuan": self.cap_yuan,
                "by_model": self.by_model,
                "entries": self.entries[-500:],     # 只留最近 500 条明细
                "denied": self.denied,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                               encoding="utf-8")
                os.replace(tmp, self.path)     # 原子替换，避免读到半截文件
            except Exception as e:  # noqa: BLE001
                logger.warning("成本流水落盘失败: {}", e)

    # ── 记账 / 校验 ──
    def remaining(self) -> float:
        if self.cap_yuan <= 0:
            return float("inf")
        return self.cap_yuan - self.total

    def check(self, *, context: str = "") -> None:
        """调用外部 API 之前的硬校验。"""
        if self.cap_yuan > 0 and self.total >= self.cap_yuan:
            self.denied += 1
            self._dirty = True
            self._flush(force=True)
            raise BudgetExceeded(
                f"LLM 成本已达上限 ¥{self.cap_yuan:.2f}（已用 ¥{self.total:.4f}），"
                f"拒绝继续调用。调整 LLM_BUDGET_YUAN 或重置流水后可继续。"
                + (f" [{context}]" if context else "")
            )

    def add(self, model: str, prompt_tokens: int, completion_tokens: int,
            *, cached_tokens: int = 0, note: str = "") -> float:
        cost = cost_yuan(model, prompt_tokens, completion_tokens, cached_tokens)
        with self._lock:
            self.total += cost
            self._dirty = True
            item = self.by_model.setdefault(model or "unknown",
                                            {"calls": 0, "in": 0, "out": 0, "cost": 0.0})
            item["calls"] += 1
            item["in"] += prompt_tokens
            item["out"] += completion_tokens
            item["cost"] = round(item["cost"] + cost, 6)
            if note:
                self.entries.append({
                    "t": time.strftime("%H:%M:%S"), "model": model, "note": note,
                    "in": prompt_tokens, "out": completion_tokens,
                    "cost": round(cost, 6), "total": round(self.total, 6),
                })
        self._flush()
        return cost

    def snapshot(self) -> Dict[str, Any]:
        return {
            "cap_yuan": self.cap_yuan,
            "spent_yuan": round(self.total, 6),
            "remaining_yuan": (None if self.cap_yuan <= 0
                               else round(self.remaining(), 6)),
            "used_pct": (None if self.cap_yuan <= 0
                         else round(self.total / self.cap_yuan * 100, 2)),
            "denied_calls": self.denied,
            "by_model": self.by_model,
            "ledger_file": str(self.path),
        }

    def reset(self) -> None:
        with self._lock:
            self.total = 0.0
            self.by_model = {}
            self.entries = []
            self.denied = 0
            self._dirty = True
        self._flush(force=True)

    def reconfigure(self, cap_yuan: float, path: Optional[Path] = None) -> "SpendLedger":
        """原地重配上限/流水路径。

        刻意**不**创建新对象：`llm.py` 与 `routers/health.py` 在模块级 import 了
        本单例，若此处换成新实例，那些引用会指向旧对象——表现为「设置了上限但
        完全不生效」，是一类极难发现的静默失效。
        """
        with self._lock:
            self.cap_yuan = max(0.0, cap_yuan)
            if path is not None:
                self.path = path
            self._dirty = True
        self._load()
        self._flush(force=True)
        return self


def _ledger_path() -> Path:
    if settings.llm_budget_ledger:
        p = Path(settings.llm_budget_ledger)
        return p if p.is_absolute() else (BACKEND_DIR.parent / p)
    return settings.data_dir / "llm_spend.json"


spend_ledger = SpendLedger(_ledger_path(), cap_yuan=settings.llm_budget_yuan)


def init_budget(cap_yuan: Optional[float] = None, path: Optional[Path] = None) -> SpendLedger:
    """按配置初始化预算护栏（应用启动时调用一次；测试可重复调用）。"""
    cap = settings.llm_budget_yuan if cap_yuan is None else cap_yuan
    spend_ledger.reconfigure(cap, path)
    logger.info("LLM 成本护栏: 上限 ¥{:.2f} / 已用 ¥{:.4f} / 流水 {}",
                cap, spend_ledger.total, spend_ledger.path)
    return spend_ledger


def assert_budget(context: str = "") -> None:
    spend_ledger.check(context=context)


# ── 请求级计量器 ─────────────────────────────────────────────────────
class Meter:
    """请求级计量器：累计 token、成本、调用次数。"""

    def __init__(self) -> None:
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.cost = 0.0
        self.by_model: Dict[str, Dict[str, float]] = {}

    def record(self, model: str, prompt_tokens: int = 0,
               completion_tokens: int = 0, cost: Optional[float] = None,
               cached_tokens: int = 0) -> None:
        self.calls += 1
        self.prompt_tokens += max(0, prompt_tokens)
        self.completion_tokens += max(0, completion_tokens)
        self.cached_tokens += max(0, cached_tokens)
        self.cost += cost if cost is not None else cost_yuan(
            model, prompt_tokens, completion_tokens, cached_tokens)
        item = self.by_model.setdefault(model or "unknown",
                                        {"calls": 0, "in": 0, "out": 0})
        item["calls"] += 1
        item["in"] += prompt_tokens
        item["out"] += completion_tokens

    def snapshot(self) -> Dict[str, Any]:
        return {
            "llm_calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
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


def record_usage(model: str, prompt_tokens: int = 0, completion_tokens: int = 0,
                 cached_tokens: int = 0, note: str = "") -> None:
    """由 LLM 客户端调用：把真实 usage 同时记入「请求计量器」与「全局预算流水」。

    两本账分开是有意的——请求级 Meter 随响应返回给调用方（可解释性），
    全局 SpendLedger 是护栏（不可绕过），后者即使没有请求上下文也必须记账。
    """
    cost = spend_ledger.add(model, prompt_tokens, completion_tokens,
                            cached_tokens=cached_tokens, note=note)
    meter = _meter_ctx.get()
    if meter is not None:
        meter.record(model, prompt_tokens, completion_tokens,
                     cost=cost, cached_tokens=cached_tokens)


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
    # 串行关键路径耗时（span 可能嵌套，这里取最外层之和的近似：仅统计非嵌套顶层）
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
