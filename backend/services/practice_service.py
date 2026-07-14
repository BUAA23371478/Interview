from __future__ import annotations

import json as _json
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from backend.agents.prompts import EVALUATE_PROMPT, GENERATE_QUESTION_PROMPT, VALIDATE_TOPIC_PROMPT
from backend.database.connection import async_session
from backend.llm.client import UnifiedLLMClient
from backend.middleware.error_handler import SessionNotFoundError, TopicValidationError
from backend.repositories.practice_repo import PracticeRepo
from backend.sse.emitter import SSEEmitter
from backend.sse.manager import SSEManager

DEFAULT_MAX_QUESTIONS = 20


class PracticeService:
    """刷题模式业务编排层。"""

    _session_state: dict[int, dict[str, Any]] = {}
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
        logger.info(f"创建刷题会话 user={user_id} topic={topic} max_q={max_questions}")

        validation = await self.llm.chat_with_json(
            [{"role": "user", "content": VALIDATE_TOPIC_PROMPT.format(topic=topic)}]
        )
        if not validation.get("is_valid", False):
            raise TopicValidationError(validation.get("reason", "请输入技术面试相关主题"))

        session = await self.practice_repo.create_session(
            user_id=user_id, topic=topic, difficulty_level=3, max_questions=max_questions,
        )

        PracticeService._session_state[session.id] = {
            "session_id": session.id, "user_id": user_id, "topic": topic,
            "max_questions": max_questions, "phase": "loading_question",
            "current_question": None, "question_type": None, "reference_answer": None,
            "knowledge_points": [], "user_answer": None, "score": None,
            "is_correct": None, "feedback": None, "difficulty_level": session.difficulty_level,
            "consecutive_correct": 0, "consecutive_wrong": 0,
            "question_index": 0, "total_correct": 0, "total_questions": 0,
            "asked_questions": [],
        }
        logger.info(f"刷题会话 {session.id} 创建成功")
        return session

    # ==================================================================
    # SSE stream：Phase 1 持有短生命期 DB → Phase 2 释放
    # ==================================================================

    async def stream_session(self, session_id: int, user_id: int) -> AsyncGenerator[dict[str, Any], None]:
        session_key = f"practice:{session_id}"
        self.sse.create_connection(session_key, user_id)
        logger.info(f"SSE 连接建立: {session_key}")

        try:
            # ====== Phase 1: 短生命期 DB session（恢复 + 首题） ======
            async with async_session() as db:
                self.practice_repo = PracticeRepo(db)

                # 每次连接强制从 DB 恢复，避免使用可能过期的内存缓存
                state = await self._load_and_restore(session_id, user_id)
                PracticeService._session_state[session_id] = state

                yield self._sse("session_ready", {"sessionId": str(session_id), "maxQuestions": state.get("max_questions", DEFAULT_MAX_QUESTIONS)})

                if self._is_completed(state):
                    logger.info(f"会话已完成 session={session_id}")
                    yield self._sse("session_completed", {"message": "本会话已达题目上限"})
                    await db.commit()
                    async for event in self.sse.stream_events(session_key):
                        yield event
                    return

                pending = state.get("pending_question")
                pending_record_id = state.get("pending_record_id")
                if pending and pending_record_id:
                    logger.info(f"[SSE] 恢复待答题目 idx={state['question_index']}")
                    PracticeService._pending_record_ids[session_id] = pending_record_id
                    yield self._sse("question_start", {"questionIndex": state["question_index"]})
                    for i in range(0, len(pending), 80):
                        yield self._sse("question_chunk", {"content": pending[i : i + 80]})
                    yield self._sse("question_done", {
                        "question": {"id": f"practice-{session_id}-{state['question_index']}", "content": pending, "type": state.get("question_type", "short_answer"), "options": None},
                        "questionIndex": state["question_index"], "difficulty": state.get("difficulty_level", 3),
                        "referenceAnswer": state.get("reference_answer", ""),
                    })
                    state["phase"] = "answering"
                    state.pop("pending_question", None)
                else:
                    yield self._sse("question_start", {"questionIndex": state.get("question_index", 0) + 1})
                    try:
                        logger.info(f"[SSE] 生成首题 session={session_id}")
                        await self._generate_question(state)
                        logger.info(f"[SSE] 首题完成 len={len(state.get('current_question', ''))}")
                    except Exception as e:
                        logger.error(f"生成首题失败: {e}")
                        yield self._sse("error", {"message": f"AI 题目生成失败: {e}"})
                        await db.rollback()
                        return

                    question_text = state["current_question"] or ""
                    for i in range(0, len(question_text), 80):
                        yield self._sse("question_chunk", {"content": question_text[i : i + 80]})
                    yield self._sse("question_done", {
                        "question": {"id": f"practice-{session_id}-{state['question_index']}", "content": question_text, "type": state.get("question_type", "short_answer"), "options": None},
                        "questionIndex": state["question_index"], "difficulty": state.get("difficulty_level", 3),
                        "referenceAnswer": state.get("reference_answer", ""),
                    })
                    state["phase"] = "answering"

                await db.commit()
            # ====== DB session 已释放，后续 POST 正常写入 ======

            # ====== Phase 2: 队列消费（不持有 DB） ======
            async for event in self.sse.stream_events(session_key):
                yield event

        finally:
            self.sse.remove_connection(session_key)
            logger.info(f"SSE 连接断开: {session_key}")

    # ==================================================================
    # POST 端点（各自独立的短生命期 DB session）
    # ==================================================================

    async def submit_answer(self, session_id: int, user_id: int, answer: str, time_spent_seconds: int | None) -> None:
        state = PracticeService._session_state.get(session_id)
        if state is None or state.get("user_id") != user_id:
            raise SessionNotFoundError()

        logger.info(f"提交答案 session={session_id} q={state['question_index']}")
        state["user_answer"] = answer
        state["phase"] = "submitting"

        evaluation = await self.llm.chat_with_json(
            EVALUATE_PROMPT.format(topic=state["topic"], question=state["current_question"],
                                   reference_answer=state["reference_answer"], user_answer=answer)
        )

        state["score"] = float(evaluation.get("score", 0))
        state["is_correct"] = bool(evaluation.get("is_correct", state["score"] >= 60))
        state["feedback"] = {
            "score": state["score"], "isCorrect": state["is_correct"],
            "correctAnswer": evaluation.get("correct_answer") or state["reference_answer"] or "",
            "analysis": evaluation.get("analysis") or "",
            "knowledgePoints": evaluation.get("knowledge_points") or state["knowledge_points"] or [],
            "commonMistakes": evaluation.get("common_mistakes") or [],
        }
        state["total_questions"] = state.get("total_questions", 0) + 1
        if state["is_correct"]:
            state["total_correct"] = state.get("total_correct", 0) + 1

        self._adjust_difficulty(state)

        analysis_text = state["feedback"].get("analysis", "") if isinstance(state["feedback"], dict) else ""
        pending_id = PracticeService._pending_record_ids.pop(session_id, None)
        if pending_id:
            await self.practice_repo.update_record_answer(
                pending_id, user_answer=answer, score=state["score"],
                is_correct=state["is_correct"], feedback=analysis_text,
                time_spent_seconds=time_spent_seconds,
            )
        else:
            await self.practice_repo.create_record(
                session_id=session_id, question_number=state["question_index"],
                question=state["current_question"] or "", question_type=state["question_type"] or "short_answer",
                reference_answer=state["reference_answer"] or "", user_answer=answer,
                score=state["score"], is_correct=state["is_correct"],
                feedback=analysis_text, knowledge_points=state["knowledge_points"],
                time_spent_seconds=time_spent_seconds,
            )

        completed = state["total_questions"] >= state.get("max_questions", DEFAULT_MAX_QUESTIONS)
        await self.practice_repo.update_session_stats(
            session_id,
            **({"status": "completed"} if completed else {}),
            consecutive_correct=state["consecutive_correct"],
            consecutive_wrong=state["consecutive_wrong"],
            difficulty_level=state["difficulty_level"],
            total_questions=state["total_questions"],
            total_correct=state["total_correct"],
        )

        emitter = SSEEmitter(f"practice:{session_id}")
        await emitter.emit("feedback_start", {"questionIndex": state["question_index"]})
        if analysis_text:
            for i in range(0, len(analysis_text), 120):
                await emitter.emit_text("feedback_chunk", analysis_text[i : i + 120])
        await emitter.emit("feedback_done", {
            "score": state["score"], "is_correct": state["is_correct"],
            "feedback": state["feedback"], "completed": completed,
        })
        state["phase"] = "feedback_shown"
        logger.info(f"评估完成 session={session_id} score={state['score']} completed={completed}")

    async def request_next(self, session_id: int, user_id: int) -> None:
        state = PracticeService._session_state.get(session_id)
        if state is None or state.get("user_id") != user_id:
            raise SessionNotFoundError()

        logger.info(f"请求下一题 session={session_id}")
        emitter = SSEEmitter(f"practice:{session_id}")

        if self._is_completed(state):
            await emitter.emit("session_completed", {"message": "本会话已达题目上限"})
            return

        state["phase"] = "loading_question"
        try:
            await self._generate_question(state)
        except Exception as e:
            logger.error(f"生成下一题失败: {e}")
            await emitter.emit("error", {"message": f"AI 题目生成失败: {e}"})
            return

        question_text = state["current_question"] or ""
        await emitter.emit("question_start", {"questionIndex": state["question_index"]})
        for i in range(0, len(question_text), 80):
            await emitter.emit_text("question_chunk", question_text[i : i + 80])
        await emitter.emit("question_done", {
            "question": {"id": f"practice-{session_id}-{state['question_index']}", "content": question_text, "type": state.get("question_type", "short_answer"), "options": None},
            "questionIndex": state["question_index"], "difficulty": state.get("difficulty_level", 3),
            "referenceAnswer": state.get("reference_answer", ""),
        })
        state["phase"] = "answering"

    async def skip_question(self, session_id: int, user_id: int) -> None:
        """不了解：不调 LLM 评估，直接标记为跳过，推送参考答案。"""
        state = PracticeService._session_state.get(session_id)
        if state is None or state.get("user_id") != user_id:
            raise SessionNotFoundError()

        logger.info(f"跳过题目 session={session_id} q={state['question_index']}")
        state["phase"] = "submitting"

        # 更新 pending record 为"不了解"
        pending_id = PracticeService._pending_record_ids.pop(session_id, None)
        if pending_id:
            await self.practice_repo.update_record_answer(
                pending_id, user_answer="不了解", score=0, is_correct=False,
                feedback="", time_spent_seconds=0,
            )
        else:
            await self.practice_repo.create_record(
                session_id=session_id, question_number=state["question_index"],
                question=state["current_question"] or "", question_type=state.get("question_type", "short_answer"),
                reference_answer=state.get("reference_answer", "") or "", user_answer="不了解",
                score=0, is_correct=False, feedback="", knowledge_points=state["knowledge_points"],
                time_spent_seconds=0,
            )

        state["total_questions"] = state.get("total_questions", 0) + 1
        state["feedback"] = {
            "score": 0, "isCorrect": False,
            "correctAnswer": state.get("reference_answer", ""),
            "analysis": "", "knowledgePoints": state.get("knowledge_points", []),
            "commonMistakes": [],
        }

        completed = state["total_questions"] >= state.get("max_questions", DEFAULT_MAX_QUESTIONS)
        await self.practice_repo.update_session_stats(
            session_id,
            **({"status": "completed"} if completed else {}),
            total_questions=state["total_questions"],
            total_correct=state.get("total_correct", 0),
        )

        # SSE 推送参考答案
        emitter = SSEEmitter(f"practice:{session_id}")
        ref = state.get("reference_answer", "") or ""
        await emitter.emit("feedback_start", {"questionIndex": state["question_index"]})
        if ref:
            for i in range(0, len(ref), 120):
                await emitter.emit_text("feedback_chunk", ref[i : i + 120])
        await emitter.emit("feedback_done", {
            "score": 0, "is_correct": False,
            "feedback": state["feedback"], "completed": completed, "skipped": True,
        })
        state["phase"] = "feedback_shown"
        logger.info(f"跳过完成 session={session_id}")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    async def _load_and_restore(self, session_id: int, user_id: int) -> dict[str, Any]:
        session = await self.practice_repo.get_session(session_id)
        if session is None or session.user_id != user_id:
            raise SessionNotFoundError()

        state = self._restore_state(session)
        records = await self.practice_repo.get_records_by_session(session.id)
        if records:
            state["asked_questions"] = [(r.question_number, r.question[:60]) for r in records if r.user_answer]

        pending = await self.practice_repo.get_pending_record(session.id)
        if pending:
            state["pending_question"] = pending.question
            state["current_question"] = pending.question
            state["question_type"] = pending.question_type
            state["reference_answer"] = pending.reference_answer
            state["knowledge_points"] = pending.knowledge_points or []
            state["question_index"] = pending.question_number
            state["pending_record_id"] = pending.id
            state["total_questions"] = sum(1 for r in records if r.user_answer)
            logger.info(f"恢复待答题目 idx={pending.question_number} rid={pending.id}")
        else:
            state["question_index"] = session.total_questions or 0
            state["total_questions"] = session.total_questions or 0
            state["total_correct"] = session.total_correct or 0

        return state

    async def _generate_question(self, state: dict[str, Any]) -> str:
        if self._is_completed(state):
            raise RuntimeError("会话已完成")

        # 如果已有待答题目，不允许生成新题（必须先回答或跳过当前题）
        existing_pending = await self.practice_repo.get_pending_record(state["session_id"])
        if existing_pending:
            raise RuntimeError(f"已有待答题目 q={existing_pending.question_number}，请先回答")

        next_index = max(1, state["question_index"] + 1)
        prompt = self._build_question_prompt_for_index(state, next_index)
        payload = await self.llm.chat_with_json(prompt)

        question_text = payload.get("question", "请简述该主题的核心概念。")
        question_type = payload.get("question_type", "short_answer")
        reference_answer = payload.get("reference_answer", "请结合定义、原理和场景作答。")
        knowledge_points = payload.get("knowledge_points", [])

        # 先写 DB，成功后再更新内存
        record = await self.practice_repo.create_pending_record(
            session_id=state["session_id"], question_number=next_index,
            question=question_text, question_type=question_type,
            reference_answer=reference_answer, knowledge_points=knowledge_points,
        )

        state["question_index"] = next_index
        state["current_question"] = question_text
        state["question_type"] = question_type
        state["reference_answer"] = reference_answer
        state["knowledge_points"] = knowledge_points
        state.setdefault("asked_questions", []).append((next_index, question_text[:60]))
        PracticeService._pending_record_ids[state["session_id"]] = record.id
        logger.info(f"pending record id={record.id} q={next_index}")
        return question_text

    def _build_question_prompt_for_index(self, state: dict[str, Any], next_index: int) -> str:
        asked = state.get("asked_questions", [])
        dedup_section = ""
        if asked:
            lines = "\n".join(f"  {q}. {p}..." for q, p in asked[-20:])
            dedup_section = f"\n⚠️ 已出题目，绝对不要重复出题（可换考点或角度）：\n{lines}"

        return GENERATE_QUESTION_PROMPT.format(
            topic=state["topic"], difficulty=state["difficulty_level"],
            question_index=next_index,
            history_summary=f"已答题数: {state.get('total_questions', 0)}, 正确率: {self._accuracy(state)}{dedup_section}",
        )

    @staticmethod
    def _accuracy(state: dict[str, Any]) -> str:
        total = state.get("total_questions", 0)
        if total == 0:
            return "N/A"
        return f"{round(state.get('total_correct', 0) / total * 100)}%"

    @staticmethod
    def _is_completed(state: dict[str, Any]) -> bool:
        if state.get("status") == "completed":
            return True
        return state.get("total_questions", 0) >= state.get("max_questions", DEFAULT_MAX_QUESTIONS)

    @staticmethod
    def _adjust_difficulty(state: dict[str, Any]) -> None:
        if state["is_correct"]:
            state["consecutive_correct"] = state.get("consecutive_correct", 0) + 1
            state["consecutive_wrong"] = 0
            if state["consecutive_correct"] >= 3:
                state["difficulty_level"] = min(5, state["difficulty_level"] + 1)
                state["consecutive_correct"] = 0
        else:
            state["consecutive_wrong"] = state.get("consecutive_wrong", 0) + 1
            state["consecutive_correct"] = 0
            if state["consecutive_wrong"] >= 2:
                state["difficulty_level"] = max(1, state["difficulty_level"] - 1)
                state["consecutive_wrong"] = 0

    def _restore_state(self, session) -> dict[str, Any]:
        return {
            "session_id": session.id, "user_id": session.user_id, "topic": session.topic,
            "max_questions": session.max_questions or DEFAULT_MAX_QUESTIONS,
            "phase": "loading_question", "current_question": None, "question_type": None,
            "reference_answer": None, "knowledge_points": [],
            "difficulty_level": session.difficulty_level,
            "consecutive_correct": session.consecutive_correct or 0,
            "consecutive_wrong": session.consecutive_wrong or 0,
            "question_index": session.total_questions or 0,
            "total_correct": session.total_correct or 0,
            "total_questions": session.total_questions or 0,
            "score": None, "is_correct": None, "feedback": None, "user_answer": None,
            "asked_questions": [], "status": session.status,
        }

    def get_status(self, session_id: int, user_id: int) -> dict[str, Any] | None:
        state = PracticeService._session_state.get(session_id)
        if state is None or state.get("user_id") != user_id:
            return None
        return {
            "phase": state.get("phase", "loading_question"),
            "difficulty": state.get("difficulty_level", 3),
            "questionIndex": state.get("question_index", 0),
            "topic": state.get("topic", ""),
            "maxQuestions": state.get("max_questions", DEFAULT_MAX_QUESTIONS),
            "totalQuestions": state.get("total_questions", 0),
            "completed": self._is_completed(state),
        }

    @staticmethod
    def _sse(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"event": event_type, "data": _json.dumps(data, ensure_ascii=False)}
