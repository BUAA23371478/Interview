"""题库规划 Agent：基于 JD + 简历 + RAG 上下文规划题目分布。"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.base_agent import BaseAgent, _safe_truncate
from app.agents.resume_analyzer import jd_to_summary


class QuestionPlanner(BaseAgent):
    name = "question_planner"
    task = "question_plan"
    name = "question_planner"
    description = "面试题目规划"

    SYSTEM_PROMPT = """你是面试出题专家。基于岗位要求、候选人画像与知识库资料，规划 __TOTAL__ 道面试题。输出严格 JSON：
{"plan": [{"topic": "主题", "question_type": "concept|scenario|code|behavior|project",
           "difficulty": "easy|medium|hard", "focus": "考察点", "prompt": "预设题目或留空"}]}

分布规则：
- 难度比例：基础 30% / 中等 50% / 高阶 20%
- 题型混合：概念题 / 场景设计 / 代码实现 / 行为面试 / 项目深挖
- 优先覆盖岗位核心技术栈，针对候选人弱点定向出题
- plan 数组长度必须严格等于 __TOTAL__
请以 JSON 输出，不要多余文字。"""

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        total = int(state.get("total_questions", 10))
        jd_parsed = state.get("jd_parsed") or {}
        resume_parsed = state.get("resume_parsed") or {}
        rag_context = (state.get("rag_context") or "")[:4000]

        user_prompt = (
            f"岗位要求:\n{jd_to_summary(jd_parsed)}\n\n"
            f"候选人画像:\n"
            f"- 匹配度: {resume_parsed.get('overall_score', '-')}/100\n"
            f"- 优势: {', '.join(resume_parsed.get('strengths', []))}\n"
            f"- 不足: {', '.join(resume_parsed.get('weaknesses', []))}\n\n"
            f"知识库参考资料:\n{rag_context or '（无）'}\n\n"
            f"请规划 {total} 道题。"
        )
        prompt = self.SYSTEM_PROMPT.replace("__TOTAL__", str(total))
        parsed = await self.invoke_llm_json(prompt, user_prompt)
        plan: List[Dict[str, Any]] = parsed.get("plan", [])
        # 归一化
        for i, q in enumerate(plan[:total]):
            q.setdefault("id", f"Q{i + 1}")
            q.setdefault("topic", "综合")
            q.setdefault("question_type", "concept")
            q.setdefault("difficulty", "medium")
            q.setdefault("focus", "")
            q.setdefault("prompt", "")
        plan = plan[:total]
        if not plan:
            state["error"] = "题目规划失败"
            state["question_plan"] = []
        else:
            state["question_plan"] = plan
            state["current_question_idx"] = 0
            state["error"] = None
        return state


question_planner = QuestionPlanner()
