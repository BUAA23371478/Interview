"""简历匹配分析 Agent：识别候选人与岗位的匹配度、优劣势。"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base_agent import BaseAgent, _safe_truncate


def jd_to_summary(jd: Dict[str, Any]) -> str:
    """把 jd_parsed 转成一行摘要，供 prompt 注入。"""
    parts = []
    if jd.get("title"):
        parts.append(f"岗位: {jd['title']}")
    if jd.get("level"):
        parts.append(f"职级: {jd['level']}")
    if jd.get("years_of_experience"):
        parts.append(f"经验要求: {jd['years_of_experience']} 年")
    if jd.get("tech_stack"):
        parts.append("技术栈: " + ", ".join(jd["tech_stack"]))
    if jd.get("core_competencies"):
        parts.append("核心能力: " + ", ".join(jd["core_competencies"]))
    if jd.get("summary"):
        parts.append(f"画像: {jd['summary']}")
    return "\n".join(parts)


class ResumeAnalyzer(BaseAgent):
    name = "resume_analyzer"
    task = "resume_parse"
    name = "resume_analyzer"
    description = "简历匹配分析"

    SYSTEM_PROMPT = """你是资深技术面试官，结合岗位要求分析候选人简历匹配度。输出严格 JSON：
{
  "overall_score": 82,                     // 0-100 整数
  "match_level": "low|medium|high",
  "strengths": ["优势1", ...],
  "weaknesses": ["不足1", ...],
  "tech_match": {"技术名": {"matched": true, "evidence": "证据"}},
  "experience_fit": "under|fit|over",
  "highlights": ["亮点1", ...],
  "red_flags": [],
  "summary": "一句话匹配总结"
}
请以 JSON 输出，不要多余文字。"""

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        resume_text = (state.get("resume_text") or "").strip()
        jd_parsed = state.get("jd_parsed") or {}
        if not resume_text:
            state["resume_parsed"] = {}
            state["error"] = "简历内容为空"
            return state
        jd_summary = jd_to_summary(jd_parsed) or "（未提供岗位要求）"
        user_prompt = f"岗位要求:\n{jd_summary}\n\n---\n\n候选人简历:\n{_safe_truncate(resume_text, 8000)}"
        parsed = await self.invoke_llm_json(self.SYSTEM_PROMPT, user_prompt)
        parsed.setdefault("strengths", [])
        parsed.setdefault("weaknesses", [])
        parsed.setdefault("highlights", [])
        state["resume_parsed"] = parsed
        state["weaknesses_to_remember"] = list(parsed.get("weaknesses", []))
        state["strengths"] = list(parsed.get("strengths", []))
        state["error"] = None
        return state


resume_analyzer = ResumeAnalyzer()
