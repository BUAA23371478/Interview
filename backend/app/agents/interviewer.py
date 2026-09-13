"""面试主持 Agent：出题 + 追问 + 点评 + 收尾。"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.base_agent import BaseAgent, _safe_truncate
from app.agents.difficulty_fsm import describe as describe_difficulty
from app.agents.difficulty_fsm import effective_difficulty
from app.config import settings

LEVEL_LABEL = {
    "junior": "初级", "mid": "中级", "senior": "高级",
    "staff": "资深", "principal": "专家",
}
DIFFICULTY_LABEL = {"easy": "简单", "medium": "中等", "hard": "困难"}


def _build_history_text(qa_history: List[Dict[str, Any]], last_n: int = 3) -> str:
    """最近几轮问答，供出题参考。"""
    lines = []
    for item in qa_history[-last_n:]:
        lines.append(f"[问] {item.get('question', '')[:100]}")
        ans = item.get("answer", "")
        lines.append(f"[答] {ans[:80]}")
    return "\n".join(lines)


class Interviewer(BaseAgent):
    name = "interviewer"
    task = "ask_question"
    description = "面试主控：出题、追问、点评"

    ASK_PROMPT = """你是面试官__TITLE__，正在主持面试。现在要出第 __CUR__/__TOTAL__ 题。

题目信息：
- 主题: __TOPIC__
- 题型: __QTYPE__
- 难度: __DIFFICULTY__
- 考察点: __FOCUS__
- 预设: __PRESET__

候选人画像: __RESUME_SUMMARY__
当前难度状态: __DIFFICULTY_STATE__
最近问答:
__HISTORY__

要求：
- 口语化、像真实面试官提问，不要输出"面试官："前缀
- 不超过 120 字
- 可以有一句自然的过渡语
输出严格 JSON：{"question": "题目", "is_followup": false}
请以 JSON 输出。"""

    FOLLOWUP_PROMPT = """你是面试官，针对候选人刚才的回答继续追问。
原题: __ORIGINAL__
候选回答: __ANSWER__
回答遗漏点: __KEY_MISSING__

要求：
- 追问不超过 80 字，针对遗漏点深挖
- 口语化
输出严格 JSON：{"question": "追问", "is_followup": true}
请以 JSON 输出。"""

    COMMENT_PROMPT = """你是面试官，对候选人刚才的回答给出简短点评（60 字内），
不要透露具体分数，指出一个可以改进的点。
原题: __QUESTION__
候选回答: __ANSWER__
输出严格 JSON：{"comment": "点评"}
请以 JSON 输出。"""

    FINISH_PROMPT = """你是面试官，面试结束，给候选人一句收尾语（80 字内）。
候选人整体表现: __IMPRESSION__
输出严格 JSON：{"farewell": "收尾语"}
请以 JSON 输出。"""

    async def ask_question(self, state: Dict[str, Any]) -> str:
        plan = state.get("question_plan", [])
        idx = int(state.get("current_question_idx", 0))
        q = plan[idx] if idx < len(plan) else {}
        jd = state.get("jd_parsed") or {}
        resume = state.get("resume_parsed") or {}
        title = f"（{LEVEL_LABEL.get(jd.get('level', ''), '')}{jd.get('title', '')}）".replace("（）", "")

        # 难度由状态机裁决（修复初版「FSM 只写状态、出题仍用预设 plan 难度」的脱钩问题）
        difficulty = effective_difficulty(state, q)
        state["current_question_difficulty"] = difficulty

        prompt = self.ASK_PROMPT
        prompt = prompt.replace("__TITLE__", title or "技术岗")
        prompt = prompt.replace("__CUR__", str(idx + 1))
        prompt = prompt.replace("__TOTAL__", str(len(plan)))
        prompt = prompt.replace("__TOPIC__", str(q.get("topic", "")))
        prompt = prompt.replace("__QTYPE__", str(q.get("question_type", "concept")))
        prompt = prompt.replace("__DIFFICULTY__", DIFFICULTY_LABEL.get(difficulty, "中等"))
        prompt = prompt.replace("__FOCUS__", str(q.get("focus", "")))
        prompt = prompt.replace("__PRESET__", str(q.get("prompt", "")) or "无")
        prompt = prompt.replace("__RESUME_SUMMARY__", _safe_truncate(str(resume.get("summary", "")), 300) or "（未提供简历）")
        prompt = prompt.replace("__DIFFICULTY_STATE__", describe_difficulty(state))
        prompt = prompt.replace("__HISTORY__", _build_history_text(state.get("qa_history", [])) or "（无）")

        parsed = await self.invoke_llm_json(prompt, "请出题")
        return str(parsed.get("question", "")).strip()

    async def ask_followup(self, state: Dict[str, Any]) -> str:
        history = state.get("qa_history", [])
        last = history[-1] if history else {}
        prompt = self.FOLLOWUP_PROMPT
        prompt = prompt.replace("__ORIGINAL__", _safe_truncate(str(last.get("question", "")), 300))
        prompt = prompt.replace("__ANSWER__", _safe_truncate(str(last.get("answer", "")), 500))
        missing = (last.get("score") or {}).get("key_missing", [])
        prompt = prompt.replace("__KEY_MISSING__", _safe_truncate("；".join(missing), 300))
        parsed = await self.invoke_llm_json(prompt, "请追问", task="followup")
        return str(parsed.get("question", "")).strip()

    async def comment(self, state: Dict[str, Any]) -> str:
        history = state.get("qa_history", [])
        last = history[-1] if history else {}
        prompt = self.COMMENT_PROMPT
        prompt = prompt.replace("__QUESTION__", _safe_truncate(str(last.get("question", "")), 300))
        prompt = prompt.replace("__ANSWER__", _safe_truncate(str(last.get("answer", "")), 500))
        parsed = await self.invoke_llm_json(prompt, "请点评")
        return str(parsed.get("comment", "")).strip()

    async def farewell(self, state: Dict[str, Any]) -> str:
        records = state.get("score_records", [])
        avg = sum(r.get("score", {}).get("correctness", 0) for r in records) / max(len(records), 1)
        impression = "整体表现不错" if avg >= 7 else "有一些提升空间"
        prompt = self.FINISH_PROMPT.replace("__IMPRESSION__", impression)
        parsed = await self.invoke_llm_json(prompt, "请收尾")
        return str(parsed.get("farewell", "感谢参与本次面试")).strip()


interviewer = Interviewer()
