"""难度状态机：连对升档，连错降档。"""
from __future__ import annotations

from typing import Any, Dict

from app.config import settings

LEVELS = ("easy", "medium", "hard")
ORDER = {lv: i for i, lv in enumerate(LEVELS)}


def update_difficulty(state: Dict[str, Any]) -> None:
    """单题评估后调用。is_correct 来自 last_correctness。"""
    is_correct = bool(state.get("last_correctness"))
    current = str(state.get("current_difficulty", settings.default_difficulty))
    cons_correct = int(state.get("consecutive_correct", 0))
    cons_wrong = int(state.get("consecutive_wrong", 0))

    if is_correct:
        cons_correct += 1
        cons_wrong = 0
    else:
        cons_wrong += 1
        cons_correct = 0

    new_level = current
    idx = ORDER.get(current, 1)
    if cons_correct >= settings.consecutive_to_upgrade and idx < len(LEVELS) - 1:
        new_level = LEVELS[idx + 1]
        cons_correct = 0
    elif cons_wrong >= settings.consecutive_to_downgrade and idx > 0:
        new_level = LEVELS[idx - 1]
        cons_wrong = 0

    state["current_difficulty"] = new_level
    state["consecutive_correct"] = cons_correct
    state["consecutive_wrong"] = cons_wrong
