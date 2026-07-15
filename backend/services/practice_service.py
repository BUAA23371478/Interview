"""刷题模式业务编排层 —— 基于 LangGraph Agent 状态图。

使用 LangGraph StateGraph + interrupt_before 实现人机交互暂停，
通过 SqliteSaver checkpoint 持久化状态，支持断线恢复。

图结构: validate → generate → [interrupt] → evaluate → adjust → next → generate (loop) / END
"""

from __future__ import annotations

import json as _json
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from backend.agents.practice_agent import (
    DEFAULT_MAX_QUESTIONS,
    PracticeAgent,
    PracticeAgentState,
    create_checkpointer,
)
from backend.agents.prompts import VALIDATE_TOPIC_PROMPT
from backend.database.connection import async_session
from backend.llm.client import UnifiedLLMClient
from backend.middleware.error_handler import SessionNotFoundError, TopicValidationError
from backend.repositories.practice_repo import PracticeRepo
from backend.sse.emitter import SSEEmitter
from backend.sse.manager import SSEManager

# ---------------------------------------------------------------------------
# 全局 checkpointer（单例，所有 Agent 共享）
# ---------------------------------------------------------------------------

_checkpointer: Any = None


def _get_checkpointer():
    """延迟初始化 checkpointer（避免导入时创建文件）。"""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = create_checkpointer()
    return _checkpointer


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PracticeService:
    """刷题模式业务编排层 —— 委托给 LangGraph PracticeAgent。

    职责：
    - 会话生命周期管理（创建 / 恢复 / 状态查询）
    - SSE 事件流（将 Agent 节点输出转换为前端事件）
    - 人机交互桥接（POST 端点触发图执行下一段）
    """

    # 保留内存状态缓存，加速热点会话访问（checkpoint 为主力存储）
    _session_cache: dict[int, PracticeAgentState] = {}
    # 出题时创建的 pending record id → 提交/跳过时用于原地更新（避免重复记录）
    _pending_record_ids: dict[int, int] = {}

    def __init__(self, db, llm_client: UnifiedLLMClient, sse_manager: SSEManager) -> None:
        self.db = db
        self.llm = llm_client
        self.sse = sse_manager
        self.practice_repo = PracticeRepo(db) if db is not None else None

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def create_session(self, user_id: int, topic: str, max_questions: int = DEFAULT_MAX_QUESTIONS):
        """创建刷题会话：校验主题 → 持久化 → 初始化状态。"""
        logger.info(f"创建刷题会话 user={user_id} topic={topic} max_q={max_questions}")

        # 主题校验
        validation = await self.llm.chat_with_json(
            [{"role": "user", "content": VALIDATE_TOPIC_PROMPT.format(topic=topic)}]
        )
        if not validation.get("is_valid", False):
            raise TopicValidationError(validation.get("reason", "请输入技术面试相关主题"))

        session = await self.practice_repo.create_session(
            user_id=user_id, topic=topic, difficulty_level=3, max_questions=max_questions,
        )

        # 初始化 Agent 状态
        state = PracticeAgent.default_state(
            session_id=session.id,
            user_id=user_id,
            topic=topic,
            max_questions=max_questions,
        )
        PracticeService._session_cache[session.id] = state
        logger.info(f"刷题会话 {session.id} 创建成功")
        return session

    # ==================================================================
    # SSE 流（长连接）
    # ==================================================================

    async def stream_session(self, session_id: int, user_id: int) -> AsyncGenerator[dict[str, Any], None]:
        """SSE 流式主循环。

        Phase 1: 短生命期 DB → 恢复状态 → 生成首题（Agent graph: validate → generate）
        Phase 2: 队列消费（等待 POST 端点的后续事件）
        """
        session_key = f"practice:{session_id}"
        self.sse.create_connection(session_key, user_id)
        logger.info(f"SSE 连接建立: {session_key}")

        try:
            # ====== Phase 1: 短生命期 DB（恢复 + 首题） ======
            async with async_session() as db:
                self.practice_repo = PracticeRepo(db)

                state = await self._load_and_prepare(session_id, user_id)
                PracticeService._session_cache[session_id] = state

                yield self._sse("session_ready", {
                    "sessionId": str(session_id),
                    "maxQuestions": state.get("max_questions", DEFAULT_MAX_QUESTIONS),
                })

                if self._is_completed(state):
                    logger.info(f"会话已完成 session={session_id}")
                    yield self._sse("session_completed", {"message": "本会话已达题目上限"})
                    await db.commit()
                    async for event in self.sse.stream_events(session_key):
                        yield event
                    return

                # 处理待答题目（断线恢复场景）
                pending = state.get("pending_question")
                if pending and state.get("current_question"):
                    logger.info(f"[SSE] 恢复待答题目 idx={state['question_index']}")
                    yield self._sse("question_start", {"questionIndex": state["question_index"]})
                    question_text = state["current_question"]
                    for i in range(0, len(question_text), 80):
                        yield self._sse("question_chunk", {"content": question_text[i : i + 80]})
                    yield self._sse("question_done", {
                        "question": {
                            "id": f"practice-{session_id}-{state['question_index']}",
                            "content": question_text,
                            "type": state.get("question_type", "short_answer"),
                            "options": None,
                        },
                        "questionIndex": state["question_index"],
                        "difficulty": state.get("difficulty_level", 3),
                        "referenceAnswer": state.get("reference_answer", ""),
                    })
                    state.pop("pending_question", None)
                else:
                    # 通过 Agent graph 生成首题
                    try:
                        logger.info(f"[SSE] Agent 生成首题 session={session_id}")
                        await self._run_and_stream_question(state, session_key, session_id, is_first=True)
                    except Exception as e:
                        logger.error(f"生成首题失败: {e}")
                        yield self._sse("error", {"message": f"AI 题目生成失败: {e}"})
                        await db.rollback()
                        return

                await db.commit()
            # ====== DB session 已释放 ======

            # ====== Phase 2: 队列消费 ======
            async for event in self.sse.stream_events(session_key):
                yield event

        finally:
            self.sse.remove_connection(session_key)
            logger.info(f"SSE 连接断开: {session_key}")

    # ==================================================================
    # POST 端点
    # ==================================================================

    async def submit_answer(self, session_id: int, user_id: int, answer: str, time_spent_seconds: int | None) -> None:
        """提交答案 → Agent graph: evaluate → adjust → next。"""
        state = self._get_state(session_id, user_id)
        logger.info(f"提交答案 session={session_id} q={state.get('question_index')}")

        state["user_answer"] = answer

        emitter = SSEEmitter(f"practice:{session_id}")
        agent = self._make_agent()
        config = {"configurable": {"thread_id": f"practice_{session_id}"}}

        # 更新 checkpoint 中的 user_answer
        await agent.graph.aupdate_state(config, {"user_answer": answer})

        # 运行 evaluate → adjust → next（在 generate 前暂停）
        try:
            async for event in agent.graph.astream(None, config, interrupt_before=["generate"]):
                for node_name, node_output in event.items():
                    if node_name == "evaluate":
                        state.update(node_output)
                    elif node_name == "adjust":
                        state.update(node_output)
                    elif node_name == "next":
                        state.update(node_output)

            # 同步状态到缓存
            final_graph_state = agent.graph.get_state(config)
            if final_graph_state and final_graph_state.values:
                for k, v in final_graph_state.values.items():
                    if v is not None:
                        state[k] = v
            PracticeService._session_cache[session_id] = state

            # 持久化答题记录——直接从 DB 查最新 pending record 并更新
            feedback = state.get("feedback", {})
            analysis_text = feedback.get("analysis", "") if isinstance(feedback, dict) else ""
            pending = await self.practice_repo.get_pending_record(session_id)
            if pending:
                await self.practice_repo.update_record_answer(
                    pending.id,
                    user_answer=answer,
                    score=state.get("score", 0),
                    is_correct=state.get("is_correct", False),
                    feedback=analysis_text,
                    time_spent_seconds=time_spent_seconds,
                )
            else:
                logger.warning(f"未找到 pending record session={session_id}，创建新记录")
                await self.practice_repo.create_record(
                    session_id=session_id,
                    question_number=state.get("question_index", 0),
                    question=state.get("current_question", ""),
                    question_type=state.get("question_type", "short_answer"),
                    reference_answer=state.get("reference_answer", ""),
                    user_answer=answer,
                    score=state.get("score", 0),
                    is_correct=state.get("is_correct", False),
                    feedback=analysis_text,
                    knowledge_points=state.get("knowledge_points", []),
                    time_spent_seconds=time_spent_seconds,
                )

            # 判断是否完成
            completed = state.get("next_action") == "end"
            if completed:
                await self.practice_repo.update_session_stats(
                    session_id, status="completed",
                )

            # SSE 推送反馈
            await emitter.emit("feedback_start", {"questionIndex": state.get("question_index", 0)})
            if analysis_text:
                for i in range(0, len(analysis_text), 120):
                    await emitter.emit_text("feedback_chunk", analysis_text[i : i + 120])
            await emitter.emit("feedback_done", {
                "score": state.get("score", 0),
                "is_correct": state.get("is_correct", False),
                "feedback": feedback,
                "completed": completed,
            })

            # 如果已完成，发送 session_completed
            if completed:
                await emitter.emit("session_completed", {"message": "本会话已达题目上限"})

            logger.info(f"评估完成 session={session_id} score={state.get('score')} completed={completed}")

        except Exception as e:
            logger.error(f"Agent 评估失败: {e}")
            await emitter.emit("error", {"message": f"AI 评估失败: {e}"})
            raise

    async def request_next(self, session_id: int, user_id: int) -> None:
        """请求下一题 → Agent graph: generate（从 checkpoint 继续）。"""
        state = self._get_state(session_id, user_id)
        logger.info(f"请求下一题 session={session_id}")

        if self._is_completed(state):
            emitter = SSEEmitter(f"practice:{session_id}")
            await emitter.emit("session_completed", {"message": "本会话已达题目上限"})
            return

        await self._run_and_stream_question(state, f"practice:{session_id}", session_id, is_first=False)

    async def skip_question(self, session_id: int, user_id: int) -> None:
        """不了解：跳过当前题目，不调 LLM 评估，直接推送参考答案。"""
        state = self._get_state(session_id, user_id)
        logger.info(f"跳过题目 session={session_id} q={state.get('question_index')}")

        # 直接从 DB 查最新 pending record 并更新
        pending = await self.practice_repo.get_pending_record(session_id)
        if pending:
            await self.practice_repo.update_record_answer(
                pending.id,
                user_answer="不了解",
                score=0,
                is_correct=False,
                feedback="",
                time_spent_seconds=0,
            )
        else:
            logger.warning(f"skip 未找到 pending record session={session_id}，创建新记录")
            await self.practice_repo.create_record(
                session_id=session_id,
                question_number=state.get("question_index", 0),
                question=state.get("current_question", ""),
                question_type=state.get("question_type", "short_answer"),
                reference_answer=state.get("reference_answer", ""),
                user_answer="不了解",
                score=0,
                is_correct=False,
                feedback="",
                knowledge_points=state.get("knowledge_points", []),
                time_spent_seconds=0,
            )

        total = state.get("total_questions", 0) + 1
        state["total_questions"] = total
        feedback = {
            "score": 0,
            "isCorrect": False,
            "correctAnswer": state.get("reference_answer", ""),
            "analysis": "",
            "knowledgePoints": state.get("knowledge_points", []),
            "commonMistakes": [],
        }
        state["feedback"] = feedback

        completed = total >= state.get("max_questions", DEFAULT_MAX_QUESTIONS)
        await self.practice_repo.update_session_stats(
            session_id,
            **({"status": "completed"} if completed else {}),
            total_questions=total,
            total_correct=state.get("total_correct", 0),
        )

        if completed:
            state["next_action"] = "end"

        PracticeService._session_cache[session_id] = state

        # SSE 推送参考答案
        emitter = SSEEmitter(f"practice:{session_id}")
        ref = state.get("reference_answer", "") or ""
        await emitter.emit("feedback_start", {"questionIndex": state.get("question_index", 0)})
        if ref:
            for i in range(0, len(ref), 120):
                await emitter.emit_text("feedback_chunk", ref[i : i + 120])
        await emitter.emit("feedback_done", {
            "score": 0, "is_correct": False,
            "feedback": feedback, "completed": completed, "skipped": True,
        })

        if completed:
            await emitter.emit("session_completed", {"message": "本会话已达题目上限"})

        logger.info(f"跳过完成 session={session_id}")

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_status(self, session_id: int, user_id: int) -> dict[str, Any] | None:
        """查询会话状态（用于前端轮询 / 恢复）。"""
        state = PracticeService._session_cache.get(session_id)
        if state is None or state.get("user_id") != user_id:
            return None
        return {
            "phase": "answering" if state.get("current_question") else "loading_question",
            "difficulty": state.get("difficulty_level", 3),
            "questionIndex": state.get("question_index", 0),
            "topic": state.get("topic", ""),
            "maxQuestions": state.get("max_questions", DEFAULT_MAX_QUESTIONS),
            "totalQuestions": state.get("total_questions", 0),
            "completed": self._is_completed(state),
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _make_agent(self) -> PracticeAgent:
        """创建 Agent 实例（绑定 checkpointer）。"""
        return PracticeAgent(self.llm, self.practice_repo, _get_checkpointer())

    def _get_state(self, session_id: int, user_id: int) -> PracticeAgentState:
        """获取会话状态（优先内存缓存）。"""
        state = PracticeService._session_cache.get(session_id)
        if state is None or state.get("user_id") != user_id:
            raise SessionNotFoundError()
        return state

    async def _run_and_stream_question(
        self, state: PracticeAgentState, session_key: str, session_id: int, is_first: bool
    ) -> None:
        """通过 Agent graph 运行 validate → generate（在 evaluate 前暂停）。

        将 generate 节点的输出通过 SSE 发送。
        """
        agent = self._make_agent()
        config = {"configurable": {"thread_id": f"practice_{session_id}"}}
        emitter = SSEEmitter(session_key)

        # 计算新的 question_index（仅在非首次时）
        if not is_first:
            next_index = state.get("question_index", 0) + 1
            state["question_index"] = next_index

        # 运行图：validate → generate（interrupt_before=["evaluate"] 确保暂停）
        run_state = state if is_first else None
        try:
            async for event in agent.graph.astream(run_state, config, interrupt_before=["evaluate"]):
                for node_name, node_output in event.items():
                    if node_name == "validate":
                        # 检查验证错误
                        if node_output.get("error"):
                            await emitter.emit("error", {"message": node_output["error"]})
                            return
                    elif node_name == "generate":
                        # 同步到缓存状态
                        for k, v in node_output.items():
                            if v is not None and k != "_pending_record_id":
                                state[k] = v
                        # 记住 pending record id，提交/跳过时用于原地更新
                        rid = node_output.get("_pending_record_id")
                        if rid:
                            PracticeService._pending_record_ids[session_id] = rid

                        # 流式发送题目
                        question_text = state.get("current_question", "")
                        await emitter.emit("question_start", {"questionIndex": state.get("question_index", 0)})
                        for i in range(0, len(question_text), 80):
                            await emitter.emit_text("question_chunk", question_text[i : i + 80])
                        await emitter.emit("question_done", {
                            "question": {
                                "id": f"practice-{session_id}-{state['question_index']}",
                                "content": question_text,
                                "type": state.get("question_type", "short_answer"),
                                "options": None,
                            },
                            "questionIndex": state.get("question_index", 0),
                            "difficulty": state.get("difficulty_level", 3),
                            "referenceAnswer": state.get("reference_answer", ""),
                        })

            # 更新缓存
            final_graph_state = agent.graph.get_state(config)
            if final_graph_state and final_graph_state.values:
                for k, v in final_graph_state.values.items():
                    if v is not None:
                        state[k] = v
            PracticeService._session_cache[session_id] = state

        except Exception as e:
            logger.error(f"Agent graph 执行失败: {e}")
            raise

    async def _load_and_prepare(self, session_id: int, user_id: int) -> PracticeAgentState:
        """从 DB 恢复会话状态（含待答题目检测）。"""
        session = await self.practice_repo.get_session(session_id)
        if session is None or session.user_id != user_id:
            raise SessionNotFoundError()

        # 检查缓存
        cached = PracticeService._session_cache.get(session_id)
        if cached:
            logger.info(f"使用内存缓存 session={session_id}")
            # 缓存命中时仍需检查 DB 是否有待答记录（防止缓存缺失 pending_question）
            pending = await self.practice_repo.get_pending_record(session.id)
            if pending:
                cached["pending_question"] = pending.question
                cached["current_question"] = pending.question
                cached["question_type"] = pending.question_type
                cached["reference_answer"] = pending.reference_answer
                cached["knowledge_points"] = pending.knowledge_points or []
                cached["question_index"] = pending.question_number
                cached["pending_record_id"] = pending.id
                PracticeService._pending_record_ids[session_id] = pending.id
                logger.info(f"缓存命中 + 恢复待答题目 idx={pending.question_number}")
            return cached

        # 从 DB 恢复
        state = PracticeAgent.restore_state(
            session_id=session.id,
            user_id=session.user_id,
            topic=session.topic,
            max_questions=session.max_questions or DEFAULT_MAX_QUESTIONS,
            difficulty_level=session.difficulty_level,
            consecutive_correct=session.consecutive_correct or 0,
            consecutive_wrong=session.consecutive_wrong or 0,
            total_questions=session.total_questions or 0,
            total_correct=session.total_correct or 0,
            status=session.status,
        )

        # 恢复已答题目列表（用于去重）
        records = await self.practice_repo.get_records_by_session(session.id)
        if records:
            state["asked_questions"] = [
                (r.question_number, r.question[:60]) for r in records
            ]

        # 检查待答题目
        pending = await self.practice_repo.get_pending_record(session.id)
        if pending:
            state["pending_question"] = pending.question
            state["current_question"] = pending.question
            state["question_type"] = pending.question_type
            state["reference_answer"] = pending.reference_answer
            state["knowledge_points"] = pending.knowledge_points or []
            state["question_index"] = pending.question_number
            state["pending_record_id"] = pending.id
            PracticeService._pending_record_ids[session_id] = pending.id
            logger.info(f"恢复待答题目 idx={pending.question_number}")

        return state

    @staticmethod
    def _is_completed(state: PracticeAgentState) -> bool:
        if state.get("status") == "completed":
            return True
        if state.get("next_action") == "end":
            return True
        return state.get("total_questions", 0) >= state.get("max_questions", DEFAULT_MAX_QUESTIONS)

    @staticmethod
    def _sse(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"event": event_type, "data": _json.dumps(data, ensure_ascii=False)}
