"""模拟面试模式 LangGraph Agent。

基于 LangGraph StateGraph 管理面试轮次流转：

    START → setup → ask_question → [interrupt: wait_answer]
        → provide_feedback → decide_next
            → follow_up → ask_question (loop)
            → next_round → ask_question (loop)
            → report → generate_report → END

使用 interrupt_before 实现人机交互暂停，通过 SqliteSaver checkpoint 持久化状态。

设计文档参考：PLAN.md 第一章
"""

from __future__ import annotations

import json as _json
from typing import Any, Literal, Optional, TypedDict

from langgraph.graph import END, StateGraph
from loguru import logger

from backend.agents.prompts import (
    DECIDE_NEXT_PROMPT,
    INTERVIEW_FEEDBACK_PROMPT,
    INTERVIEW_FOLLOW_UP_PROMPT,
    INTERVIEW_QUESTION_PROMPT,
    GENERATE_REPORT_PROMPT,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MAX_FOLLOW_UPS_PER_ROUND = 2
DEFAULT_TOTAL_ROUNDS = 10

# ---------------------------------------------------------------------------
# 状态定义（TypedDict，与 PLAN 1.2 节一致）
# ---------------------------------------------------------------------------


class InterviewAgentState(TypedDict, total=False):
    """面试 Agent 状态。

    字段与 PLAN.md 1.2 节 InterviewAgentState 完全一致。
    """

    # 会话标识
    session_id: int
    user_id: int

    # 输入
    jd_content: str
    resume_content: str
    total_rounds: int

    # 当前轮次
    current_round: int
    is_follow_up: bool
    follow_up_count: int
    max_follow_ups: int  # 默认 2

    # 当前问答
    current_question: Optional[str]
    user_answer: Optional[str]
    ai_feedback: Optional[str]

    # 历史
    qa_history: list[dict]

    # 决策
    action: str  # follow_up | next_round | report

    # 报告
    report: Optional[dict]

    # 流程控制
    next_action: str  # setup | ask | feedback | decide | follow_up | report | end
    error: Optional[str]
    phase: str  # asking | waiting | deciding | done


# ---------------------------------------------------------------------------
# Agent 类
# ---------------------------------------------------------------------------


class InterviewAgent:
    """面试 Agent —— 管理单次模拟面试的 LangGraph 状态图。

    用法::

        agent = InterviewAgent(llm_client, interview_repo, checkpointer)
        config = {"configurable": {"thread_id": f"interview_{session_id}"}}

        # Phase 1: setup → ask_question → pause
        async for event in agent.graph.astream(state, config,
                                               interrupt_before=["provide_feedback"]):
            ...

        # Phase 2: submit answer → feedback → decide → pause
        await agent.graph.aupdate_state(config, {"user_answer": answer})
        async for event in agent.graph.astream(None, config,
                                               interrupt_before=["ask_question"]):
            ...

        # Phase 3: resume → next question / follow_up / report
        async for event in agent.graph.astream(None, config,
                                               interrupt_before=["provide_feedback"]):
            ...
    """

    def __init__(self, llm_client, interview_repo, checkpointer: Any = None) -> None:
        self.llm = llm_client
        self.repo = interview_repo
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # 状态图构建
    # ------------------------------------------------------------------

    def _build_graph(self) -> StateGraph:
        """构建面试 StateGraph。

        图结构:
            setup → ask_question → provide_feedback → decide_next
                → ask_question (follow_up / next_round)
                → generate_report → END
        """
        workflow = StateGraph(InterviewAgentState)

        # 注册节点
        workflow.add_node("setup", self._setup_node)
        workflow.add_node("ask_question", self._ask_question_node)
        workflow.add_node("provide_feedback", self._provide_feedback_node)
        workflow.add_node("decide_next", self._decide_next_node)
        workflow.add_node("generate_report", self._generate_report_node)

        # 入口
        workflow.set_entry_point("setup")

        # 固定边
        workflow.add_edge("setup", "ask_question")
        workflow.add_edge("provide_feedback", "decide_next")

        # 条件边：decide_next → ask_question (follow_up/next_round) / generate_report
        workflow.add_conditional_edges(
            "decide_next",
            self._route_after_decide,
            {
                "ask_question": "ask_question",
                "generate_report": "generate_report",
            },
        )
        workflow.add_edge("ask_question", "provide_feedback")
        workflow.add_edge("generate_report", END)

        return workflow.compile(checkpointer=self.checkpointer)

    # ------------------------------------------------------------------
    # 节点实现
    # ------------------------------------------------------------------

    async def _setup_node(self, state: InterviewAgentState) -> dict[str, Any]:
        """初始化面试上下文。"""
        logger.info(f"[InterviewAgent] 初始化 session={state.get('session_id')}")
        return {
            "current_round": state.get("current_round", 1),
            "qa_history": state.get("qa_history", []),
            "is_follow_up": False,
            "follow_up_count": 0,
            "max_follow_ups": state.get("max_follow_ups", MAX_FOLLOW_UPS_PER_ROUND),
            "phase": "asking",
            "next_action": "ask",
        }

    async def _ask_question_node(self, state: InterviewAgentState) -> dict[str, Any]:
        """生成面试问题（基于 JD + 简历 + 历史上下文 + 可接入 RAG）。"""
        is_follow_up = state.get("is_follow_up", False)
        follow_up_context = "这是一次追问，请延续上一题的话题进行深入提问。" if is_follow_up else ""
        is_follow_up_instruction = (
            "这是对上一题回答的追问，请延续同一话题深入提问"
            if is_follow_up
            else "独立生成一个新问题，覆盖不同的技术栈或能力项"
        )

        recent_history = state.get("qa_history", [])[-6:]
        history_text = _json.dumps(recent_history, ensure_ascii=False) if recent_history else "暂无历史记录"

        # RAG 检索：按 JD 技术栈 + 简历项目检索相关考点
        from backend.rag.vector_store import vector_store as vs

        search_query = f"{state.get('jd_content', '')[:200]} {state.get('resume_content', '')[:200]}"
        knowledge_context = await vs.search_for_agent(
            query=search_query,
            top_k=3,
        )
        logger.info(
            f"[InterviewAgent] RAG 检索完成 "
            f"context_len={len(knowledge_context)}"
        )

        prompt = INTERVIEW_QUESTION_PROMPT.format(
            jd=state.get("jd_content", ""),
            resume=state.get("resume_content", ""),
            current_round=state.get("current_round", 1),
            total_rounds=state.get("total_rounds", DEFAULT_TOTAL_ROUNDS),
            follow_up_context=follow_up_context,
            qa_history=history_text,
            is_follow_up_instruction=is_follow_up_instruction,
        )

        # 将知识库参考注入 prompt（在最后追加）
        prompt += f"\n\n📚 知识库参考资料（请结合以下内容出题，使问题更贴近实际考点）：\n{knowledge_context}"

        result = await self.llm.chat_with_json(prompt)

        question = result.get("question", "请介绍一个你最有代表性的项目。")
        updated_history = list(state.get("qa_history", [])) + [
            {
                "round": state.get("current_round", 1),
                "is_follow_up": is_follow_up,
                "question": question,
            }
        ]

        logger.info(
            f"[InterviewAgent] 出题 round={state.get('current_round')} "
            f"follow_up={is_follow_up}"
        )

        return {
            "current_question": question,
            "qa_history": updated_history,
            "phase": "waiting",
            "next_action": "feedback",
        }

    async def _provide_feedback_node(self, state: InterviewAgentState) -> dict[str, Any]:
        """生成 AI 简短回应（评价 + 过渡）。"""
        # 使用 INTERVIEW_FEEDBACK_PROMPT 生成反馈
        # 注意：此时还不知道下一步动作，先给通用评价
        feedback = await self.llm.chat(
            INTERVIEW_FEEDBACK_PROMPT.format(
                question=state.get("current_question", ""),
                answer=state.get("user_answer", ""),
                action="评估中",  # 占位，后续在 service 层精调
            )
        )
        return {
            "ai_feedback": feedback.strip(),
            "phase": "deciding",
            "next_action": "decide",
        }

    async def _decide_next_node(self, state: InterviewAgentState) -> dict[str, Any]:
        """决策下一步：追问 / 下一轮 / 生成报告。"""
        decision = await self.llm.chat_with_json(
            DECIDE_NEXT_PROMPT.format(
                jd=state.get("jd_content", ""),
                resume=state.get("resume_content", ""),
                current_round=state.get("current_round", 1),
                total_rounds=state.get("total_rounds", DEFAULT_TOTAL_ROUNDS),
                current_question=state.get("current_question", ""),
                user_answer=state.get("user_answer", ""),
                follow_up_count=state.get("follow_up_count", 0),
                max_follow_ups=state.get("max_follow_ups", MAX_FOLLOW_UPS_PER_ROUND),
                qa_history=_json.dumps(state.get("qa_history", []), ensure_ascii=False),
            )
        )

        current_round = state.get("current_round", 1)
        total_rounds = state.get("total_rounds", DEFAULT_TOTAL_ROUNDS)
        follow_up_count = state.get("follow_up_count", 0)
        max_follow_ups = state.get("max_follow_ups", MAX_FOLLOW_UPS_PER_ROUND)
        is_last_round = current_round >= total_rounds

        if is_last_round:
            should_follow_up = (
                bool(decision.get("should_follow_up", False))
                and follow_up_count < max_follow_ups
            )
            if should_follow_up:
                action = "follow_up"
                result = {
                    "action": action,
                    "is_follow_up": True,
                    "follow_up_count": follow_up_count + 1,
                    "next_action": "ask",
                }
            else:
                action = "report"
                result = {
                    "action": action,
                    "next_action": "report",
                }
        elif decision.get("should_follow_up") and follow_up_count < max_follow_ups:
            action = "follow_up"
            result = {
                "action": action,
                "is_follow_up": True,
                "follow_up_count": follow_up_count + 1,
                "next_action": "ask",
            }
        else:
            action = "next_round"
            result = {
                "action": action,
                "current_round": current_round + 1,
                "is_follow_up": False,
                "follow_up_count": 0,
                "next_action": "ask",
            }

        logger.info(
            f"[InterviewAgent] 决策: {action} round={result.get('current_round', current_round)}"
        )
        return result

    async def _generate_report_node(self, state: InterviewAgentState) -> dict[str, Any]:
        """生成完整复盘报告。"""
        logger.info(f"[InterviewAgent] 生成报告 session={state.get('session_id')}")

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

        # 持久化报告
        await self.repo.save_report(state.get("session_id", 0), report)

        return {
            "report": report,
            "phase": "done",
            "next_action": "end",
        }

    # ------------------------------------------------------------------
    # 条件路由
    # ------------------------------------------------------------------

    @staticmethod
    def _route_after_decide(state: InterviewAgentState) -> Literal["ask_question", "generate_report"]:
        action = state.get("next_action", "report")
        if action == "report":
            return "generate_report"
        return "ask_question"

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    async def generate_follow_up(self, state: InterviewAgentState) -> str:
        """生成动态追问（由 Service 层调用，用于替换通用问题）。"""
        follow_up = await self.llm.chat(
            INTERVIEW_FOLLOW_UP_PROMPT.format(
                original_question=state.get("current_question", ""),
                user_answer=state.get("user_answer", ""),
            )
        )
        return follow_up.strip() or "能具体展开说说吗？"

    @staticmethod
    def default_state(
        session_id: int,
        user_id: int,
        jd_content: str,
        resume_content: str,
        total_rounds: int = DEFAULT_TOTAL_ROUNDS,
    ) -> InterviewAgentState:
        """创建初始状态。"""
        return InterviewAgentState(
            session_id=session_id,
            user_id=user_id,
            jd_content=jd_content,
            resume_content=resume_content,
            total_rounds=total_rounds,
            current_round=1,
            is_follow_up=False,
            follow_up_count=0,
            max_follow_ups=MAX_FOLLOW_UPS_PER_ROUND,
            current_question=None,
            user_answer=None,
            ai_feedback=None,
            qa_history=[],
            action="",
            report=None,
            next_action="setup",
            error=None,
            phase="asking",
        )

    @staticmethod
    def restore_state(session) -> InterviewAgentState:
        """从 DB 会话恢复状态。"""
        return InterviewAgentState(
            session_id=session.id,
            user_id=session.user_id,
            jd_content=session.jd_content,
            resume_content=session.resume_content,
            total_rounds=session.total_rounds,
            current_round=max(1, (session.completed_rounds or 0) + 1),
            is_follow_up=False,
            follow_up_count=0,
            max_follow_ups=MAX_FOLLOW_UPS_PER_ROUND,
            current_question=None,
            user_answer=None,
            ai_feedback=None,
            qa_history=[],
            action="",
            report=session.report_content,
            next_action="ask" if session.status != "completed" else "end",
            error=None,
            phase=session.status or "asking",
        )
