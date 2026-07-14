"""模拟面试模式 LangGraph Agent。

基于 LangGraph StateGraph 管理面试轮次流转：
  setup → ask_question → wait_answer → provide_feedback
    → decide_next → (follow_up → ask_question) | (next_round → ask_question)
    | (report → END)

设计文档参考：后端技术设计文档 第五章 5.2 节
"""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from langgraph.graph import StateGraph, END
from loguru import logger


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MAX_FOLLOW_UPS_PER_ROUND = 2


# ---------------------------------------------------------------------------
# Agent 类
# ---------------------------------------------------------------------------

class InterviewAgent:
    """面试 Agent —— 管理单次模拟面试的状态图。

    用法::

        agent = InterviewAgent(llm_client, interview_repo)
        state = {"session_id": 1, "jd_content": "...", "resume_content": "...", ...}
        state = await agent.setup(state)
        # 通过服务的 submit_answer → provide_feedback → decide_next → ... 推进
    """

    def __init__(self, llm_client, interview_repo) -> None:
        self.llm = llm_client
        self.repo = interview_repo
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # 状态图构建
    # ------------------------------------------------------------------

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(dict)

        workflow.add_node("setup", self.setup)
        workflow.add_node("ask_question", self.ask_question)
        workflow.add_node("provide_feedback", self.provide_feedback)
        workflow.add_node("decide_next", self.decide_next)
        workflow.add_node("generate_report", self.generate_report)

        workflow.set_entry_point("setup")

        workflow.add_edge("setup", "ask_question")
        workflow.add_edge("ask_question", END)          # wait_answer
        workflow.add_edge("provide_feedback", "decide_next")

        workflow.add_conditional_edges(
            "decide_next",
            self._after_decide,
            {
                "follow_up": "ask_question",
                "next_round": "ask_question",
                "report": "generate_report",
            },
        )
        workflow.add_edge("generate_report", END)

        return workflow.compile()

    # ------------------------------------------------------------------
    # 节点实现
    # ------------------------------------------------------------------

    async def setup(self, state: dict[str, Any]) -> dict[str, Any]:
        """初始化面试上下文：解析 JD + 简历。"""
        logger.info(f"面试 Agent 初始化 session={state.get('session_id')}")
        state["current_round"] = state.get("current_round", 1)
        state["qa_history"] = state.get("qa_history", [])
        state["is_follow_up"] = False
        state["follow_up_count"] = 0
        state["phase"] = "asking"
        return state

    async def ask_question(self, state: dict[str, Any]) -> dict[str, Any]:
        """生成面试问题（基于 JD + 简历 + 历史上下文）。"""
        from backend.agents.prompts import INTERVIEW_QUESTION_PROMPT

        follow_up_context = "这是一次追问，请延续上一题的话题进行深入提问。" if state.get("is_follow_up") else ""
        is_follow_up_instruction = (
            "这是对上一题回答的追问，请延续同一话题深入提问"
            if state.get("is_follow_up")
            else "独立生成一个新问题，覆盖不同的技术栈或能力项"
        )

        recent_history = state.get("qa_history", [])[-6:]
        history_text = json.dumps(recent_history, ensure_ascii=False) if recent_history else "暂无历史记录"

        prompt = INTERVIEW_QUESTION_PROMPT.format(
            jd=state.get("jd_content", ""),
            resume=state.get("resume_content", ""),
            current_round=state.get("current_round", 1),
            total_rounds=state.get("total_rounds", 10),
            follow_up_context=follow_up_context,
            qa_history=history_text,
            is_follow_up_instruction=is_follow_up_instruction,
        )

        result = await self.llm.chat_with_json(prompt)
        state["current_question"] = result.get("question", "请介绍一个你最有代表性的项目。")
        state["qa_history"].append(
            {
                "round": state["current_round"],
                "is_follow_up": state.get("is_follow_up", False),
                "question": state["current_question"],
            }
        )
        state["phase"] = "waiting"
        logger.info(f"面试出题 round={state['current_round']} follow_up={state.get('is_follow_up')}")
        return state

    async def provide_feedback(self, state: dict[str, Any]) -> dict[str, Any]:
        """生成简短的 AI 回应。"""
        from backend.agents.prompts import INTERVIEW_FEEDBACK_PROMPT

        feedback = await self.llm.chat(
            INTERVIEW_FEEDBACK_PROMPT.format(
                question=state.get("current_question", ""),
                answer=state.get("user_answer", ""),
            )
        )
        state["ai_feedback"] = feedback.strip()
        state["phase"] = "deciding"
        return state

    async def decide_next(self, state: dict[str, Any]) -> dict[str, Any]:
        """决策下一步：追问 / 下一轮 / 生成报告。"""
        from backend.agents.prompts import DECIDE_NEXT_PROMPT

        decision = await self.llm.chat_with_json(
            DECIDE_NEXT_PROMPT.format(
                jd=state.get("jd_content", ""),
                resume=state.get("resume_content", ""),
                current_round=state.get("current_round", 1),
                total_rounds=state.get("total_rounds", 10),
                current_question=state.get("current_question", ""),
                user_answer=state.get("user_answer", ""),
                follow_up_count=state.get("follow_up_count", 0),
                max_follow_ups=MAX_FOLLOW_UPS_PER_ROUND,
                qa_history=json.dumps(state.get("qa_history", []), ensure_ascii=False),
            )
        )

        current_round = state.get("current_round", 1)
        total_rounds = state.get("total_rounds", 10)
        follow_up_count = state.get("follow_up_count", 0)

        if current_round >= total_rounds:
            if decision.get("should_follow_up") and follow_up_count < MAX_FOLLOW_UPS_PER_ROUND:
                state["next_action"] = "follow_up"
                state["is_follow_up"] = True
                state["follow_up_count"] = follow_up_count + 1
            else:
                state["next_action"] = "report"
        elif decision.get("should_follow_up") and follow_up_count < MAX_FOLLOW_UPS_PER_ROUND:
            state["next_action"] = "follow_up"
            state["is_follow_up"] = True
            state["follow_up_count"] = follow_up_count + 1
        else:
            state["next_action"] = "next_round"
            state["current_round"] = current_round + 1
            state["is_follow_up"] = False
            state["follow_up_count"] = 0

        logger.info(f"面试决策: {state['next_action']} round={state.get('current_round')}")
        return state

    async def generate_report(self, state: dict[str, Any]) -> dict[str, Any]:
        """生成完整复盘报告。"""
        from backend.agents.prompts import GENERATE_REPORT_PROMPT

        report_text = await self.llm.chat(
            [
                {
                    "role": "user",
                    "content": GENERATE_REPORT_PROMPT.format(
                        jd=state.get("jd_content", ""),
                        resume=state.get("resume_content", ""),
                        total_rounds=state.get("total_rounds", 10),
                        qa_history=json.dumps(state.get("qa_history", []), ensure_ascii=False),
                    ),
                }
            ],
            response_format={"type": "json_object"},
        )

        try:
            report = json.loads(report_text)
        except json.JSONDecodeError:
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
        state["phase"] = "done"

        # 持久化报告
        await self.repo.save_report(state.get("session_id", 0), report)

        logger.info(f"面试报告生成完成 session={state.get('session_id')}")
        return state

    # ------------------------------------------------------------------
    # 条件边
    # ------------------------------------------------------------------

    @staticmethod
    def _after_decide(state: dict[str, Any]) -> Literal["follow_up", "next_round", "report"]:
        action = state.get("next_action", "next_round")
        if action == "follow_up":
            return "follow_up"
        if action == "report":
            return "report"
        return "next_round"
