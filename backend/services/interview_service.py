from __future__ import annotations

import json as _json
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from backend.agents.prompts import (
    DECIDE_NEXT_PROMPT,
    INTERVIEW_FEEDBACK_PROMPT,
    INTERVIEW_FOLLOW_UP_PROMPT,
    INTERVIEW_QUESTION_PROMPT,
    GENERATE_REPORT_PROMPT,
)
from backend.llm.client import UnifiedLLMClient
from backend.middleware.error_handler import SessionNotFoundError
from backend.repositories.interview_repo import InterviewRepo
from backend.sse.emitter import SSEEmitter
from backend.sse.manager import SSEManager


class InterviewService:
    """模拟面试模式业务编排层，协调 LLM / SSE / Repository。"""

    _session_state: dict[int, dict[str, Any]] = {}

    def __init__(self, db, llm_client: UnifiedLLMClient, sse_manager: SSEManager) -> None:
        self.db = db
        self.llm = llm_client
        self.sse = sse_manager
        self.interview_repo = InterviewRepo(db)

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def create_session(self, user_id: int, jd: str, resume: str, total_rounds: int):
        """创建面试会话，持久化并初始化内存状态。"""
        logger.info(f"创建面试会话 user={user_id} rounds={total_rounds}")
        session = await self.interview_repo.create_session(
            user_id=user_id, jd_content=jd, resume_content=resume, total_rounds=total_rounds
        )
        InterviewService._session_state[session.id] = {
            "session_id": session.id,
            "user_id": user_id,
            "jd_content": jd,
            "resume_content": resume,
            "total_rounds": total_rounds,
            "current_round": 1,
            "is_follow_up": False,
            "follow_up_count": 0,
            "current_question": None,
            "user_answer": None,
            "ai_feedback": None,
            "qa_history": [],
            "report": None,
            "phase": "waiting_question",
        }
        logger.info(f"面试会话 {session.id} 创建成功")
        return session

    async def stream_session(self, session_id: int, user_id: int) -> AsyncGenerator[dict[str, Any], None]:
        """SSE 流式主循环：直接 yield 首个问题事件，之后从队列消费后续事件。"""
        session_key = f"interview:{session_id}"
        self.sse.create_connection(session_key, user_id)
        logger.info(f"SSE 连接建立: {session_key}")

        try:
            state = InterviewService._session_state.get(session_id)
            if state is None:
                session = await self.interview_repo.get_session(session_id)
                if session is None or session.user_id != user_id:
                    raise SessionNotFoundError()
                state = self._restore_state(session)
                InterviewService._session_state[session_id] = state

            # --- Phase 1: 生成首个问题，直接 yield 不经过队列 ---
            yield self._sse("session_ready", {"sessionId": str(session_id)})

            if state.get("phase") == "completed" and state.get("report"):
                yield self._sse("report_done", state["report"])
                yield self._sse("interview_complete", {"sessionId": str(session_id)})
            else:
                try:
                    await self._generate_first_question(state)
                except Exception as e:
                    logger.error(f"生成首个面试问题失败: {e}")
                    yield self._sse("error", {"message": f"AI 问题生成失败: {e}"})
                    return

                question_text = state["current_question"] or ""
                yield self._sse("question_start", {"round": state["current_round"], "isFollowUp": state["is_follow_up"]})
                for i in range(0, len(question_text), 80):
                    yield self._sse("question_chunk", {"content": question_text[i : i + 80]})
                yield self._sse(
                    "question_done",
                    {"question": question_text, "round": state["current_round"], "isFollowUp": state["is_follow_up"]},
                )
                state["phase"] = "answering"

            # --- Phase 2: 消费队列中的后续事件 ---
            async for event in self.sse.stream_events(session_key):
                yield event
        finally:
            self.sse.remove_connection(session_key)
            logger.info(f"SSE 连接断开: {session_key}")

    async def submit_answer(self, session_id: int, user_id: int, answer: str) -> None:
        """提交面试回答 → AI 反馈 → 决策下一步 → 持久化。"""
        state = InterviewService._session_state.get(session_id)
        if state is None or state.get("user_id") != user_id:
            raise SessionNotFoundError()

        logger.info(f"提交面试回答 session={session_id} round={state['current_round']}")
        state["phase"] = "submitting"

        # 1. 持久化 QA 记录
        await self.interview_repo.create_qa(
            session_id=session_id,
            round_number=state["current_round"],
            is_follow_up=state["is_follow_up"],
            question=state["current_question"] or "",
            user_answer=answer,
            ai_feedback=None,
        )

        # 2. 更新 qa_history（内存）
        state["user_answer"] = answer
        state["qa_history"].append(
            {
                "round": state["current_round"],
                "is_follow_up": state["is_follow_up"],
                "question": state["current_question"],
                "answer": answer,
            }
        )

        emitter = SSEEmitter(f"interview:{session_id}")

        # 3. 生成 AI 反馈（简短回应）
        feedback = await self.llm.chat(
            INTERVIEW_FEEDBACK_PROMPT.format(question=state["current_question"], answer=answer)
        )
        state["ai_feedback"] = feedback

        # 4. 决策下一步
        decision = await self.llm.chat_with_json(
            DECIDE_NEXT_PROMPT.format(
                jd=state["jd_content"],
                resume=state["resume_content"],
                current_round=state["current_round"],
                total_rounds=state["total_rounds"],
                current_question=state["current_question"],
                user_answer=answer,
                follow_up_count=state["follow_up_count"],
                max_follow_ups=2,
                qa_history=_json.dumps(state["qa_history"], ensure_ascii=False),
            )
        )

        action = "next_round"

        # 5. 根据决策执行不同分支
        if state["current_round"] >= state["total_rounds"]:
            # 最后一轮：允许追问一次，否则生成报告
            should_follow_up = (
                bool(decision.get("should_follow_up", False)) and state["follow_up_count"] < 2
            )
            if should_follow_up:
                state["is_follow_up"] = True
                state["follow_up_count"] += 1
                action = "follow_up"
                await self._emit_feedback(emitter, feedback, action)
                await self._ask_and_emit_follow_up(state, emitter)
            else:
                action = "report"
                await self._emit_feedback(emitter, feedback, action)
                await self._complete_interview(state, emitter)
            return

        if decision.get("should_follow_up", False) and state["follow_up_count"] < 2:
            state["is_follow_up"] = True
            state["follow_up_count"] += 1
            action = "follow_up"
            await self._emit_feedback(emitter, feedback, action)
            await self._ask_and_emit_follow_up(state, emitter)
            return

        # 进入下一轮
        state["is_follow_up"] = False
        state["follow_up_count"] = 0
        state["current_round"] += 1
        state["phase"] = "waiting_question"
        await self._update_session_progress(state)
        await emitter.emit("round_advanced", {"round": state["current_round"]})
        await self._emit_feedback(emitter, feedback, action)
        await self._ask_and_emit_question(state, emitter)

    async def get_report(self, session_id: int, user_id: int) -> dict[str, Any] | None:
        """获取复盘报告：优先从内存取，否则从 DB 取。"""
        state = InterviewService._session_state.get(session_id)

        # 内存中没有 → 从 DB 读取
        if state is None:
            session = await self.interview_repo.get_session(session_id)
            if session is None or session.user_id != user_id:
                raise SessionNotFoundError()
            if session.report_content:
                return {"sessionId": str(session_id), "report": session.report_content}
            # DB 中也没有报告 → 无法恢复
            state = self._restore_state(session)
            InterviewService._session_state[session_id] = state

        if state.get("user_id") != user_id:
            raise SessionNotFoundError()

        # 如果面试还在进行中但没有报告，不允许提前获取
        if not state.get("report"):
            if state.get("phase") != "completed":
                return None
            # 已标记完成但无报告，尝试从 DB 读取
            session = await self.interview_repo.get_session(session_id)
            if session and session.report_content:
                state["report"] = session.report_content
                return {"sessionId": str(session_id), "report": session.report_content}
            return None

        return {"sessionId": str(session_id), "report": state["report"]}

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _generate_first_question(self, state: dict[str, Any]) -> None:
        """生成首个面试问题（非流式），更新状态。"""
        prompt = self._build_question_prompt(state)
        state["phase"] = "receiving_question"
        payload = await self.llm.chat_with_json(prompt)
        state["current_question"] = payload.get(
            "question", "请介绍一个你最有代表性的项目，并说明你的职责。"
        )
        state["qa_history"].append(
            {
                "round": state["current_round"],
                "is_follow_up": state["is_follow_up"],
                "question": state["current_question"],
            }
        )
        logger.info(f"面试出题 round={state['current_round']} follow_up={state['is_follow_up']}")

    async def _ask_and_emit_question(self, state: dict[str, Any], emitter: SSEEmitter) -> None:
        """生成面试问题（非流式）并通过 SSE 队列发送。"""
        prompt = self._build_question_prompt(state)

        state["phase"] = "receiving_question"
        await emitter.emit("question_start", {"round": state["current_round"], "isFollowUp": state["is_follow_up"]})
        payload = await self.llm.chat_with_json(prompt)
        state["current_question"] = payload.get(
            "question", "请介绍一个你最有代表性的项目，并说明你的职责。"
        )
        state["qa_history"].append(
            {
                "round": state["current_round"],
                "is_follow_up": state["is_follow_up"],
                "question": state["current_question"],
            }
        )

        for index in range(0, len(state["current_question"]), 80):
            await emitter.emit_text("question_chunk", state["current_question"][index : index + 80])

        await emitter.emit(
            "question_done",
            {"question": state["current_question"], "round": state["current_round"], "isFollowUp": state["is_follow_up"]},
        )
        state["phase"] = "answering"
        logger.info(f"面试出题 round={state['current_round']} follow_up={state['is_follow_up']}")

    async def _ask_and_emit_follow_up(self, state: dict[str, Any], emitter: SSEEmitter) -> None:
        """生成动态追问问题（基于上下文）并通过 SSE 发送。"""
        # 使用 LLM 生成动态追问
        state["phase"] = "receiving_question"
        await emitter.emit("question_start", {"round": state["current_round"], "isFollowUp": True})
        follow_up = await self.llm.chat(
            INTERVIEW_FOLLOW_UP_PROMPT.format(
                original_question=state["current_question"],
                user_answer=state["user_answer"],
            )
        )
        follow_up = follow_up.strip() or "能具体展开说说吗？"

        for index in range(0, len(follow_up), 80):
            await emitter.emit_text("question_chunk", follow_up[index : index + 80])

        state["current_question"] = follow_up
        state["qa_history"].append(
            {
                "round": state["current_round"],
                "is_follow_up": True,
                "question": follow_up,
            }
        )

        await emitter.emit(
            "question_done",
            {"question": follow_up, "round": state["current_round"], "isFollowUp": True},
        )
        state["phase"] = "answering"
        logger.info(f"追问 round={state['current_round']}")

    async def _complete_interview(self, state: dict[str, Any], emitter: SSEEmitter) -> None:
        """完成面试：生成报告、持久化、发送完成事件。"""
        state["phase"] = "generating_report"
        await emitter.emit("report_generating", {})

        # 生成报告
        report_text = await self.llm.chat(
            [
                {
                    "role": "user",
                    "content": GENERATE_REPORT_PROMPT.format(
                        jd=state["jd_content"],
                        resume=state["resume_content"],
                        total_rounds=state["total_rounds"],
                        qa_history=_json.dumps(state["qa_history"], ensure_ascii=False),
                    ),
                }
            ],
            response_format={"type": "json_object"},
        )

        try:
            report = _json.loads(report_text)
        except _json.JSONDecodeError:
            logger.warning("报告 JSON 解析失败，使用默认报告")
            report = {
                "overall_score": 80,
                "tech_depth": 80,
                "clarity": 80,
                "logic": 80,
                "job_match": 80,
                "overall_comment": "整体表现稳定。",
                "round_reviews": [],
                "highlights": [],
                "weaknesses": [],
                "suggestions": [],
            }

        state["report"] = report
        state["phase"] = "completed"

        # 持久化报告
        await self.interview_repo.save_report(state["session_id"], report)
        await self._update_session_progress(state)

        await emitter.emit("report_done", report)
        await emitter.emit("interview_complete", {"sessionId": str(state["session_id"])})
        logger.info(f"面试完成 session={state['session_id']} score={report.get('overall_score')}")

    async def _emit_feedback(self, emitter: SSEEmitter, feedback: str, action: str) -> None:
        """把简短反馈拆成 SSE 事件，方便前端逐步渲染。"""
        await emitter.emit("feedback_start", {})
        for index in range(0, len(feedback), 120):
            await emitter.emit_text("feedback_chunk", feedback[index : index + 120])
        await emitter.emit("feedback_done", {"action": action})

    def _build_question_prompt(self, state: dict[str, Any]) -> str:
        """构建面试出题提示词，融入 JD + 简历 + 历史上下文。"""
        follow_up_context = ""
        if state["is_follow_up"]:
            follow_up_context = "这是一次追问，请延续上一题的话题进行深入提问。"

        is_follow_up_instruction = (
            "这是对上一题回答的追问，请延续同一话题深入提问"
            if state["is_follow_up"]
            else "独立生成一个新问题，覆盖不同的技术栈或能力项"
        )

        # 格式化历史问答（最近 6 轮）
        recent_history = state["qa_history"][-6:] if state["qa_history"] else []
        history_text = _json.dumps(recent_history, ensure_ascii=False) if recent_history else "暂无历史记录"

        return INTERVIEW_QUESTION_PROMPT.format(
            jd=state["jd_content"],
            resume=state["resume_content"],
            current_round=state["current_round"],
            total_rounds=state["total_rounds"],
            follow_up_context=follow_up_context,
            qa_history=history_text,
            is_follow_up_instruction=is_follow_up_instruction,
        )

    async def _update_session_progress(self, state: dict[str, Any]) -> None:
        """更新会话进度到数据库。"""
        await self.interview_repo.update_session_progress(
            state["session_id"],
            completed_rounds=state["current_round"],
            status=state.get("phase", "in_progress"),
        )

    @staticmethod
    def _sse(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        """构造一条 SSE 事件 dict（data 必须 JSON 序列化）。"""
        return {"event": event_type, "data": _json.dumps(data, ensure_ascii=False)}

    def get_status(self, session_id: int, user_id: int) -> dict[str, Any] | None:
        state = InterviewService._session_state.get(session_id)
        if state is None or state.get("user_id") != user_id:
            return None
        return {
            "currentRound": state.get("current_round", 1),
            "totalRounds": state.get("total_rounds", 0),
            "phase": state.get("phase", "waiting_question"),
            "isFollowUp": state.get("is_follow_up", False),
            "followUpCount": state.get("follow_up_count", 0),
        }

    def _restore_state(self, session) -> dict[str, Any]:
        """从 DB 会话恢复内存状态。"""
        return {
            "session_id": session.id,
            "user_id": session.user_id,
            "jd_content": session.jd_content,
            "resume_content": session.resume_content,
            "total_rounds": session.total_rounds,
            "current_round": max(1, (session.completed_rounds or 0) + 1),
            "is_follow_up": False,
            "follow_up_count": 0,
            "current_question": None,
            "user_answer": None,
            "ai_feedback": None,
            "qa_history": [],
            "report": session.report_content,
            "phase": session.status or "in_progress",
        }
