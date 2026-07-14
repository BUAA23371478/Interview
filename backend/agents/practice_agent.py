"""刷题模式 LangGraph Agent。

基于 LangGraph StateGraph 管理刷题循环的状态流转：
  validate_topic → generate_question → wait_answer → evaluate → feedback
    → adjust_difficulty → wait_next → (loop)

设计文档参考：后端技术设计文档 第五章 5.1 节
"""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from langgraph.graph import StateGraph, END
from loguru import logger


# ---------------------------------------------------------------------------
# 状态定义
# ---------------------------------------------------------------------------

class PracticeState(dict):
    """刷题 Agent 的状态字典。

    字段说明（与 TypedDict 等价，这里使用 dict 以兼容 langgraph 的 StateGraph 泛型）：
      session_id, user_id, topic,
      current_question, question_type, reference_answer, knowledge_points,
      user_answer, score, is_correct, feedback,
      difficulty_level (1-5), consecutive_correct, consecutive_wrong,
      question_index, total_correct, total_questions,
      next_action: generate_question | wait_answer | evaluate | feedback | error | end
    """

    pass


# 难度标签
DIFFICULTY_LABELS: dict[int, str] = {
    1: "入门",
    2: "初级",
    3: "中级",
    4: "高级",
    5: "专家",
}


# ---------------------------------------------------------------------------
# Agent 类
# ---------------------------------------------------------------------------

class PracticeAgent:
    """刷题 Agent —— 管理单次刷题会话的状态图。

    用法::

        agent = PracticeAgent(llm_client, practice_repo)
        state = PracticeState(session_id=1, topic="Java", ...)
        state = await agent.validate_topic(state)
        # 继续通过 graph.ainvoke / graph.astream 推进状态
    """

    def __init__(self, llm_client, practice_repo) -> None:
        self.llm = llm_client
        self.repo = practice_repo
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # 状态图构建
    # ------------------------------------------------------------------

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(PracticeState)

        workflow.add_node("validate_topic", self.validate_topic)
        workflow.add_node("generate_question", self.generate_question)
        workflow.add_node("evaluate", self.evaluate)
        workflow.add_node("adjust_difficulty", self.adjust_difficulty)

        workflow.set_entry_point("validate_topic")

        workflow.add_conditional_edges(
            "validate_topic",
            self._after_validate,
            {
                "generate_question": "generate_question",
                "error": END,
            },
        )
        workflow.add_edge("generate_question", END)  # wait_answer 由外部 POST 触发
        workflow.add_edge("evaluate", "adjust_difficulty")
        workflow.add_edge("adjust_difficulty", END)   # wait_next 由外部 POST 触发

        return workflow.compile()

    # ------------------------------------------------------------------
    # 节点实现
    # ------------------------------------------------------------------

    async def validate_topic(self, state: dict[str, Any]) -> dict[str, Any]:
        """校验主题是否属于技术面试领域。"""
        from backend.agents.prompts import VALIDATE_TOPIC_PROMPT

        logger.info(f"校验主题: {state.get('topic')}")
        result = await self.llm.chat_with_json(
            VALIDATE_TOPIC_PROMPT.format(topic=state.get("topic", ""))
        )

        if result.get("is_valid", False):
            state["next_action"] = "generate_question"
        else:
            state["error"] = result.get("reason", "请输入技术面试相关主题")
            state["next_action"] = "error"
        return state

    async def generate_question(self, state: dict[str, Any]) -> dict[str, Any]:
        """生成题目。"""
        from backend.agents.prompts import GENERATE_QUESTION_PROMPT

        state["question_index"] = state.get("question_index", 0) + 1
        prompt = GENERATE_QUESTION_PROMPT.format(
            topic=state.get("topic", ""),
            difficulty=DIFFICULTY_LABELS.get(state.get("difficulty_level", 3), "中级"),
            question_index=state["question_index"],
            history_summary=self._history_summary(state),
        )
        result = await self.llm.chat_with_json(prompt)

        state["current_question"] = result.get("question", "请简述该主题的核心概念。")
        state["question_type"] = result.get("question_type", "short_answer")
        state["reference_answer"] = result.get("reference_answer", "")
        state["knowledge_points"] = result.get("knowledge_points", [])
        state["next_action"] = "wait_answer"
        return state

    async def evaluate(self, state: dict[str, Any]) -> dict[str, Any]:
        """评分 + 生成解析。"""
        from backend.agents.prompts import EVALUATE_PROMPT

        prompt = EVALUATE_PROMPT.format(
            topic=state.get("topic", ""),
            question=state.get("current_question", ""),
            reference_answer=state.get("reference_answer", ""),
            user_answer=state.get("user_answer", ""),
        )
        result = await self.llm.chat_with_json(prompt)

        state["score"] = float(result.get("score", 0))
        state["is_correct"] = bool(result.get("is_correct", state["score"] >= 60))
        state["feedback"] = result.get("feedback", "")
        state["total_questions"] = state.get("total_questions", 0) + 1
        if state["is_correct"]:
            state["total_correct"] = state.get("total_correct", 0) + 1
        state["next_action"] = "feedback"
        return state

    async def adjust_difficulty(self, state: dict[str, Any]) -> dict[str, Any]:
        """难度自适应：连续答对 3 题升一档，连续答错 2 题降一档。"""
        if state.get("is_correct"):
            state["consecutive_correct"] = state.get("consecutive_correct", 0) + 1
            state["consecutive_wrong"] = 0
            if state["consecutive_correct"] >= 3:
                state["difficulty_level"] = min(5, state.get("difficulty_level", 3) + 1)
                state["consecutive_correct"] = 0
                logger.info(f"难度提升至 {state['difficulty_level']}")
        else:
            state["consecutive_wrong"] = state.get("consecutive_wrong", 0) + 1
            state["consecutive_correct"] = 0
            if state["consecutive_wrong"] >= 2:
                state["difficulty_level"] = max(1, state.get("difficulty_level", 3) - 1)
                state["consecutive_wrong"] = 0
                logger.info(f"难度降低至 {state['difficulty_level']}")

        # 持久化
        await self.repo.update_session_stats(
            state["session_id"],
            consecutive_correct=state.get("consecutive_correct", 0),
            consecutive_wrong=state.get("consecutive_wrong", 0),
            difficulty_level=state.get("difficulty_level", 3),
            total_questions=state.get("total_questions", 0),
            total_correct=state.get("total_correct", 0),
        )
        state["next_action"] = "end"
        return state

    # ------------------------------------------------------------------
    # 条件边
    # ------------------------------------------------------------------

    @staticmethod
    def _after_validate(state: dict[str, Any]) -> Literal["generate_question", "error"]:
        if state.get("next_action") == "error":
            return "error"
        return "generate_question"

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _history_summary(state: dict[str, Any]) -> str:
        total = state.get("total_questions", 0)
        if total == 0:
            return "暂无历史记录"
        correct = state.get("total_correct", 0)
        accuracy = f"{round(correct / total * 100)}%" if total > 0 else "N/A"
        return f"已答 {total} 题，正确率 {accuracy}，当前难度 {DIFFICULTY_LABELS.get(state.get('difficulty_level', 3), '中级')}"
