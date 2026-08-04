"""闲聊兜底 Agent。"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base_agent import BaseAgent, _safe_truncate

SYSTEM_PROMPT = """你是一个友好的 AI 面试陪练助手。用户可能在闲聊或咨询问题。
- 回答简洁口语化，不超过 100 字
- 技术问题可以简要回答，并建议用户开始一场模拟面试来练习
- 不要输出 JSON"""


class ChatAgent(BaseAgent):
    name = "chat_agent"
    description = "闲聊与引导性对话"

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_input = state.get("user_input", "")
        reply = await self.invoke_llm(SYSTEM_PROMPT, _safe_truncate(user_input, 2000))
        state["agent_reply"] = reply
        return state


chat_agent = ChatAgent()
