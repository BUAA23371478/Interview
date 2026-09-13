"""意图路由 Agent：识别用户输入意图。"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base_agent import BaseAgent

INTENT_TYPES = ["start_interview", "answer_question", "input_jd", "use_skill", "chat"]


class IntentRouter(BaseAgent):
    name = "intent_router"
    task = "chat"
    name = "intent_router"
    description = "意图识别与路由分发"

    SYSTEM_PROMPT = """你是意图分类器。判断用户输入的意图，输出严格 JSON：
{"intent": "<类别>", "confidence": 0.0~1.0, "skill": null}

类别只允许以下之一：
- start_interview: 用户要开始模拟面试/面试
- answer_question: 用户在回答面试题/提供答案
- input_jd: 用户提供岗位描述 JD
- use_skill: 用户要用专项技能（练习/讲解/对比）
- chat: 其他闲聊

请以 JSON 输出，不要多余文字。"""

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_input = (state.get("user_input") or "").strip()
        if not user_input:
            state["intent"] = "chat"
            state["intent_confidence"] = 0.9
            return state

        # 快捷命令短路（省 token）
        if user_input.startswith("/interview"):
            state["intent"] = "start_interview"
            state["intent_confidence"] = 1.0
            return state
        if user_input.startswith("/skill"):
            state["intent"] = "use_skill"
            state["intent_confidence"] = 1.0
            return state
        if user_input.startswith("/jd"):
            state["intent"] = "input_jd"
            state["jd_text"] = user_input[3:].strip() or state.get("jd_text", "")
            state["intent_confidence"] = 1.0
            return state

        parsed = await self.invoke_llm_json(self.SYSTEM_PROMPT, user_input)
        intent = parsed.get("intent")
        if intent not in INTENT_TYPES:
            intent = "chat"
        state["intent"] = intent
        state["intent_confidence"] = float(parsed.get("confidence", 0.5))
        skill = parsed.get("skill")
        if skill:
            state["skill_name"] = str(skill)
        return state


intent_router = IntentRouter()
