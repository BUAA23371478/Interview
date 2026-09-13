"""任务级模型路由 + 降级链。

核心思想：**按任务语义选模型，而不是全局一个模型。**

一次面试里各类任务的成本/能力诉求并不相同：

| 任务 | 特征 | 模型档位 |
|---|---|---|
| JD/简历解析、题目规划 | 结构化抽取，可容忍小模型 | cheap/standard |
| 出题、追问 | 需要中文表达质量 | standard |
| 评分、复盘报告 | 需要长链推理与一致性 | strong |
| 自由问答 | 通用 | standard |

如果全流程都挂最强模型，token 成本会成倍上升而收益集中在少数环节。
路由层把「贵模型」精准投到推理密集环节，其余走性价比模型 —— 这是可量化的成本优化。

降级链（fallback）
------------------
主模型失败（限流/超时/不可用）时按序尝试备用模型，全部失败才抛错。
这样单个 provider 抖动不会让整个面试中断，属于「兜底机制」的第一层。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from loguru import logger

from app.gateway.registry import ModelSpec, get_model


@dataclass(frozen=True)
class RouteSpec:
    primary: str
    fallbacks: Tuple[str, ...] = ()
    reason: str = ""


# 任务 → 路由策略（单一事实来源，便于 A/B 与成本复盘）
TASK_POLICY: Dict[str, RouteSpec] = {
    "jd_parse":       RouteSpec("deepseek-chat", ("qwen-turbo",), "结构化抽取，无需强模型"),
    "resume_parse":   RouteSpec("deepseek-chat", ("qwen-turbo",), "结构化抽取，无需强模型"),
    "question_plan":  RouteSpec("deepseek-chat", ("qwen-plus",), "规划类，中等档位足够"),
    "ask_question":   RouteSpec("deepseek-chat", ("qwen-plus",), "需要中文表达质量"),
    "followup":       RouteSpec("deepseek-chat", ("qwen-plus",), "需要结合上下文追问"),
    "score":          RouteSpec("deepseek-chat", ("qwen-plus",), "评分要稳定，窄任务"),
    "report":         RouteSpec("deepseek-reasoner", ("deepseek-chat",), "长链推理，报告质量敏感"),
    "study_plan":     RouteSpec("deepseek-chat", ("qwen-plus",), "模板化生成"),
    "chat":           RouteSpec("deepseek-chat", ("qwen-plus",), "通用问答"),
    "ai_precheck":    RouteSpec("qwen-turbo", ("deepseek-chat",), "极低成本即可"),
}
_DEFAULT_POLICY = RouteSpec("deepseek-chat", ("qwen-plus",), "未登记任务，走默认档位")


@dataclass
class RoutePlan:
    """一次路由决策的完整记录（可入账、可解释）。"""

    task: str
    chain: List[ModelSpec] = field(default_factory=list)
    reason: str = ""
    overridden: bool = False

    @property
    def primary(self) -> Optional[ModelSpec]:
        return self.chain[0] if self.chain else None

    def describe(self) -> Dict[str, object]:
        return {
            "task": self.task,
            "model_chain": [m.id for m in self.chain],
            "reason": self.reason,
            "overridden": self.overridden,
        }


def route(task: str, *, prefer: Optional[str] = None) -> RoutePlan:
    """为某类任务生成模型调用链。

    prefer: 用户显式指定的模型（来自模型设置），优先于任务策略；
            若该模型不在注册表中则忽略并回落策略（避免用户填错就整场不可用）。
    """
    policy = TASK_POLICY.get(task, _DEFAULT_POLICY)
    chain: List[ModelSpec] = []
    overridden = False

    if prefer:
        spec = get_model(prefer)
        if spec is not None:
            chain.append(spec)
            overridden = True
        else:
            logger.warning("用户指定模型 {} 未在注册表中，回落任务策略 {}", prefer, policy.primary)

    for mid in (policy.primary, *policy.fallbacks):
        spec = get_model(mid)
        if spec is not None and spec not in chain:
            chain.append(spec)

    return RoutePlan(task=task, chain=chain,
                     reason=policy.reason + ("（用户覆盖）" if overridden else ""),
                     overridden=overridden)


def fallback_chain(task: str) -> List[str]:
    return [m.id for m in route(task).chain]


def current_prefer() -> str:
    """当前请求用户指定的偏好模型（X-LLM-Model 头），空 = 由任务策略决定。"""
    from app.llm import llm_prefer_ctx
    return llm_prefer_ctx.get() or ""
