"""
统一 LLM 客户端（OpenAI 兼容）。

Key 策略：纯服务端托管（`settings.llm_api_key` + `settings.provider_key()`）。
业务侧不接收、不落库用户自有 Key；用户购买积分后由平台代为调用。
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import random
import re
import time
from collections import OrderedDict
from typing import Any, AsyncGenerator, Dict, List, NamedTuple, Optional

from loguru import logger

from app.config import settings
from app.observability import (BudgetExceeded, assert_budget, estimate_tokens,
                               record_usage, spend_ledger)

# 请求级模型选择：由网关路由（app/gateway）按任务写入；空 = 用全局默认
llm_model_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("llm_model_ctx", default="")
# 请求级「用户偏好模型」：来自 X-LLM-Model 头，作为路由的 prefer 输入。
# 必须与 llm_model_ctx 分开：否则路由写入的实际模型会被下一轮当成用户偏好，
# 导致一次请求里所有任务都退化成同一个模型（任务级路由失效）。
llm_prefer_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("llm_prefer_ctx", default="")

_NO_KEY_ERROR = (
    "服务端未配置 LLM API Key：请在部署环境配置 settings.llm_api_key"
    " 或 settings.llm_provider_keys（按 provider 取对应 Key）"
)


def set_llm_model_context(model_id: Optional[str]) -> None:
    """设置当前请求的**用户偏好模型**（由依赖层从 X-LLM-Model 头调用）。"""
    llm_prefer_ctx.set((model_id or "").strip())


class LLMError(Exception):
    def __init__(self, message: str = "LLM 调用失败") -> None:
        super().__init__(message)
        self.message = message


# ── 重试策略：只重试「值得重试」的错误 + 带 jitter 的退避 ──────────────
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def is_retryable(exc: Exception) -> bool:
    """4xx 中只有 429/408 等值得重试；其余（401/403/404/400）立即失败。"""
    status = getattr(exc, "status_code", None)
    if status is None:
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
    if isinstance(status, int):
        return status in _RETRYABLE_STATUS
    # 网络类/超时类错误（无状态码）→ 可重试
    name = type(exc).__name__.lower()
    return any(k in name for k in ("timeout", "connect", "network", "read", "protocol", "unavailable"))


def retry_delay(attempt: int, exc: Exception, *, base: float = 0.5, cap: float = 6.0) -> float:
    """Full-jitter 退避；若响应带 Retry-After 则优先遵循（并封顶）。

    交互式场景必须封顶：用户正在等待，60s 的重试等价于停机。
    """
    retry_after = None
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if headers:
        try:
            retry_after = float(headers.get("retry-after"))
        except (TypeError, ValueError):
            retry_after = None
    ceiling = min(cap, base * (2 ** attempt))
    if retry_after is not None:
        ceiling = min(max(retry_after, 0.1), cap)
    return random.uniform(0.05, ceiling) if ceiling > 0.05 else 0.05


def usage_of(usage: Any) -> tuple:
    """从各家不同结构的 usage 中取出 (prompt_tokens, completion_tokens, cached_tokens)。

    OpenAI / DeepSeek(chat.completions)：prompt_tokens / completion_tokens，
      缓存命中数在 prompt_tokens_details.cached_tokens 或 prompt_cache_hit_tokens；
    Responses API / Anthropic 风格：input_tokens / output_tokens。
    缺 usage 时返回全 0，由调用方用 estimate_tokens 兜底，避免账目凭空少记。
    """
    if usage is None:
        return 0, 0, 0
    pt = int(getattr(usage, "prompt_tokens", None)
             or getattr(usage, "input_tokens", 0) or 0)
    ct = int(getattr(usage, "completion_tokens", None)
             or getattr(usage, "output_tokens", 0) or 0)
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = int(getattr(details, "cached_tokens", 0) or 0)
    if not cached:
        cached = int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0)
    return pt, ct, cached


class Target(NamedTuple):
    """一次 LLM 调用的完整目标描述。"""

    model_name: str          # 发给服务商的真实模型名
    base_url: str
    style: str               # chat | responses
    provider: str            # 决定用哪把服务端凭据
    route_id: str = ""       # 对外路由 id（注册表 id）
    supports_thinking: bool = False
    context_window: int = 0

    def __str__(self) -> str:
        return f"{self.route_id or self.model_name}@{self.provider}"


class MockLLM:
    """确定性 mock，根据 prompt 中的关键子串返回结构化内容。"""
    @staticmethod
    def is_available() -> bool:
        return bool(settings.llm_api_key)

    @staticmethod
    def chat(system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        # 优先按 user_prompt 路由（各 Agent 调用时传入的内容不同，最可靠）
        up = (user_prompt or "").strip()
        if up in ("请评分", "请出题", "请追问", "请点评", "请生成报告", "请收尾", "开始面试"):
            return MockLLM._route_by_user_prompt(up)
        if up == "请评分":
            return MockLLM._score_json()
        return MockLLM._route_by_system(system_prompt, user_prompt)

    @staticmethod
    def _route_by_user_prompt(up: str) -> str:
        if up == "请评分":
            return MockLLM._score_json()
        if up == "请出题":
            return json.dumps({"question": "请简述 RAG 的混合检索是如何工作的？", "is_followup": False})
        if up == "请追问":
            return json.dumps({"question": "那两路结果的分数是怎么融合的？", "is_followup": True})
        if up == "请点评":
            return json.dumps({"comment": "回答思路清晰，可补充具体实例"})
        if up == "请收尾":
            return json.dumps({"farewell": "感谢参与，整体表现不错，继续加油！"})
        if up == "请生成报告":
            return MockLLM._report_json()
        return json.dumps({"ok": True, "message": "mock 响应"})

    @staticmethod
    def _score_json() -> str:
        return json.dumps({
            "correctness": 7, "depth": 6, "structure": 8, "example": 6,
            "is_correct": True, "key_missing": ["没有提到 RRF 融合权重"],
            "followup_needed": False, "followup_reason": "",
            "score": 7, "feedback": "基本正确",
            "correct_points": ["核心思路对"], "missing_points": ["细节不足"],
        })

    @staticmethod
    def _report_json() -> str:
        return json.dumps({
            "overall_score": 78,
            "recommendation": "hire",
            "dimension_scores": {
                "technical_knowledge": 8, "problem_solving": 7, "system_design": 7,
                "communication": 8, "practical_experience": 8, "learning_ability": 7,
            },
            "strengths": ["RAG 理解扎实"],
            "weaknesses": ["分布式知识欠缺"],
            "highlights": [{"round": 1, "reason": "能讲清 RRF 融合"}],
            "concerns": [],
            "topic_performance": [
                {"topic": "RAG", "performance": "good", "comment": "理解深入"},
                {"topic": "Agent", "performance": "average", "comment": "基本掌握"},
            ],
            "summary": "整体表现良好，RAG 方向扎实，分布式方向需加强",
            "interviewer_comment": "建议重点复习分布式一致性",
        })

    @staticmethod
    def _route_by_system(system_prompt: str, user_prompt: str) -> str:
        # 路由
        if "意图" in system_prompt or "intent" in system_prompt.lower():
            return json.dumps({"intent": "start_interview", "confidence": 0.95, "skill": None})
        if "岗位" in system_prompt and "解析" in system_prompt:
            return json.dumps({
                "title": "AI Agent 工程师",
                "level": "senior",
                "years_of_experience": 3,
                "tech_stack": ["Python", "RAG", "LangChain", "MCP"],
                "nice_to_have": ["分布式系统"],
                "core_competencies": ["系统设计", "Agent 工程化", "RAG"],
                "industry": "AI",
                "key_responsibilities": ["Agent 架构设计", "RAG 落地"],
                "summary": "负责大模型 Agent 系统架构设计与落地",
            })
        if "简历" in system_prompt and ("匹配" in system_prompt or "画像" in system_prompt):
            return json.dumps({
                "overall_score": 82,
                "match_level": "high",
                "strengths": ["RAG 项目经验丰富", "工程落地能力强"],
                "weaknesses": ["分布式经验不足", "Agent 框架源码深度不够"],
                "tech_match": {"Python": {"matched": True, "evidence": "5 年 Python"}},
                "experience_fit": "fit",
                "highlights": ["主导过生产级 RAG 系统"],
                "red_flags": [],
                "summary": "与岗位高度匹配",
            })
        if "规划" in system_prompt and "题目" in system_prompt:
            return json.dumps({"plan": [
                {"topic": "RAG", "question_type": "concept", "difficulty": "medium",
                 "focus": "检索链路", "prompt": "请解释混合检索的召回与重排流程"},
                {"topic": "Agent", "question_type": "concept", "difficulty": "easy",
                 "focus": "Agent 与 LLM 区别", "prompt": "Agent 和普通 LLM 应用的区别是什么？"},
                {"topic": "MCP", "question_type": "concept", "difficulty": "medium",
                 "focus": "协议设计", "prompt": "MCP 协议解决了什么问题？"},
            ]})
        if "出题" in system_prompt or "面试官" in system_prompt:
            return json.dumps({"question": "请简述 RAG 的混合检索是如何工作的？", "is_followup": False})
        if "复习计划" in system_prompt or "学习计划" in system_prompt:
            return json.dumps({
                "overall_advice": "重点补强分布式知识",
                "weeks": [
                    {"week": 1, "theme": "RAG 进阶", "goals": ["重排算法"], "daily_hours": 2, "resources": ["技术博客"]},
                    {"week": 2, "theme": "Agent 框架", "goals": ["LangGraph 源码"], "daily_hours": 2, "resources": ["官方文档"]},
                    {"week": 3, "theme": "分布式", "goals": ["一致性协议"], "daily_hours": 3, "resources": ["DDIA"]},
                    {"week": 4, "theme": "综合模拟", "goals": ["每日一套题"], "daily_hours": 2, "resources": ["题库"]},
                ],
                "practice_projects": ["构建一个多 Agent RAG 系统"],
                "mock_interview_tips": ["用 STAR 法则组织项目回答"],
            })
        if "知识库内容审核员" in system_prompt:
            return json.dumps({
                "is_tech_related": True, "has_harmful_content": False,
                "is_duplicate_likely": False, "approve_score": 85,
                "recommended_category": "面经", "reason": "内容为技术面试相关知识，可收录",
            })
        if "闲聊" in system_prompt or "chat" in system_prompt.lower():
            return "好的，有什么我可以帮你的？"
        # 兜底：若 prompt 明确要求 JSON 输出，则返回一个空 JSON
        if "JSON" in system_prompt or "json" in system_prompt:
            return json.dumps({"ok": True, "message": "mock 响应"})
        # 兜底：回显
        return user_prompt[:200]

    @staticmethod
    async def chat_stream(system_prompt: str, user_prompt: str, **kwargs: Any) -> AsyncGenerator[str, None]:
        text = MockLLM.chat(system_prompt, user_prompt, **kwargs)
        for i in range(0, len(text), 10):
            yield text[i:i + 10]
            await asyncio.sleep(0.01)


class UnifiedLLMClient:
    """统一 LLM 客户端：服务端托管 key + 多 provider 路由 + mock 回退。

    支持两种调用模式（由 LLM_RESPONSES_MODE 切换）：
    - chat.completions（默认）：OpenAI 兼容，DeepSeek 的 deepseek-flash
    - responses：DeepSeek Responses API，deepseek-v4-flash

    凭据模型：业务侧**不接收用户自带 key**；Key 由服务端 settings 持有，
    按 provider 分别取（见 app.config.Settings.provider_key）。
    """

    def __init__(self) -> None:
        # 按 (api_key, base_url) 分池缓存客户端：修掉「单槽缓存 + 多 provider 路由」
        # 导致的客户端串号。每个 provider 独立一个 AsyncOpenAI 实例，连接可复用。
        self._pool: "OrderedDict[str, Any]" = OrderedDict()
        self._pool_lock = asyncio.Lock()
        self._pool_max = 64
        self._max_retries = 3

    @property
    def enabled(self) -> bool:
        """当前目标模型所属 provider 是否有可用服务端 key。"""
        return bool(self._key_for_provider(self.resolve().provider))

    def _key_for_provider(self, provider: str) -> str:
        """按 provider 取凭据。

        关键设计：**凭据必须按 provider 解析**。
        若所有 provider 共用一把服务端 key，模型路由一旦切到另一家，
        请求就会因为 401 失败——降级链形同虚设，而且失败恰好发生在最需要它的时刻。
        """
        return settings.provider_key(provider)

    def _key_for(self, model_id: str) -> str:
        """按对外模型 id 取凭据（内部解析其 provider）。"""
        from app.gateway.registry import provider_of
        return self._key_for_provider(provider_of(model_id))

    def _effective_key(self) -> str:
        """兼容旧调用：等价于「按当前目标模型取 key」。"""
        return self._key_for(self.target()[0])

    @staticmethod
    def _pool_key(api_key: str, base_url: str) -> str:
        """池键：只存哈希，避免在字典键上明文持有用户密钥。"""
        return hashlib.sha256(f"{api_key}|{base_url}".encode()).hexdigest()

    def _acquire(self, api_key: str, base_url: str) -> Any:
        """从池中取（或创建）指定 key 的客户端。LRU 淘汰，避免密钥无限累积。"""
        pk = self._pool_key(api_key, base_url)
        client = self._pool.get(pk)
        if client is not None:
            self._pool.move_to_end(pk)
            return client
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=settings.llm_timeout,
            max_retries=0,  # 重试由本模块统一控制（带 jitter）
        )
        self._pool[pk] = client
        if len(self._pool) > self._pool_max:
            self._pool.popitem(last=False)
        return client

    def _get_client(self) -> Any:
        """chat.completions 模式客户端（按目标模型所属 provider 取凭据与接入点）。"""
        t = self.resolve()
        return self._acquire(self._key_for_provider(t.provider), t.base_url)

    def _get_responses_client(self) -> Any:
        """Responses API 模式客户端（同上）。"""
        t = self.resolve()
        return self._acquire(self._key_for_provider(t.provider), t.base_url)

    def resolve(self) -> "Target":
        """当前请求的完整调用目标。

        拆成独立方法（而不是改 target() 的返回结构）是为了不波及既有调用点：
        target() 仍返回三元组，需要 provider / 思考能力的路径用 resolve()。
        """
        from app.gateway.registry import get_model
        spec = get_model(llm_model_ctx.get())
        if spec is not None:
            return Target(model_name=spec.model_name, base_url=spec.base_url,
                          style=spec.api_style, provider=spec.provider,
                          route_id=spec.id, supports_thinking=spec.supports_thinking,
                          context_window=spec.context_window)
        if settings.llm_responses_mode:
            return Target(model_name=settings.llm_responses_model,
                          base_url=settings.llm_responses_base_url, style="responses",
                          provider=settings.llm_default_provider,
                          route_id=settings.llm_responses_model)
        return Target(model_name=settings.llm_model, base_url=settings.llm_base_url,
                      style="chat", provider=settings.llm_default_provider,
                      route_id=settings.llm_model)

    def target(self) -> "tuple[str, str, str]":
        """当前请求的目标 (model_id, base_url, api_style)。

        优先级：请求级模型（网关路由 / 用户模型设置）> 全局配置。
        没有它，多模型只是「配置项」；有了它，同一次面试里不同环节
        才能真正使用不同档位的模型。
        """
        from app.gateway.registry import get_model
        spec = get_model(llm_model_ctx.get())
        if spec is not None:
            return spec.id, spec.base_url, spec.api_style
        if settings.llm_responses_mode:
            return settings.llm_responses_model, settings.llm_responses_base_url, "responses"
        return settings.llm_model, settings.llm_base_url, "chat"

    @property
    def _mode_label(self) -> str:
        try:
            return self.target()[2]
        except Exception:  # noqa: BLE001
            return "responses" if settings.llm_responses_mode else "chat.completions"

    def stats(self) -> Dict[str, object]:
        """运行时可观测指标：多 provider key 池规模、服务端 key 状态、调用模式。"""
        model_id, base_url, style = self.target()
        return {
            "mode": style,
            "target_model": model_id,
            "target_base_url": base_url,
            "pool_size": len(self._pool),
            "pool_max": self._pool_max,
            "server_key": bool(settings.llm_api_key),
            "max_retries": self._max_retries,
            "timeout_s": settings.llm_timeout,
            "budget": spend_ledger.snapshot(),
        }

    def _thinking_kwargs(self, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """思考模式控制参数。

        DeepSeek V4 系列默认开启「思考模式」：先输出思维链，再给正文。
        实测数据（bench/model_availability.md）：

        | 配置 | 正文 | 思维链 | 正文首字 |
        |---|---|---|---|
        | 关闭思考 + 256 token | 69 字 | 0 字 | 783 ms |
        | 默认思考 + 64 token | **0 字** | 145 字 | 无 |
        | 默认思考 + 768 token | 58 字 | 211 字 | 988 ms |

        结论：不显式关闭思考，「小 max_tokens 的调用会静默返回空正文」——
        接口 200、无异常、内容为空，属于最难排查的一类线上故障。
        因此默认关闭；并且当 max_tokens 低于阈值时**无论如何都关闭**
        （预算必然被思维链吃掉）。
        """
        t = self.resolve()
        if not t.supports_thinking:
            return {}
        limit = max_tokens or settings.llm_max_tokens
        if settings.llm_thinking_mode == "disabled" or limit < settings.llm_thinking_min_tokens:
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        return {}

    async def probe(self) -> Dict[str, Any]:
        """真实探活一次（会消耗极少量额度），用于上线自检与评测取证。"""
        model_id, base_url, style = self.target()
        if not self.enabled:
            return {"ok": False, "mode": style, "model": model_id,
                    "base_url": base_url,
                    "error": _NO_KEY_ERROR if not settings.test_mode else "test_mode 下走 mock"}
        t0 = time.perf_counter()
        try:
            text = await self.chat("你是连通性探针。", "只回复两个字：正常",
                                  temperature=0.0, max_tokens=16)
            return {"ok": True, "mode": style, "model": model_id, "base_url": base_url,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "reply": (text or "")[:40]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "mode": style, "model": model_id, "base_url": base_url,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "error": f"{type(e).__name__}: {e}"}

    async def chat(self, system_prompt: str, user_prompt: str,
                   *, temperature: Optional[float] = None,
                   max_tokens: Optional[int] = None) -> str:
        # 测试模式（仅 pytest）：未配 key 时用确定性 mock
        if not self.enabled:
            if settings.test_mode:
                return MockLLM.chat(system_prompt, user_prompt)
            # 生产/本地：无 key 一律报错，引导用户配置（不降级 mock）
            raise LLMError(_NO_KEY_ERROR)
        temperature = temperature if temperature is not None else settings.llm_temperature
        model_id, _base_url, style = self.target()
        last_err: Optional[Exception] = None
        for attempt in range(self._max_retries):
            # 成本护栏放在 try 之外：预算超限必须直接抛出，
            # 不能被下面的 except Exception 当成「可重试错误」反复重试刷钱。
            assert_budget(f"llm.chat:{model_id}")
            try:
                if style == "responses":
                    resp = await self._get_responses_client().responses.create(
                        model=model_id,
                        instructions=system_prompt,
                        input=user_prompt,
                        temperature=temperature,
                        max_output_tokens=max_tokens or settings.llm_max_tokens,
                    )
                    pt, ct, cached = usage_of(getattr(resp, "usage", None))
                    if not (pt or ct):
                        # 服务商未回传 usage：用文本长度兜底，保证成本账目不为零
                        pt = estimate_tokens(system_prompt + user_prompt)
                        ct = estimate_tokens(getattr(resp, "output_text", "") or "")
                    record_usage(model_id, pt, ct, cached_tokens=cached, note="chat:responses")
                    return getattr(resp, "output_text", "") or ""
                resp = await self._get_client().chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens or settings.llm_max_tokens,
                    **self._thinking_kwargs(max_tokens),
                )
                msg = resp.choices[0].message
                content = msg.content or ""
                reasoning = getattr(msg, "reasoning_content", "") or ""
                pt, ct, cached = usage_of(getattr(resp, "usage", None))
                if not (pt or ct):
                    pt = estimate_tokens(system_prompt + user_prompt)
                    ct = estimate_tokens(content)
                record_usage(model_id, pt, ct, cached_tokens=cached, note="chat:completions")

                if not content.strip() and reasoning:
                    # 「思考模式吃满输出预算」的典型症状：有思维链、没正文。
                    # 若当前是 auto 模式，先就地关掉思考重试一次；仍为空则报错，
                    # 交由上层降级链换模型——绝不能把空字符串当成正常结果返回。
                    if settings.llm_thinking_mode != "disabled":
                        logger.warning("模型 {} 正文为空（思维链 {} 字），关闭思考重试一次",
                                       model_id, len(reasoning))
                        resp = await self._get_client().chat.completions.create(
                            model=model_id,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            temperature=temperature,
                            max_tokens=max_tokens or settings.llm_max_tokens,
                            extra_body={"thinking": {"type": "disabled"}},
                        )
                        msg = resp.choices[0].message
                        content = msg.content or ""
                        pt2, ct2, cached2 = usage_of(getattr(resp, "usage", None))
                        record_usage(model_id, pt2, ct2, cached_tokens=cached2,
                                     note="chat:retry-no-thinking")
                    if not content.strip():
                        raise LLMError(
                            f"模型 {model_id} 仅返回思维链（{len(reasoning)} 字）而正文为空："
                            "思考模式占满了输出预算，且关闭思考后仍未产出正文")
                return content
            except Exception as e:  # noqa: BLE001
                last_err = e
                if not is_retryable(e) or attempt == self._max_retries - 1:
                    break
                delay = retry_delay(attempt, e)
                logger.warning("LLM chat 第 {} 次失败，{:.2f}s 后重试: {}",
                               attempt + 1, delay, type(e).__name__)
                await asyncio.sleep(delay)
        logger.error("LLM {} chat 失败（重试 {} 次）: {}", self._mode_label, self._max_retries, last_err)
        raise LLMError(str(last_err))

    async def chat_stream(self, system_prompt: str, user_prompt: str,
                          *, temperature: Optional[float] = None,
                          max_tokens: Optional[int] = None) -> AsyncGenerator[str, None]:
        """流式返回文本增量。"""
        # 测试模式（仅 pytest）：未配 key 时用确定性 mock
        if not self.enabled:
            if settings.test_mode:
                async for chunk in MockLLM.chat_stream(system_prompt, user_prompt):
                    yield chunk
                return
            raise LLMError(_NO_KEY_ERROR)
        temperature = temperature if temperature is not None else settings.llm_temperature
        model_id, _base_url, style = self.target()
        assert_budget(f"llm.chat_stream:{model_id}")
        try:
            if style == "responses":
                stream = await self._get_responses_client().responses.create(
                    model=model_id,
                    instructions=system_prompt,
                    input=user_prompt,
                    temperature=temperature,
                    max_output_tokens=max_tokens or settings.llm_max_tokens,
                    stream=True,
                )
                async for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            yield delta
                    elif etype == "response.completed":
                        pt, ct, cached = usage_of(
                            getattr(getattr(event, "response", None), "usage", None))
                        if pt or ct:
                            record_usage(model_id, pt, ct, cached_tokens=cached,
                                         note="stream:responses")
                return
            create_kwargs = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens or settings.llm_max_tokens,
                "stream": True,
                # 流式下更要显式关闭思考：否则思维链会先占用输出预算，
                # 小 max_tokens 场景正文一个字都吐不出来（实测必现）
                **self._thinking_kwargs(max_tokens),
            }
            try:
                # 让服务端在末帧回传 usage，流式调用也能被真实计量
                stream = await self._get_client().chat.completions.create(
                    **create_kwargs, stream_options={"include_usage": True})
            except Exception:  # noqa: BLE001
                # 部分 OpenAI 兼容服务不支持 stream_options，降级为不带 usage 的流式
                stream = await self._get_client().chat.completions.create(**create_kwargs)

            last_usage = None
            content_chars = 0
            reasoning_chars = 0
            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    last_usage = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                # 思维链与正文是不同字段。只读 content 会丢弃 reasoning_content，
                # 于是在思考模式下表现为「接口正常但一个字都不返回」。
                reasoning = getattr(delta, "reasoning_content", None) or ""
                reasoning_chars += len(reasoning)
                piece = delta.content
                if piece:
                    content_chars += len(piece)
                    yield piece
            if content_chars == 0 and reasoning_chars > 0:
                # 已经什么都没产出，此时抛错是安全的（不会造成前端内容截断）
                raise LLMError(
                    f"模型 {model_id} 流式调用仅产出思维链（{reasoning_chars} 字）而正文为空："
                    "思考模式占满输出预算")
            if last_usage is not None:
                pt, ct, cached = usage_of(last_usage)
                if pt or ct:
                    record_usage(model_id, pt, ct, cached_tokens=cached,
                                 note="stream:completions")
            else:
                # 流式未回传 usage（部分兼容服务不支持 stream_options）：
                # 用提示词长度兜底，避免「流式调用全部不记账」的漏洞
                record_usage(model_id, estimate_tokens(system_prompt + user_prompt), 0,
                             note="stream:completions:estimated")
        except Exception as e:  # noqa: BLE001
            logger.error("LLM {} 流式调用失败: {}", self._mode_label, e)
            raise LLMError(str(e))

    async def chat_with_json(self, system_prompt: str, user_prompt: str,
                             *, temperature: Optional[float] = None) -> Dict[str, Any]:
        """调用 LLM 并解析 JSON；解析失败返回 {}。"""
        temperature = temperature if temperature is not None else settings.llm_json_temperature
        text = await self.chat(system_prompt, user_prompt, temperature=temperature)
        return parse_json_response(text)

    async def test_connection(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """兼容旧 API：忽略传入的 api_key（业务侧已不接收 BYOK），走服务端托管 key。"""
        return await self.probe()
        """测试 LLM 连通性。api_key 可选：测试指定 key（前端模型设置用）。"""
        key = api_key or self._effective_key()
        if not key:
            return {"ok": False, "model": "mock", "error": "未配置 API Key"}
        try:
            if settings.llm_responses_mode:
                from openai import AsyncOpenAI
                c = AsyncOpenAI(api_key=key, base_url=settings.llm_responses_base_url, timeout=30.0)
                resp = await c.responses.create(
                    model=settings.llm_responses_model,
                    input="ping",
                    max_output_tokens=5,
                )
                text = getattr(resp, "output_text", "") or ""
                return {"ok": True, "model": settings.llm_responses_model, "response": text[:50]}
            from openai import AsyncOpenAI
            c = AsyncOpenAI(api_key=key, base_url=settings.llm_base_url, timeout=30.0)
            resp = await c.chat.completions.create(
                model=settings.llm_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return {"ok": True, "model": settings.llm_model, "response": (resp.choices[0].message.content or "")[:50]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "model": settings.llm_responses_model if settings.llm_responses_mode else settings.llm_model, "error": str(e)}


def parse_json_response(text: str) -> Dict[str, Any]:
    """解析 LLM 返回的 JSON（容忍 markdown 围栏与多余文字）。失败返回 {}。"""
    if not text:
        return {}
    text = text.strip()
    # 去掉 ```json ... ``` 围栏
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 提取第一个 {...} 或 [...] 块
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start != -1:
            end = text.rfind(closer)
            if end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
    return {}


llm_client = UnifiedLLMClient()
