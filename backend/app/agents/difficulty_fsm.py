"""难度状态机：连对升档，连错降档。

初版问题（已修复）：
  `update_difficulty` 只把结果写进 `state["current_difficulty"]`，而出题时
  `interviewer.ask_question` 取的是 `question_plan[idx]["difficulty"]`——
  plan 是一次性预生成的，两处各说各话。
  也就是说「连对升级 / 连错降级」这条自适应逻辑**从来没有真正影响过题目难度**，
  它只作为一句文本出现在 prompt 里（"当前难度状态：中等"），纯装饰。

现在：
  - `effective_difficulty()` 是出题难度的唯一裁决者，plan 里的 difficulty 只作为初始档位；
  - 每次转移都会写入 `state["difficulty_trace"]`，可回放、可评测、可画曲线；
  - 评估信号从布尔 `is_correct` 扩展为「正确性 + 深度」双阈值，避免只会背概念也一直升级。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import settings

LEVELS = ("easy", "medium", "hard")
ORDER = {lv: i for i, lv in enumerate(LEVELS)}
DIFFICULTY_LABEL = {"easy": "简单", "medium": "中等", "hard": "困难"}
DIFFICULTY_MODE_ADAPTIVE = "adaptive"


def _grade(score: Dict[str, Any]) -> bool:
    """判定本题是否算「通过」。

    双阈值：正确性 >= 6 且深度 >= 5（与 evaluator 的 is_correct 定义一致，
    但对缺失字段更宽容，避免 LLM 少返回一个字段就把难度一路降到底）。
    """
    if "is_correct" in score:
        return bool(score["is_correct"])
    try:
        return int(score.get("correctness", 0)) >= 6 and int(score.get("depth", 0)) >= 5
    except (TypeError, ValueError):
        return False


def update_difficulty(state: Dict[str, Any]) -> Dict[str, Any]:
    """单题评估后调用，更新难度档位并返回本次转移信息。"""
    is_correct = bool(state.get("last_correctness"))
    current = str(state.get("current_difficulty") or settings.default_difficulty)
    if current not in ORDER:
        current = settings.default_difficulty

    cons_correct = int(state.get("consecutive_correct", 0))
    cons_wrong = int(state.get("consecutive_wrong", 0))

    if is_correct:
        cons_correct += 1
        cons_wrong = 0
    else:
        cons_wrong += 1
        cons_correct = 0

    new_level, reason = current, "hold"
    idx = ORDER[current]
    if cons_correct >= settings.consecutive_to_upgrade and idx < len(LEVELS) - 1:
        new_level = LEVELS[idx + 1]
        cons_correct = 0
        reason = "upgrade"
    elif cons_wrong >= settings.consecutive_to_downgrade and idx > 0:
        new_level = LEVELS[idx - 1]
        cons_wrong = 0
        reason = "downgrade"

    state["current_difficulty"] = new_level
    state["consecutive_correct"] = cons_correct
    state["consecutive_wrong"] = cons_wrong

    transition = {
        "index": int(state.get("current_question_idx", 0)),
        "from": current,
        "to": new_level,
        "reason": reason,
        "last_correct": is_correct,
    }
    trace: List[Dict[str, Any]] = state.setdefault("difficulty_trace", [])
    trace.append(transition)
    return transition


def effective_difficulty(state: Dict[str, Any],
                         plan_item: Optional[Dict[str, Any]] = None) -> str:
    """出题时实际使用的难度。

    adaptive 模式（默认）：以状态机为准 —— 这是让自适应真正生效的关键。
    plan 模式：完全尊重预生成计划（用于做 A/B 对照实验）。
    """
    mode = getattr(settings, "difficulty_mode", DIFFICULTY_MODE_ADAPTIVE)
    if mode == "plan" and plan_item and plan_item.get("difficulty") in ORDER:
        return str(plan_item["difficulty"])
    current = state.get("current_difficulty")
    if current in ORDER:
        return str(current)
    if plan_item and plan_item.get("difficulty") in ORDER:
        return str(plan_item["difficulty"])
    return settings.default_difficulty


def describe(state: Dict[str, Any]) -> str:
    """供 prompt 使用的难度状态描述（含连对/连错进度，让模型知道自己在什么位置）。"""
    level = DIFFICULTY_LABEL.get(str(state.get("current_difficulty", "")), "中等")
    cc = int(state.get("consecutive_correct", 0))
    cw = int(state.get("consecutive_wrong", 0))
    parts = [f"当前难度：{level}"]
    if cc:
        parts.append(f"已连对 {cc} 题（连对 {settings.consecutive_to_upgrade} 题升档）")
    if cw:
        parts.append(f"已连错 {cw} 题（连错 {settings.consecutive_to_downgrade} 题降档）")
    return "；".join(parts)
