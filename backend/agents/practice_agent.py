"""刷题模式 LangGraph Agent。

基于 LangGraph StateGraph 管理刷题循环的状态流转：

    START → validate → generate → [interrupt: wait_answer]
        → evaluate → adjust → next → generate (loop) / END

使用 interrupt_before 实现人机交互暂停，通过 SqliteSaver checkpoint 持久化状态。

设计文档参考：PLAN.md 第一章
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, TypedDict

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    try:
        from langgraph.checkpoint.memory import MemorySaver as SqliteSaver
    except ImportError:
        SqliteSaver = None  # type: ignore[assignment]

from langgraph.graph import END, StateGraph
from loguru import logger

from backend.agents.prompts import (
    EVALUATE_PROMPT,
    GENERATE_QUESTION_PROMPT,
    VALIDATE_TOPIC_PROMPT,
)
from backend.config import settings

# ---------------------------------------------------------------------------
# 难度标签
# ---------------------------------------------------------------------------

DIFFICULTY_LABELS: dict[int, str] = {
    1: "入门",
    2: "初级",
    3: "中级",
    4: "高级",
    5: "专家",
}

DEFAULT_MAX_QUESTIONS = 20

# ---------------------------------------------------------------------------
# 状态定义（TypedDict，与 PLAN 1.2 节一致）
# ---------------------------------------------------------------------------


class PracticeAgentState(TypedDict, total=False):
    """刷题 Agent 状态。

    字段与 PLAN.md 1.2 节 PracticeAgentState 完全一致。
    """

    # 会话标识
    session_id: int
    user_id: int

    # 用户输入
    topic: str
    max_questions: int

    # 当前题目
    current_question: Optional[str]
    question_type: Optional[str]  # short_answer / choice
    reference_answer: Optional[str]
    knowledge_points: list[str]

    # 用户回答
    user_answer: Optional[str]

    # 评估结果
    score: Optional[float]
    is_correct: Optional[bool]
    feedback: Optional[dict]

    # 难度自适应
    difficulty_level: int  # 1-5
    consecutive_correct: int
    consecutive_wrong: int

    # 进度
    question_index: int
    total_correct: int
    total_questions: int

    # 去重
    asked_questions: list[tuple[int, str]]  # [(题号, 题目摘要)]

    # 流程控制
    next_action: str  # validate | generate | evaluate | adjust | next | end
    error: Optional[str]


# ---------------------------------------------------------------------------
# Checkpoint 管理
# ---------------------------------------------------------------------------


def create_checkpointer(db_path: str = "data/checkpoints.db") -> Any:
    """创建 SQLite checkpoint 存储。

    与项目现有 SQLite 数据库风格一致，单文件部署。
    当 langgraph SQLite checkpoint 不可用时，回退到 MemorySaver。
    """
    import os

    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    if SqliteSaver is not None:
        try:
            return SqliteSaver.from_conn_string(db_path)
        except (TypeError, AttributeError):
            # MemorySaver 不需要参数
            return SqliteSaver()
    return None


# ---------------------------------------------------------------------------
# Agent 类
# ---------------------------------------------------------------------------


class PracticeAgent:
    """刷题 Agent —— 管理单次刷题会话的 LangGraph 状态图。

    用法::

        checkpointer = create_checkpointer()
        agent = PracticeAgent(llm_client, practice_repo, checkpointer)
        config = {"configurable": {"thread_id": f"practice_{session_id}"}}

        # Phase 1: 生成首题（在 evaluate 前暂停）
        async for event in agent.graph.astream(state, config,
                                               interrupt_before=["evaluate"]):
            ...

        # Phase 2: 提交答案（在 generate 前暂停）
        await agent.graph.aupdate_state(config, {"user_answer": answer})
        async for event in agent.graph.astream(None, config,
                                               interrupt_before=["generate"]):
            ...

        # Phase 3: 请求下一题
        async for event in agent.graph.astream(None, config,
                                               interrupt_before=["evaluate"]):
            ...
    """

    def __init__(self, llm_client, practice_repo, checkpointer: SqliteSaver | None = None) -> None:
        self.llm = llm_client
        self.repo = practice_repo
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # 状态图构建
    # ------------------------------------------------------------------

    def _build_graph(self) -> StateGraph:
        """构建刷题 StateGraph。

        图结构: validate → generate → evaluate → adjust → next → generate (loop) / END
        外部通过 interrupt_before=["evaluate"] / ["generate"] 控制暂停。
        """
        workflow = StateGraph(PracticeAgentState)

        # 注册节点
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("generate", self._generate_node)
        workflow.add_node("evaluate", self._evaluate_node)
        workflow.add_node("adjust", self._adjust_node)
        workflow.add_node("next", self._next_node)

        # 入口
        workflow.set_entry_point("validate")

        # 固定边
        workflow.add_edge("validate", "generate")
        workflow.add_edge("generate", "evaluate")
        workflow.add_edge("evaluate", "adjust")
        workflow.add_edge("adjust", "next")

        # 条件边：next → generate（继续）或 END（完成）
        workflow.add_conditional_edges(
            "next",
            self._route_after_next,
            {
                "generate": "generate",
                "end": END,
            },
        )

        return workflow.compile(checkpointer=self.checkpointer)

    # ------------------------------------------------------------------
    # 节点实现
    # ------------------------------------------------------------------

    async def _validate_node(self, state: PracticeAgentState) -> dict[str, Any]:
        """校验主题是否属于技术面试领域。"""
        logger.info(f"[PracticeAgent] 校验主题: {state.get('topic')}")

        result = await self.llm.chat_with_json(
            VALIDATE_TOPIC_PROMPT.format(topic=state.get("topic", ""))
        )

        if not result.get("is_valid", False):
            error_msg = result.get("reason", "请输入技术面试相关主题")
            logger.warning(f"[PracticeAgent] 主题校验失败: {error_msg}")
            return {
                "error": error_msg,
                "next_action": "error",
            }

        logger.info(f"[PracticeAgent] 主题校验通过")
        return {"next_action": "generate"}

    async def _generate_node(self, state: PracticeAgentState) -> dict[str, Any]:
        """生成题目（接入 RAG 检索知识点）。

        每次进入此节点 question_index 自增，生成新题目后持久化为 pending record。
        """
        next_index = state.get("question_index", 0) + 1
        topic = state.get("topic", "")
        difficulty = state.get("difficulty_level", 3)
        asked = state.get("asked_questions", [])

        # RAG 检索：从知识库获取与主题相关的参考资料
        from backend.rag.vector_store import vector_store as vs

        knowledge_context = await vs.search_for_agent(
            query=topic,
            top_k=3,
            category=None,  # 不过滤分类，让向量相似度决定
        )
        logger.info(
            f"[PracticeAgent] RAG 检索完成 topic={topic} "
            f"context_len={len(knowledge_context)}"
        )

        # 构建去重提示
        dedup_section = ""
        if asked:
            lines = "\n".join(f"  {q}. {p}..." for q, p in asked[-20:])
            dedup_section = f"\n⚠️ 已出题目，绝对不要重复出题（可换考点或角度）：\n{lines}"

        prompt = GENERATE_QUESTION_PROMPT.format(
            topic=topic,
            difficulty=DIFFICULTY_LABELS.get(difficulty, "中级"),
            question_index=next_index,
            history_summary=(
                f"已答题数: {state.get('total_questions', 0)}, "
                f"正确率: {self._accuracy_str(state)}{dedup_section}"
                f"\n\n📚 知识库参考资料：\n{knowledge_context}"
            ),
        )

        logger.info(f"[PracticeAgent] 生成题目 idx={next_index} topic={topic}")
        result = await self.llm.chat_with_json(prompt)

        question_text = result.get("question", "请简述该主题的核心概念。")
        question_type = result.get("question_type", "short_answer")
        reference_answer = result.get("reference_answer", "")
        knowledge_points = result.get("knowledge_points", [])

        # 持久化到 DB（捕获 returned record 的 id，供 service 层跟踪）
        record = await self.repo.create_pending_record(
            session_id=state.get("session_id", 0),
            question_number=next_index,
            question=question_text,
            question_type=question_type,
            reference_answer=reference_answer,
            knowledge_points=knowledge_points,
        )

        updated_asked = list(asked) + [(next_index, question_text[:60])]

        return {
            "question_index": next_index,
            "current_question": question_text,
            "question_type": question_type,
            "reference_answer": reference_answer,
            "knowledge_points": knowledge_points,
            "asked_questions": updated_asked,
            "next_action": "evaluate",
            "_pending_record_id": record.id,
        }

    async def _evaluate_node(self, state: PracticeAgentState) -> dict[str, Any]:
        """评分 + 生成反馈（接入 RAG 检索参考答案）。"""
        logger.info(
            f"[PracticeAgent] 评估回答 session={state.get('session_id')} "
            f"q={state.get('question_index')}"
        )

        # RAG 检索：搜索相关参考答案
        from backend.rag.vector_store import vector_store as vs

        search_query = f"{state.get('topic', '')} {state.get('current_question', '')}"
        knowledge_context = await vs.search_for_agent(
            query=search_query,
            top_k=3,
        )

        prompt = EVALUATE_PROMPT.format(
            topic=state.get("topic", ""),
            question=state.get("current_question", ""),
            reference_answer=(
                f"{state.get('reference_answer', '')}\n\n"
                f"📚 知识库补充参考：\n{knowledge_context}"
            ),
            user_answer=state.get("user_answer", ""),
        )
        result = await self.llm.chat_with_json(prompt)

        score = float(result.get("score", 0))
        is_correct = bool(result.get("is_correct", score >= 60))
        total_questions = state.get("total_questions", 0) + 1
        total_correct = state.get("total_correct", 0) + (1 if is_correct else 0)

        feedback = {
            "score": score,
            "isCorrect": is_correct,
            "correctAnswer": result.get("correct_answer") or state.get("reference_answer", ""),
            "analysis": result.get("analysis") or "",
            "knowledgePoints": result.get("knowledge_points") or state.get("knowledge_points", []),
            "commonMistakes": result.get("common_mistakes") or [],
        }

        return {
            "user_answer": state.get("user_answer"),  # 保留
            "score": score,
            "is_correct": is_correct,
            "feedback": feedback,
            "total_questions": total_questions,
            "total_correct": total_correct,
            "next_action": "adjust",
        }

    async def _adjust_node(self, state: PracticeAgentState) -> dict[str, Any]:
        """难度自适应：连对 3 题升档，连错 2 题降档。"""
        difficulty = state.get("difficulty_level", 3)
        is_correct = state.get("is_correct", False)
        consecutive_correct = state.get("consecutive_correct", 0)
        consecutive_wrong = state.get("consecutive_wrong", 0)

        if is_correct:
            consecutive_correct += 1
            consecutive_wrong = 0
            if consecutive_correct >= 3:
                difficulty = min(5, difficulty + 1)
                consecutive_correct = 0
                logger.info(f"[PracticeAgent] 难度提升至 {difficulty}")
        else:
            consecutive_wrong += 1
            consecutive_correct = 0
            if consecutive_wrong >= 2:
                difficulty = max(1, difficulty - 1)
                consecutive_wrong = 0
                logger.info(f"[PracticeAgent] 难度降低至 {difficulty}")

        # 持久化
        await self.repo.update_session_stats(
            state.get("session_id", 0),
            consecutive_correct=consecutive_correct,
            consecutive_wrong=consecutive_wrong,
            difficulty_level=difficulty,
            total_questions=state.get("total_questions", 0),
            total_correct=state.get("total_correct", 0),
        )

        return {
            "difficulty_level": difficulty,
            "consecutive_correct": consecutive_correct,
            "consecutive_wrong": consecutive_wrong,
            "next_action": "next",
        }

    async def _next_node(self, state: PracticeAgentState) -> dict[str, Any]:
        """判断是否继续：已达上限 → end，否则 → generate。"""
        total = state.get("total_questions", 0)
        max_q = state.get("max_questions", DEFAULT_MAX_QUESTIONS)

        if total >= max_q:
            logger.info(f"[PracticeAgent] 已达题目上限 total={total} max={max_q}")
            # 标记会话完成
            await self.repo.update_session_stats(
                state.get("session_id", 0),
                status="completed",
            )
            return {"next_action": "end"}

        logger.info(f"[PracticeAgent] 继续出题 total={total}/{max_q}")
        return {"next_action": "generate"}

    # ------------------------------------------------------------------
    # 条件路由
    # ------------------------------------------------------------------

    @staticmethod
    def _route_after_next(state: PracticeAgentState) -> Literal["generate", "end"]:
        action = state.get("next_action", "end")
        if action == "generate":
            return "generate"
        return "end"

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _accuracy_str(state: PracticeAgentState) -> str:
        total = state.get("total_questions", 0)
        if total == 0:
            return "N/A"
        return f"{round(state.get('total_correct', 0) / total * 100)}%"

    @staticmethod
    def default_state(
        session_id: int,
        user_id: int,
        topic: str,
        max_questions: int = DEFAULT_MAX_QUESTIONS,
        difficulty_level: int = 3,
    ) -> PracticeAgentState:
        """创建初始状态。"""
        return PracticeAgentState(
            session_id=session_id,
            user_id=user_id,
            topic=topic,
            max_questions=max_questions,
            current_question=None,
            question_type=None,
            reference_answer=None,
            knowledge_points=[],
            user_answer=None,
            score=None,
            is_correct=None,
            feedback=None,
            difficulty_level=difficulty_level,
            consecutive_correct=0,
            consecutive_wrong=0,
            question_index=0,
            total_correct=0,
            total_questions=0,
            asked_questions=[],
            next_action="validate",
            error=None,
        )

    @staticmethod
    def restore_state(
        session_id: int,
        user_id: int,
        topic: str,
        max_questions: int,
        difficulty_level: int,
        consecutive_correct: int,
        consecutive_wrong: int,
        total_questions: int,
        total_correct: int,
        status: str | None = None,
    ) -> PracticeAgentState:
        """从 DB 记录恢复状态。"""
        s = PracticeAgentState(
            session_id=session_id,
            user_id=user_id,
            topic=topic,
            max_questions=max_questions,
            current_question=None,
            question_type=None,
            reference_answer=None,
            knowledge_points=[],
            user_answer=None,
            score=None,
            is_correct=None,
            feedback=None,
            difficulty_level=difficulty_level,
            consecutive_correct=consecutive_correct,
            consecutive_wrong=consecutive_wrong,
            question_index=total_questions,
            total_correct=total_correct,
            total_questions=total_questions,
            asked_questions=[],
            next_action="generate" if (status != "completed" and total_questions < max_questions) else "end",
            error=None,
        )
        return s
