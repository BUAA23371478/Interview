"""评估 Agent：逐题评分 + 面试总结报告。"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.base_agent import BaseAgent, _safe_truncate

SKIP_KEYWORDS = ("不知道", "不清楚", "不会", "跳过", "pass", "不懂", "没接触过", "可以再说一遍", "再说一遍")


class Evaluator(BaseAgent):
    name = "evaluator"
    task = "score"
    description = "答案评分与面试报告"

    SINGLE_SCORE_PROMPT = """你是面试官，为候选人的回答评分。输出严格 JSON：
{
  "correctness": 0-10,    // 正确性
  "depth": 0-10,          // 深度
  "structure": 0-10,      // 条理
  "example": 0-10,        // 是否有实例/细节
  "is_correct": true,     // correctness>=6 且 depth>=5 为 true
  "key_missing": ["遗漏点1"],   // 最多 3 个
  "followup_needed": false,     // key_missing 非空且 correctness<8 时为 true
  "followup_reason": ""
}
题目: __QUESTION__
候选回答: __ANSWER__
请以 JSON 输出。"""

    REPORT_PROMPT = """你是面试主考官，基于整场面试的逐题评分生成总结报告。输出严格 JSON：
{
  "overall_score": 78,                 // 0-100 整数
  "recommendation": "strong_hire|hire|weak_hire|no_hire",
  "dimension_scores": {
    "technical_knowledge": 8, "problem_solving": 7, "system_design": 7,
    "communication": 8, "practical_experience": 8, "learning_ability": 7
  },
  "strengths": ["优势1"],
  "weaknesses": ["不足1"],
  "highlights": [{"round": 1, "reason": "亮点"}],
  "concerns": [],
  "topic_performance": [{"topic": "主题", "performance": "good|average|weak", "comment": "评价"}],
  "summary": "200字内总结",
  "interviewer_comment": "100字内面试官评语"
}
请基于 __QA_RECORDS__ 的真实评分，不要编造。请以 JSON 输出。"""

    async def score_one(self, question: str, answer: str) -> Dict[str, Any]:
        prompt = self.SINGLE_SCORE_PROMPT
        prompt = prompt.replace("__QUESTION__", _safe_truncate(question, 500))
        prompt = prompt.replace("__ANSWER__", _safe_truncate(answer, 2000))
        parsed = await self.invoke_llm_json(prompt, "请评分", temperature=0.2)

        # 兜底：候选人表示不会 → 不追问
        if any(k in answer.lower() for k in SKIP_KEYWORDS) or len(answer.strip()) < 10:
            parsed["followup_needed"] = False
            parsed["key_missing"] = []

        def _num(v: Any, default: int = 0) -> int:
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        correctness = _num(parsed.get("correctness"))
        depth = _num(parsed.get("depth"))
        parsed["correctness"] = max(0, min(10, correctness))
        parsed["depth"] = max(0, min(10, depth))
        parsed["structure"] = max(0, min(10, _num(parsed.get("structure"))))
        parsed["example"] = max(0, min(10, _num(parsed.get("example"))))
        parsed["is_correct"] = bool(parsed.get("is_correct", correctness >= 6 and depth >= 5))
        parsed.setdefault("key_missing", [])
        parsed.setdefault("followup_reason", "")
        return parsed

    async def generate_report(self, state: Dict[str, Any]) -> Dict[str, Any]:
        records = state.get("score_records", [])
        qa_text = []
        for r in records:
            qa_text.append(
                f"[第{len(qa_text) + 1}题] {r.get('question', '')[:150]}\n"
                f"答: {r.get('answer', '')[:200]}\n"
                f"得分: {r.get('score', {})}"
            )
        prompt = self.REPORT_PROMPT.replace("__QA_RECORDS__", "\n".join(qa_text)[:8000] or "（无记录）")
        parsed = await self.invoke_llm_json(prompt, "请生成报告", temperature=0.3, task="report")
        parsed.setdefault("overall_score", 0)
        parsed.setdefault("strengths", [])
        parsed.setdefault("weaknesses", [])
        parsed.setdefault("dimension_scores", {})
        return parsed


evaluator = Evaluator()
