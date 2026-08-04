"""练习模式评估 Agent：给练习答案打分 + 反馈。"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base_agent import BaseAgent, _safe_truncate
from app.agents.evaluator import SKIP_KEYWORDS


class PracticeEvaluator(BaseAgent):
    name = "practice_evaluator"
    description = "练习答案评分"

    SYSTEM_PROMPT = """你是面试评分官，为练习答案打分并给出反馈。输出严格 JSON：
{
  "score": 0-10,
  "is_correct": true,        // score >= 6
  "feedback": "优缺点反馈",
  "correct_points": ["答对点"],
  "missing_points": ["遗漏点"]
}
评分标准：10=完全正确且有延伸；7-9=基本正确有小缺漏；4-6=部分正确；0-3=明显错误或不知道。
题目: __QUESTION__
参考要点: __REFERENCE__
候选回答: __ANSWER__
请以 JSON 输出。"""

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        q = state.get("current_question") or {}
        answer = state.get("last_user_answer", "")
        prompt = self.SYSTEM_PROMPT
        prompt = prompt.replace("__QUESTION__", _safe_truncate(str(q.get("question", "")), 500))
        prompt = prompt.replace("__REFERENCE__", _safe_truncate(str(q.get("reference_answer", "")), 1500))
        prompt = prompt.replace("__ANSWER__", _safe_truncate(answer, 2000))
        parsed = await self.invoke_llm_json(prompt, "请评分", temperature=0.2)

        try:
            score = max(0, min(10, int(parsed.get("score", 0))))
        except (TypeError, ValueError):
            score = 0
        # 候选人表示不会 → 直接判低分
        if any(k in answer.lower() for k in SKIP_KEYWORDS) or len(answer.strip()) < 10:
            score = min(score, 3)
        state["last_score"] = score
        state["last_is_correct"] = bool(parsed.get("is_correct", score >= 6))
        state["feedback"] = {
            "score": score,
            "is_correct": state["last_is_correct"],
            "feedback": str(parsed.get("feedback", "")),
            "correct_points": list(parsed.get("correct_points", [])),
            "missing_points": list(parsed.get("missing_points", [])),
        }
        return state


practice_evaluator = PracticeEvaluator()
