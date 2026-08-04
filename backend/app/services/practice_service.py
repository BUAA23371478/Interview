"""
练习服务：专项练习（主题/难度/公司风格），逐题评分 + 难度自适应 + 错题本。

流程：
    start:  RAG 检索主题上下文 → 出第一题
    answer: 评分 → 记录错题 → 难度 FSM → 下一题或结束报告
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from loguru import logger

from app.agents.difficulty_fsm import update_difficulty
from app.agents.practice_agent import practice_question_agent
from app.agents.practice_evaluator import practice_evaluator
from app.config import settings
from app.deps import MaooUser
from app.memory import long_term
from app.memory.short_term import short_term_memory
from app.rag.engine import query_engine


def _session_key(session_id: str) -> str:
    return f"practice:{session_id}"


def _new_state(user: MaooUser, topic: str, difficulty: str,
               company_style: str, total_rounds: int) -> Dict[str, Any]:
    return {
        "session_id": str(uuid.uuid4()),
        "maoo_user_id": user.user_id,
        "mode": "practice",
        "topic": topic,
        "difficulty": difficulty or "medium",
        "company_style": company_style or "通用",
        "total_rounds": min(max(total_rounds, 1), settings.max_quiz_rounds),
        "question_index": 0,
        "current_question": {},
        "score_records": [],
        "consecutive_correct": 0,
        "consecutive_wrong": 0,
        "finished": False,
        "error": None,
    }


async def start_practice(user: MaooUser, topic: str, difficulty: str,
                         company_style: str, total_rounds: int) -> Dict[str, Any]:
    state = _new_state(user, topic, difficulty, company_style, total_rounds)

    # RAG 检索主题上下文
    try:
        rag_context = await query_engine.search_for_agent(topic, top_k=3)
        state["rag_context"] = rag_context
    except Exception as e:  # noqa: BLE001
        logger.warning("练习 RAG 检索失败: {}", e)
        state["rag_context"] = ""

    await practice_question_agent.run(state)
    q = state["current_question"]
    if not q.get("question"):
        return {"ok": False, "message": "出题失败，请换个主题重试", "session_id": state["session_id"]}

    state["question_index"] = 0
    _save_session(state)
    await long_term.add_footprint(user.user_id, "start_practice", topic)

    return {
        "ok": True,
        "session_id": state["session_id"],
        "question": q["question"],
        "question_index": 0,
        "total_rounds": state["total_rounds"],
        "difficulty": state["difficulty"],
        "topic": topic,
    }


async def answer_practice(user: MaooUser, session_id: str, answer: str) -> Dict[str, Any]:
    state = _load_session(session_id, user)
    if not state:
        return {"ok": False, "message": "会话不存在或已过期"}
    if state.get("finished"):
        return {"ok": True, "finished": True, "report": state.get("report"), "session_id": session_id}

    state["last_user_answer"] = answer
    await practice_evaluator.run(state)
    q = state["current_question"]
    score = state["last_score"]
    is_correct = state["last_is_correct"]
    feedback = state["feedback"]
    state["last_correctness"] = is_correct
    update_difficulty(state)

    state["score_records"].append({
        "question": q.get("question", ""), "answer": answer,
        "score": score, "topic": state["topic"],
    })

    # 错题本
    if score < 6:
        await long_term.record_wrong_answer(
            user.user_id, session_id, topic=state["topic"],
            question=q.get("question", ""), answer=answer,
            reference=q.get("reference_answer", ""), score=score,
        )

    # 下一题或结束
    next_idx = state["question_index"] + 1
    if next_idx >= state["total_rounds"]:
        return await _finish_practice(user, state)

    state["question_index"] = next_idx
    state["difficulty"] = state["current_difficulty"]
    await practice_question_agent.run(state)
    next_q = state["current_question"]
    _save_session(state)

    return {
        "ok": True, "session_id": session_id, "finished": False,
        "score": score, "is_correct": is_correct,
        "feedback": feedback.get("feedback", ""),
        "correct_points": feedback.get("correct_points", []),
        "missing_points": feedback.get("missing_points", []),
        "reference": q.get("reference_answer", ""),
        "question": next_q.get("question", ""),
        "question_index": next_idx,
        "total_rounds": state["total_rounds"],
        "difficulty": state["current_difficulty"],
    }


async def _finish_practice(user: MaooUser, state: Dict[str, Any]) -> Dict[str, Any]:
    """练习结束：生成维度统计报告。"""
    records = state.get("score_records", [])
    scores = [r["score"] for r in records]
    avg = round(sum(scores) / len(scores), 1) if scores else 0
    correct = sum(1 for s in scores if s >= 6)
    topic_scores: Dict[str, list] = {}
    for r in records:
        topic_scores.setdefault(r.get("topic", state["topic"]), []).append(r["score"])
    topic_performance = [
        {"topic": t, "avg_score": round(sum(v) / len(v), 1), "count": len(v)}
        for t, v in topic_scores.items()
    ]
    report = {
        "mode": "practice",
        "topic": state["topic"],
        "company_style": state["company_style"],
        "total_questions": len(records),
        "avg_score": avg,
        "accuracy": round(correct / len(records), 2) if records else 0,
        "overall_score": round(avg * 10),
        "topic_performance": topic_performance,
        "weaknesses": [t["topic"] for t in topic_performance if t["avg_score"] < 6],
        "recommendation": "继续加油" if avg < 6 else "表现良好",
        "dimension_scores": {t["topic"]: round(t["avg_score"], 1) for t in topic_performance},
    }
    state["finished"] = True
    state["report"] = report
    _save_session(state)

    await long_term.save_report(user.user_id, state["session_id"], "practice", report)
    await long_term.add_footprint(user.user_id, "finish_practice", f"topic={state['topic']} avg={avg}")

    return {
        "ok": True, "session_id": state["session_id"], "finished": True,
        "score": round(avg, 1), "is_correct": avg >= 6,
        "feedback": f"练习完成，共 {len(records)} 题，平均分 {avg}",
        "question": "", "question_index": state["question_index"],
        "total_rounds": state["total_rounds"],
        "difficulty": state["difficulty"],
        "report": report,
    }


async def get_report(user: MaooUser, session_id: str) -> Optional[Dict[str, Any]]:
    state = _load_session(session_id, user)
    if not state:
        return None
    return {
        "session_id": session_id, "mode": "practice",
        "final_report": state.get("report", {}), "study_plan": None,
    }


async def list_history(user: MaooUser, limit: int = 30) -> list:
    reports = await long_term.list_reports(user.user_id, mode="practice", limit=limit)
    items = []
    for r in reports:
        rep = r.get("report", {})
        items.append({
            "session_id": r["session_id"],
            "mode": "practice",
            "status": "completed",
            "created_at": r.get("created_at"),
            "summary": {
                "topic": rep.get("topic"),
                "avg_score": rep.get("avg_score"),
                "overall_score": rep.get("overall_score"),
                "total_questions": rep.get("total_questions"),
                "accuracy": rep.get("accuracy"),
            },
        })
    return items


def _save_session(state: Dict[str, Any]) -> None:
    short_term_memory.save_snapshot(state["session_id"], state)


def _load_session(session_id: str, user: MaooUser) -> Optional[Dict[str, Any]]:
    state = short_term_memory.load_snapshot(session_id)
    if not state:
        return None
    if state.get("maoo_user_id") != user.user_id and not user.is_admin:
        return None
    return state
