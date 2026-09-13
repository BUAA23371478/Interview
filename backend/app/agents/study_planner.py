"""学习规划 Agent：基于报告生成 4 周复习计划。"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base_agent import BaseAgent, _safe_truncate


class StudyPlanner(BaseAgent):
    name = "study_planner"
    task = "study_plan"
    name = "study_planner"
    description = "制定个性化复习计划"

    SYSTEM_PROMPT = """你是学习规划师。基于候选人面试报告与长期薄弱点，制定 4 周复习计划。输出严格 JSON：
{
  "overall_advice": "总体建议",
  "weeks": [
    {"week": 1, "theme": "主题", "goals": ["目标1"], "daily_hours": 2, "resources": ["资料1"]},
    {"week": 2, "theme": "主题", "goals": [], "daily_hours": 2, "resources": []},
    {"week": 3, "theme": "主题", "goals": [], "daily_hours": 2, "resources": []},
    {"week": 4, "theme": "主题", "goals": [], "daily_hours": 2, "resources": []}
  ],
  "practice_projects": ["实践项目1"],
  "mock_interview_tips": ["模拟面试建议1"]
}
请以 JSON 输出。"""

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        report = state.get("final_report") or {}
        weaknesses = report.get("weaknesses", [])[:5]
        long_term = state.get("long_term_weaknesses", [])[:5]
        all_weak = list(dict.fromkeys(list(weaknesses) + list(long_term)))
        user_prompt = (
            f"面试薄弱点: {', '.join(all_weak) or '无'}\n"
            f"总体评价: {report.get('summary', '')}\n"
            f"推荐: {report.get('recommendation', '')}"
        )
        parsed = await self.invoke_llm_json(self.SYSTEM_PROMPT, user_prompt)
        parsed.setdefault("weeks", [])
        parsed.setdefault("practice_projects", [])
        parsed.setdefault("mock_interview_tips", [])
        parsed.setdefault("overall_advice", "")
        state["study_plan"] = parsed
        return state


study_planner = StudyPlanner()
