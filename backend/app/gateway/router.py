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
#
# 降级链的三条设计原则：
#   1. **跨端点**：主备必须落在不同 base_url 上，否则单端点故障时整条链一起挂。
#      DeepSeek V4 在三个端点都有部署（官方直连 / 阿里云聚合 / SiliconFlow），
#      「同模型异端点」是最理想的备选——能力完全不变，只换承载方。
#   2. **先同档再降档**：先试同档位模型，再试弱档位；绝不在中途改变输出格式约定。
#   3. **只用实测可用的模型**：注册表里的 verified=True 项均经 bench/probe_models.py
#      真实调用验证；聚合端点目录里大量未开通的 id 已在 KNOWN_UNACTIVATED 中排除。
TASK_POLICY: Dict[str, RouteSpec] = {
    "jd_parse":       RouteSpec("qwen3.8-27b", ("qwen3.8-flash", "deepseek-flash"),
                                "结构化抽取，小模型足够，三端点冗余"),
    "resume_parse":   RouteSpec("qwen3.8-27b", ("qwen3.8-flash", "deepseek-flash"),
                                "结构化抽取，小模型足够，三端点冗余"),
    "question_plan":  RouteSpec("qwen3.8-flash", ("deepseek-flash", "aliyun/deepseek-v4-flash"),
                                "规划类，中等档位足够"),
    "ask_question":   RouteSpec("deepseek-flash", ("qwen3.8-flash", "aliyun/deepseek-v4-flash"),
                                "需要中文表达质量与低延迟"),
    "followup":       RouteSpec("deepseek-flash", ("qwen3.8-flash", "kimi-k3"),
                                "需要结合上下文追问，备选强档"),
    "score":          RouteSpec("deepseek-flash",
                                ("aliyun/deepseek-v4-flash", "sf/deepseek-v4-flash"),
                                "评分要稳定；备选全是同模型异端点，换承载方不换能力"),
    "report":         RouteSpec("deepseek-v4-pro",
                                ("aliyun/deepseek-v4-pro", "sf/deepseek-v4-pro",
                                 "qwen3.8-max", "kimi-k3"),
                                "长链推理，报告质量敏感；跨三家厂商四层冗余"),
    "study_plan":     RouteSpec("qwen3.8-flash", ("deepseek-flash", "glm-5.2"),
                                "模板化生成，低成本优先"),
    "chat":           RouteSpec("deepseek-flash", ("qwen3.8-flash", "sf/deepseek-v4-flash"),
                                "通用问答，跨端点冗余"),
    "ai_precheck":    RouteSpec("qwen3.8-27b", ("glm-5.2", "qwen3.8-flash"),
                                "极低成本即可，按单价从低到高排序"),
}
_DEFAULT_POLICY = RouteSpec("deepseek-flash", ("qwen3.8-flash", "aliyun/deepseek-v4-flash"),
                            "未登记任务，走默认档位")


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
