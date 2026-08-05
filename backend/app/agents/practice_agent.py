"""练习模式出题 Agent：按主题 + 难度 + 公司风格出题。"""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base_agent import BaseAgent, _safe_truncate

COMPANY_STYLE = {
    "通用": "均衡覆盖各维度，标准追问",
    "字节": "重项目深度、分布式架构、Bad Case 分析、LLM 工程化",
    "阿里": "重 JUC 源码、MySQL 调优、中间件原理、电商场景",
    "腾讯": "重网络编程、高并发、IM/音视频、性能优化",
    "美团": "重业务理解、微服务、数据一致性、本地生活场景",
}


class PracticeQuestionAgent(BaseAgent):
    name = "practice_question"
    description = "练习模式出题"

    SYSTEM_PROMPT = """你是面试出题官，为专项练习出一道新题。输出严格 JSON：
{
  "question": "题目内容",
  "topic": "主题",
  "difficulty": "easy|medium|hard",
  "reference_answer": "参考答案",
  "company_style": "公司风格"
}
要求：
- 主题: __TOPIC__
- 难度: __DIFFICULTY__
- 公司风格: __STYLE__
- 题目要贴合主题、有考察深度；参考答案完整（标准版 + 口语版）
- 严禁与以下已出过的题目重复（换个角度、换个子知识点）：__USED_QUESTIONS__
- 若知识库无相关参考资料，请基于你的通用知识出题，不要重复已有题
请以 JSON 输出。"""

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        topic = state.get("topic", "")
        # 使用当前难度（FSM 已更新），而非初始难度
        difficulty = state.get("current_difficulty") or state.get("difficulty", "medium")
        company_style = state.get("company_style", "通用")
        rag_context = (state.get("rag_context") or "")[:3000]
        # 已出过的题（去重）
        used = state.get("score_records", [])
        used_text = "；".join(str(r.get("question", ""))[:60] for r in used) if used else "（无）"

        prompt = self.SYSTEM_PROMPT
        prompt = prompt.replace("__TOPIC__", topic)
        prompt = prompt.replace("__DIFFICULTY__", difficulty)
        prompt = prompt.replace("__STYLE__", f"{company_style}（{COMPANY_STYLE.get(company_style, '通用')}）")
        prompt = prompt.replace("__USED_QUESTIONS__", used_text)
        user_prompt = f"知识库参考资料:\n{rag_context or '（无）'}"
        parsed = await self.invoke_llm_json(prompt, user_prompt)
        state["current_question"] = {
            "question": str(parsed.get("question", "")),
            "topic": str(parsed.get("topic", topic)),
            "difficulty": str(parsed.get("difficulty", difficulty)),
            "reference_answer": str(parsed.get("reference_answer", "")),
            "company_style": company_style,
        }
        return state


practice_question_agent = PracticeQuestionAgent()
