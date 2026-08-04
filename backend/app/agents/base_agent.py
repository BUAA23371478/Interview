"""
Agent 基类：统一 LLM 调用能力。

关键约定：prompt 使用 __UPPER_CASE_PLACEHOLDER__ + .replace 注入（而非 str.format），
以兼容用户提供的 JD/简历中可能包含的 { } 字符。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.llm import llm_client


class BaseAgent:
    name: str = "base"
    description: str = ""

    async def invoke_llm(self, system_prompt: str, user_prompt: str,
                         *, temperature: Optional[float] = None) -> str:
        return await llm_client.chat(system_prompt, user_prompt, temperature=temperature)

    async def invoke_llm_json(self, system_prompt: str, user_prompt: str,
                              *, temperature: Optional[float] = None) -> Dict[str, Any]:
        return await llm_client.chat_with_json(system_prompt, user_prompt, temperature=temperature)


def _safe_truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len] + "…（已截断）"
