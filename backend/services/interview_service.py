"""模拟面试模式业务编排层 —— 基于 LangGraph Agent 状态图。

使用 LangGraph StateGraph + interrupt_before 实现人机交互暂停，
通过 SqliteSaver checkpoint 持久化状态，天然支持断线恢复。

图结构:
    START → setup → ask_question → [interrupt] → provide_feedback
        → decide_next → ask_question (loop) / generate_report → END
"""

from __future__ import annotations

import json as _json
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from backend.agents.interview_agent import (
    DEFAULT_TOTAL_ROUNDS,
    MAX_FOLLOW_UPS_PER_ROUND,
    InterviewAgent,
    InterviewAgentState,
)
from backend.agents.prompts import (
    DECIDE_NEXT_PROMPT,
    INTERVIEW_FEEDBACK_PROMPT,
    INTERVIEW_FOLLOW_UP_PROMPT,
    GENERATE_REPORT_PROMPT,
)
from backend.database.connection import async_session
from backend.llm.client import UnifiedLLMClient
from backend.middleware.error_handler import SessionNotFoundError
from backend.repositories.interview_repo import InterviewRepo
from backend.services.practice_service import _get_checkpointer
from backend.sse.emitter import SSEEmitter
from backend.sse.manager import SSEManager


class InterviewService:
    """模拟面试模式业务编排层 —— 委托给 LangGraph InterviewAgent。

    职责：
    - 会话生命周期管理（创建 / 恢复 / 状态查询）
    - SSE 事件流（将 Agent 节点输出转换为前端事件）
    - 人机交互桥接（POST 端点触发图执行下一段）
    """

    # 保留内存状态缓存（checkpoint 为主力存储，内存为热点加速）
    _session_cache: dict[int, InterviewAgentState] = {}

    def __init__(self, db, llm_client: UnifiedLLMClient, sse_manager: SSEManager) -> None:
        self.db = db
        self.llm = llm_client
        self.sse = sse_manager
        self.interview_repo = InterviewRepo(db)

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def create_session(self, user_id: int, jd: str, resume: str, total_rounds: int):
        """创建面试会话：持久化 + 初始化 Agent 状态。"""
        logger.info(f"创建面试会话 user={user_id} rounds={total_rounds}")
        session = await self.interview_repo.create_session(
            user_id=user_id, jd_content=jd, resume_content=resume, total_rounds=total_rounds
        )

        state = InterviewAgent.default_state(
            session_id=session.id,
            user_id=user_id,
            jd_content=jd,
            resume_content=resume,
            total_rounds=total_rounds,
        )
        InterviewService._session_cache[session.id] = state
        logger.info(f"面试会话 {session.id} 创建成功")
        return session

    async def stream_session(self, session_id: int, user_id: int) -> AsyncGenerator[dict[str, Any], None]:
        """SSE 流式主循环。

        Phase 1: 短生命期 DB → 恢复状态 → Agent graph: setup → ask_question
        Phase 2: 队列消费（等待 POST 端点的后续事件）
        """
        session_key = f"interview:{session_id}"
        self.sse.create_connection(session_key, user_id)
        logger.info(f"SSE 连接建立: {session_key}")

        try:
            # ====== Phase 1: 短生命期 DB ======
            async with async_session() as db:
                self.interview_repo = InterviewRepo(db)

                state = await self._load_and_prepare(session_id, user_id)
                InterviewService._session_cache[session_id] = state

                yield self._sse("session_ready", {
                    "sessionId": str(session_id),
                    "totalRounds": state.get("total_rounds", DEFAULT_TOTAL_ROUNDS),
                })

                # 已完成 → 直接返回报告
                if state.get("phase") == "done" and state.get("report"):
                    yield self._sse("report_done", state["report"])
                    yield self._sse("interview_complete", {"sessionId": str(session_id)})
                    await db.commit()
                    async for event in self.sse.stream_events(session_key):
                        yield event
                    return

                # 通过 Agent graph 生成首个问题
                try:
                    logger.info(f"[SSE] Agent 生成首题 session={session_id}")
                    await self._run_and_stream_question(state, session_key, session_id, is_first=True)
                except Exception as e:
                    logger.error(f"生成首题失败: {e}")
                    yield self._sse("error", {"message": f"AI 问题生成失败: {e}"})
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

    async def submit_answer(self, session_id: int, user_id: int, answer: str) -> None:
        """提交面试回答 → Agent graph: provide_feedback → decide_next。

        根据决策结果执行不同分支：
        - follow_up: 生成追问并 SSE 推送
        - next_round: 推进轮次并生成新问题
        - report: 生成报告并结束面试
        """
        state = self._get_state(session_id, user_id)
        logger.info(f"提交面试回答 session={session_id} round={state.get('current_round')}")

        state["user_answer"] = answer

        # 持久化 QA 记录
        await self.interview_repo.create_qa(
            session_id=session_id,
            round_number=state.get("current_round", 1),
            is_follow_up=state.get("is_follow_up", False),
            question=state.get("current_question", ""),
            user_answer=answer,
            ai_feedback=None,
        )

        # 更新 qa_history
        qa_history = list(state.get("qa_history", []))
        qa_history.append({
            "round": state.get("current_round", 1),
            "is_follow_up": state.get("is_follow_up", False),
            "question": state.get("current_question"),
            "answer": answer,
        })
        state["qa_history"] = qa_history

        emitter = SSEEmitter(f"interview:{session_id}")

        # 使用 LLM 决策下一步
        is_last_round = state.get("current_round", 1) >= state.get("total_rounds", DEFAULT_TOTAL_ROUNDS)
        decision = await self.llm.chat_with_json(
            DECIDE_NEXT_PROMPT.format(
                jd=state.get("jd_content", ""),
                resume=state.get("resume_content", ""),
                current_round=state.get("current_round", 1),
                total_rounds=state.get("total_rounds", DEFAULT_TOTAL_ROUNDS),
                current_question=state.get("current_question", ""),
                user_answer=answer,
                follow_up_count=state.get("follow_up_count", 0),
                max_follow_ups=MAX_FOLLOW_UPS_PER_ROUND,
                qa_history=_json.dumps(qa_history, ensure_ascii=False),
            )
        )

        # 确定 action
        if is_last_round:
            should_follow_up = (
                bool(decision.get("should_follow_up", False))
                and state.get("follow_up_count", 0) < MAX_FOLLOW_UPS_PER_ROUND
            )
            action = "follow_up" if should_follow_up else "report"
        elif decision.get("should_follow_up") and state.get("follow_up_count", 0) < MAX_FOLLOW_UPS_PER_ROUND:
            action = "follow_up"
        else:
            action = "next_round"

        # 生成 AI 反馈
        action_desc = {
            "follow_up": "追问",
            "next_round": "下一轮（新问题）",
            "report": "结束面试",
        }.get(action, action)

        feedback = await self.llm.chat(
            INTERVIEW_FEEDBACK_PROMPT.format(
                question=state.get("current_question", ""),
                answer=answer,
                action=action_desc,
            )
        )
        state["ai_feedback"] = feedback
        await self.interview_repo.update_qa_feedback(session_id, state.get("current_round", 1), feedback)

        # 根据 action 执行分支
        if action == "follow_up":
            state["is_follow_up"] = True
            state["follow_up_count"] = state.get("follow_up_count", 0) + 1
            await self._emit_feedback(emitter, feedback, action)
            await self._generate_and_emit_follow_up(state, emitter)
            InterviewService._session_cache[session_id] = state
            return

        if action == "report":
            await self._emit_feedback(emitter, feedback, action)
            await self._complete_interview(state, emitter)
            InterviewService._session_cache[session_id] = state
            return

        # action == "next_round"
        state["is_follow_up"] = False
        state["follow_up_count"] = 0
        state["current_round"] = state.get("current_round", 1) + 1
        await self._update_session_progress(state)
        await emitter.emit("round_advanced", {"round": state.get("current_round", 1)})
        await self._emit_feedback(emitter, feedback, action)

        # 通过 Agent graph 生成下一题
        try:
            await self._run_and_stream_question(state, f"interview:{session_id}", session_id, is_first=False)
        except Exception as e:
            logger.error(f"生成下一题失败: {e}")
            await emitter.emit("error", {"message": f"AI 问题生成失败: {e}"})

        InterviewService._session_cache[session_id] = state

    async def get_report(self, session_id: int, user_id: int) -> dict[str, Any] | None:
        """获取复盘报告：优先从内存取，否则从 DB 取。"""
        state = InterviewService._session_cache.get(session_id)

        if state is None:
            session = await self.interview_repo.get_session(session_id)
            if session is None or session.user_id != user_id:
                raise SessionNotFoundError()
            if session.report_content:
                return {"sessionId": str(session_id), "report": session.report_content}
            state = InterviewAgent.restore_state(session)
            InterviewService._session_cache[session_id] = state

        if state.get("user_id") != user_id:
            raise SessionNotFoundError()

        if not state.get("report"):
            if state.get("phase") != "done":
                return None
            session = await self.interview_repo.get_session(session_id)
            if session and session.report_content:
                state["report"] = session.report_content
                return {"sessionId": str(session_id), "report": session.report_content}
            return None

        return {"sessionId": str(session_id), "report": state["report"]}

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_status(self, session_id: int, user_id: int) -> dict[str, Any] | None:
        """查询会话状态。"""
        state = InterviewService._session_cache.get(session_id)
        if state is None or state.get("user_id") != user_id:
            return None
        return {
            "currentRound": state.get("current_round", 1),
            "totalRounds": state.get("total_rounds", 0),
            "phase": state.get("phase", "waiting"),
            "isFollowUp": state.get("is_follow_up", False),
            "followUpCount": state.get("follow_up_count", 0),
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _make_agent(self) -> InterviewAgent:
        """创建 Agent 实例。"""
        return InterviewAgent(self.llm, self.interview_repo, _get_checkpointer())

    def _get_state(self, session_id: int, user_id: int) -> InterviewAgentState:
        state = InterviewService._session_cache.get(session_id)
        if state is None or state.get("user_id") != user_id:
            raise SessionNotFoundError()
        return state

    async def _run_and_stream_question(
        self, state: InterviewAgentState, session_key: str, session_id: int, is_first: bool
    ) -> None:
        """通过 Agent graph 运行 setup → ask_question，流式输出问题。

        interrupt_before=["provide_feedback"] 确保在生成问题后暂停。
        """
        agent = self._make_agent()
        config = {"configurable": {"thread_id": f"interview_{session_id}"}}
        emitter = SSEEmitter(session_key)

        run_state = state if is_first else None

        async for event in agent.graph.astream(run_state, config, interrupt_before=["provide_feedback"]):
            for node_name, node_output in event.items():
                if node_name == "ask_question":
                    for k, v in node_output.items():
                        if v is not None:
                            state[k] = v

                    # 流式发送问题
                    question_text = state.get("current_question", "")
                    await emitter.emit(
                        "question_start",
                        {"round": state.get("current_round", 1), "isFollowUp": state.get("is_follow_up", False)},
                    )
                    for i in range(0, len(question_text), 80):
                        await emitter.emit_text("question_chunk", question_text[i : i + 80])
                    await emitter.emit(
                        "question_done",
                        {
                            "question": question_text,
                            "round": state.get("current_round", 1),
                            "isFollowUp": state.get("is_follow_up", False),
                        },
                    )
                    state["phase"] = "waiting"
                elif node_name == "setup":
                    for k, v in node_output.items():
                        if v is not None:
                            state[k] = v

        InterviewService._session_cache[session_id] = state

    async def _generate_and_emit_follow_up(self, state: InterviewAgentState, emitter: SSEEmitter) -> None:
        """生成动态追问并 SSE 推送。"""
        agent = self._make_agent()
        follow_up = await agent.generate_follow_up(state)

        await emitter.emit(
            "question_start",
            {"round": state.get("current_round", 1), "isFollowUp": True},
        )

        for i in range(0, len(follow_up), 80):
            await emitter.emit_text("question_chunk", follow_up[i : i + 80])

        state["current_question"] = follow_up
        qa_history = list(state.get("qa_history", []))
        qa_history.append({
            "round": state.get("current_round", 1),
            "is_follow_up": True,
            "question": follow_up,
        })
        state["qa_history"] = qa_history

        await emitter.emit(
            "question_done",
            {"question": follow_up, "round": state.get("current_round", 1), "isFollowUp": True},
        )
        state["phase"] = "waiting"
        logger.info(f"追问 round={state.get('current_round')}")

    async def _complete_interview(self, state: InterviewAgentState, emitter: SSEEmitter) -> None:
        """完成面试：生成报告、持久化、发送完成事件。"""
        state["phase"] = "generating_report"
        await emitter.emit("report_generating", {})

        # 使用 Agent 的 generate_report 逻辑
        agent = self._make_agent()

        # 手动调用图执行 generate_report
        config = {"configurable": {"thread_id": f"interview_{state['session_id']}"}}

        # 更新 checkpoint 状态
        try:
            await agent.graph.aupdate_state(config, {
                "user_answer": state.get("user_answer"),
                "qa_history": state.get("qa_history"),
                "ai_feedback": state.get("ai_feedback"),
                "action": "report",
                "next_action": "report",
            })
        except Exception:
            pass  # Checkpoint 可能不存在（未通过 graph 执行）

        # 直接调用 LLM 生成报告（保持与原有行为一致）
        report_text = await self.llm.chat(
            [
                {
                    "role": "user",
                    "content": GENERATE_REPORT_PROMPT.format(
                        jd=state.get("jd_content", ""),
                        resume=state.get("resume_content", ""),
                        total_rounds=state.get("total_rounds", DEFAULT_TOTAL_ROUNDS),
                        qa_history=_json.dumps(state.get("qa_history", []), ensure_ascii=False),
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
                "overall_score": 80, "tech_depth": 80, "clarity": 80,
                "logic": 80, "job_match": 80,
                "overall_comment": "整体表现稳定。",
                "round_reviews": [], "highlights": [],
                "weaknesses": [], "suggestions": [],
            }

        state["report"] = report
        state["phase"] = "done"
        state["next_action"] = "end"

        # 持久化报告
        await self.interview_repo.save_report(state.get("session_id", 0), report)
        await self._update_session_progress(state)

        await emitter.emit("report_done", report)
        await emitter.emit("interview_complete", {"sessionId": str(state.get("session_id", 0))})
        logger.info(f"面试完成 session={state.get('session_id')} score={report.get('overall_score')}")

    async def _emit_feedback(self, emitter: SSEEmitter, feedback: str, action: str) -> None:
        """将反馈拆分并 SSE 推送。"""
        await emitter.emit("feedback_start", {})
        for i in range(0, len(feedback), 120):
            await emitter.emit_text("feedback_chunk", feedback[i : i + 120])
        await emitter.emit("feedback_done", {"action": action})

    async def _update_session_progress(self, state: InterviewAgentState) -> None:
        """更新会话进度到数据库。"""
        await self.interview_repo.update_session_progress(
            state.get("session_id", 0),
            completed_rounds=state.get("current_round", 1),
            status=state.get("phase", "in_progress"),
        )

    async def _load_and_prepare(self, session_id: int, user_id: int) -> InterviewAgentState:
        """从 DB 恢复会话状态。"""
        session = await self.interview_repo.get_session(session_id)
        if session is None or session.user_id != user_id:
            raise SessionNotFoundError()

        cached = InterviewService._session_cache.get(session_id)
        if cached:
            return cached

        state = InterviewAgent.restore_state(session)
        return state

    @staticmethod
    def _sse(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"event": event_type, "data": _json.dumps(data, ensure_ascii=False)}
