"""JD 解析 Agent：提取岗位信息。"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base_agent import BaseAgent, _safe_truncate


class JDAnalyzer(BaseAgent):
    name = "jd_analyzer"
    description = "解析 JD，提取技术栈与职级要求"

    SYSTEM_PROMPT = """你是资深技术面试官。解析岗位 JD，输出严格 JSON：
{
  "title": "岗位名称",
  "level": "junior|mid|senior|staff|principal",
  "years_of_experience": 3,
  "tech_stack": ["技术1", "技术2", ...],     // 按重要性降序
  "nice_to_have": [],
  "core_competencies": ["系统设计", "算法", ...],
  "industry": "AI",
  "key_responsibilities": ["职责1", ...],   // 3-5 条
  "summary": "一句话岗位画像"
}
请以 JSON 输出，不要多余文字。"""

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        jd_text = (state.get("jd_text") or "").strip()
        if not jd_text:
            state["jd_parsed"] = {}
            state["error"] = "JD 内容为空"
            return state
        parsed = await self.invoke_llm_json(
            self.SYSTEM_PROMPT, _safe_truncate(jd_text, 8000)
        )
        parsed.setdefault("tech_stack", [])
        parsed.setdefault("core_competencies", [])
        parsed.setdefault("nice_to_have", [])
        parsed.setdefault("level", "mid")
        parsed.setdefault("title", "未知岗位")
        parsed.setdefault("key_responsibilities", [])
        state["jd_parsed"] = parsed
        state["tech_stack"] = [str(t).lower() for t in parsed.get("tech_stack", [])]
        state["error"] = None
        return state


jd_analyzer = JDAnalyzer()
