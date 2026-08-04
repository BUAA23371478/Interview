"""
面试服务：多 Agent 编排完整面试流程。

流程：
    start:  解析 JD → 解析简历 → RAG 检索 → 规划题目 → 出第一题
    answer: 评估答案 → 难度 FSM → 决定追问/下一题/收尾 → 报告 → 复习计划

状态通过 short_term（会话快照）持久化，按 X-Maoo-User-Id 隔离。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from loguru import logger

from app.agents.difficulty_fsm import update_difficulty
from app.agents.evaluator import evaluator
from app.agents.interviewer import interviewer
from app.agents.jd_analyzer import jd_analyzer
from app.agents.resume_analyzer import resume_analyzer
from app.agents.question_planner import question_planner
from app.agents.study_planner import study_planner
from app.config import settings
from app.deps import MaooUser
from app.memory import long_term
from app.memory.short_term import short_term_memory
from app.rag.engine import query_engine
from app.sse.emitter import sse_emitter, sse_manager


def _session_key(session_id: str) -> str:
    return f"interview:{session_id}"


def _new_state(user: MaooUser, jd_text: str, resume_text: str,
               total_rounds: int, difficulty: str) -> Dict[str, Any]:
    return {
        "session_id": str(uuid.uuid4()),
        "maoo_user_id": user.user_id,
        "user_input": "开始面试",
        "intent": "start_interview",
        "jd_text": jd_text,
        "resume_text": resume_text,
        "total_rounds": min(max(total_rounds, 1), settings.max_interview_rounds),
        "current_difficulty": difficulty or settings.default_difficulty,
        "current_question_idx": 0,
        "qa_history": [],
        "score_records": [],
        "consecutive_correct": 0,
        "consecutive_wrong": 0,
        "followup_count": 0,
        "max_followup": settings.max_followups_per_round,
        "interview_finished": False,
        "should_followup": False,
        "force_finish": False,
        "skill_state": {},
        "weaknesses_to_remember": [],
        "error": None,
    }


async def _prepare_interview(state: Dict[str, Any]) -> Optional[str]:
    """JD→简历→RAG→规划，返回错误信息或 None。"""
    await jd_analyzer.run(state)
    if not state.get("jd_parsed"):
        return "岗位描述解析失败，请检查内容"

    if state.get("resume_text"):
        await resume_analyzer.run(state)

    # RAG 检索：用技术栈 + 核心能力做查询
    jd = state.get("jd_parsed") or {}
    query_terms = list(jd.get("tech_stack", [])) + list(jd.get("core_competencies", []))
    query = " ".join(query_terms) if query_terms else (jd.get("summary") or "AI Agent 面试")
    try:
        rag_context = await query_engine.search_for_agent(query, top_k=settings.rag_top_k)
        state["rag_context"] = rag_context
    except Exception as e:  # noqa: BLE001
        logger.warning("RAG 检索失败: {}", e)
        state["rag_context"] = ""

    state["total_questions"] = state["total_rounds"]
    await question_planner.run(state)
    if not state.get("question_plan"):
        return "题目规划失败，请重试"
    return None


async def start_interview(user: MaooUser, jd_text: str, resume_text: str,
                          total_rounds: int, difficulty: str) -> Dict[str, Any]:
    """启动面试，返回第一题。"""
    state = _new_state(user, jd_text, resume_text, total_rounds, difficulty)
    err = await _prepare_interview(state)
    if err:
        return {"ok": False, "message": err, "session_id": state["session_id"]}

    # 加载长期薄弱点
    profile = await long_term.get_profile(user.user_id)
    state["long_term_weaknesses"] = (profile or {}).get("persistent_weaknesses", [])[:5]

    # 出第一题
    question = await interviewer.ask_question(state)
    state["current_question_text"] = question
    state["current_question"] = {
        "question": question, "idx": 0,
        "topic": (state["question_plan"][0] if state["question_plan"] else {}).get("topic", ""),
    }
    state["awaiting_answer"] = True

    _save_session(state)
    await long_term.add_footprint(user.user_id, "start_interview", jd_text[:80])

    return {
        "ok": True,
        "session_id": state["session_id"],
        "question": question,
        "question_index": 0,
        "total_rounds": state["total_rounds"],
        "difficulty": state["current_difficulty"],
        "jd_title": (state.get("jd_parsed") or {}).get("title", ""),
    }


async def answer_interview(user: MaooUser, session_id: str, answer: str) -> Dict[str, Any]:
    """提交回答 → 评分 → 决定下一步。"""
    state = _load_session(session_id, user)
    if not state:
        return {"ok": False, "message": "会话不存在或已过期"}
    if state.get("interview_finished"):
        return {"ok": True, "interview_finished": True,
                "final_report": state.get("final_report"),
                "study_plan": state.get("study_plan"), "session_id": session_id}

    state["last_user_answer"] = answer
    state["awaiting_answer"] = False

    q_text = state.get("current_question_text", "")
    q_item = state.get("current_question") or {}

    # 评分
    score = await evaluator.score_one(q_text, answer)
    score_record = {"question": q_text, "answer": answer, "score": score}
    state["score_records"].append(score_record)
    state["qa_history"].append(score_record)
    state["last_correctness"] = bool(score.get("is_correct"))
    update_difficulty(state)

    # 判断是否追问
    should_followup = bool(
        score.get("followup_needed")
        and state["followup_count"] < state["max_followup"]
    )
    state["should_followup"] = should_followup

    # 记录错题（低分）
    try:
        correctness = score.get("correctness", 0)
        if correctness < 6:
            key_missing = score.get("key_missing", [])
            reference = "；".join(str(k) for k in key_missing) if key_missing else ""
            await long_term.record_wrong_answer(
                user.user_id, session_id,
                topic=q_item.get("topic", ""),
                question=q_text, answer=answer,
                reference=reference,
                score=correctness,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("记录错题失败: {}", e)

    if should_followup:
        state["followup_count"] += 1
        followup_q = await interviewer.ask_followup(state)
        state["current_question_text"] = followup_q
        state["current_question"] = {**q_item, "is_followup": True}
        state["awaiting_answer"] = True
        _save_session(state)
        return {
            "ok": True, "session_id": session_id, "interview_finished": False,
            "should_followup": True, "question": followup_q,
            "question_index": state["current_question_idx"],
            "total_rounds": state["total_rounds"],
            "difficulty": state["current_difficulty"],
            "score": correctness,
        }

    # 下一题或结束
    next_idx = state["current_question_idx"] + 1
    if next_idx >= len(state.get("question_plan", [])) or state.get("force_finish"):
        result = await _finish_interview(user, state)
        return result

    state["current_question_idx"] = next_idx
    state["followup_count"] = 0
    next_q = await interviewer.ask_question(state)
    state["current_question_text"] = next_q
    state["current_question"] = {
        "question": next_q, "idx": next_idx,
        "topic": (state["question_plan"][next_idx] if next_idx < len(state.get("question_plan", [])) else {}).get("topic", ""),
    }
    state["awaiting_answer"] = True
    _save_session(state)
    return {
        "ok": True, "session_id": session_id, "interview_finished": False,
        "should_followup": False, "question": next_q,
        "question_index": next_idx,
        "total_rounds": state["total_rounds"],
        "difficulty": state["current_difficulty"],
        "score": correctness,
    }


async def _finish_interview(user: MaooUser, state: Dict[str, Any]) -> Dict[str, Any]:
    """面试结束：报告 + 复习计划 + 长期记忆。"""
    state["interview_finished"] = True
    report = await evaluator.generate_report(state)
    state["final_report"] = report
    state["weaknesses_to_remember"] = list(report.get("weaknesses", []))[:10]

    await study_planner.run(state)

    # 长期记忆写入
    await long_term.save_report(user.user_id, state["session_id"], "interview", report)
    if state.get("weaknesses_to_remember"):
        await long_term.append_weaknesses(user.user_id, state["weaknesses_to_remember"])
    await long_term.add_footprint(user.user_id, "finish_interview",
                                  f"score={report.get('overall_score')}")

    _save_session(state)
    return {
        "ok": True, "session_id": state["session_id"], "interview_finished": True,
        "should_followup": False, "question": "",
        "question_index": state["current_question_idx"],
        "total_rounds": state["total_rounds"],
        "difficulty": state["current_difficulty"],
        "final_report": report,
        "study_plan": state.get("study_plan"),
    }


async def get_report(user: MaooUser, session_id: str) -> Optional[Dict[str, Any]]:
    state = _load_session(session_id, user)
    if not state:
        return None
    return {
        "session_id": session_id,
        "mode": "interview",
        "final_report": state.get("final_report", {}),
        "study_plan": state.get("study_plan", {}),
    }


async def list_history(user: MaooUser, limit: int = 30) -> list:
    reports = await long_term.list_reports(user.user_id, mode="interview", limit=limit)
    items = []
    for r in reports:
        rep = r.get("report", {})
        items.append({
            "session_id": r["session_id"],
            "mode": "interview",
            "status": "completed",
            "created_at": r.get("created_at"),
            "summary": {
                "overall_score": rep.get("overall_score"),
                "recommendation": rep.get("recommendation"),
                "jd_title": "",
                "weaknesses": rep.get("weaknesses", [])[:3],
            },
        })
    return items


def _save_session(state: Dict[str, Any]) -> None:
    short_term_memory.save_snapshot(state["session_id"], state)


def _load_session(session_id: str, user: MaooUser) -> Optional[Dict[str, Any]]:
    state = short_term_memory.load_snapshot(session_id)
    if not state:
        return None
    # 会话隔离：校验属主
    if state.get("maoo_user_id") != user.user_id and not user.is_admin:
        return None
    return state
