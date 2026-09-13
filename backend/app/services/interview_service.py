"""
面试服务：多 Agent 编排完整面试流程。

流程：
    start:  解析 JD → 解析简历 → RAG 检索 → 规划题目 → 出第一题
    answer: 评估答案 → 难度 FSM → 决定追问/下一题/收尾 → 报告 → 复习计划

状态通过 short_term（会话快照）持久化，按 X-Maoo-User-Id 隔离。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

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
from app.observability import log_summary, new_meter, span, summarize
from app.rag.engine import query_engine
from app.sse.emitter import sse_emitter, sse_manager


def _session_key(session_id: str) -> str:
    return f"interview:{session_id}"


# 会话级写锁：同一会话同一时刻只允许一个请求走「读-改-写」，
# 防同一用户双击/网络重试导致两道并发请求交叉覆盖。
_session_locks: Dict[str, asyncio.Lock] = {}


def _session_lock(session_id: str) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


async def _emit(session_id: str, event: str, data: Dict[str, Any]) -> None:
    """推送 SSE 事件。观测类动作不允许影响主流程，异常一律吞掉只记日志。"""
    try:
        await sse_emitter.emit(_session_key(session_id), event, data)
    except Exception as e:  # noqa: BLE001
        logger.debug("SSE 推送失败（不影响主流程）: {}", e)


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
        "difficulty_trace": [],
        "trace": [],
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


_JD_STOPWORDS = {
    "岗位", "职责", "要求", "负责", "熟悉", "掌握", "了解", "具备", "优先", "加分", "相关",
    "经验", "能力", "团队", "工作", "良好", "以上", "以及", "能够", "具有", "参与", "独立",
    "我们", "以及", "熟练", "精通", "本科", "硕士", "以上学历", "等相关", "者优先",
}


def extract_jd_terms(text: str, top_k: int = 12) -> str:
    """从原始 JD 文本抽取关键词，作为 RAG 检索 query。

    为什么需要它：初版要等 `jd_analyzer` 解析出 tech_stack 之后才能构造检索 query，
    这让「检索」被迫串在「JD 解析」后面（多等一整个 LLM 往返）。
    用 TF-IDF 关键词抽取（纯本地、毫秒级）先把 query 造出来，
    检索就能和 JD/简历解析**并发**执行，启动关键路径因此缩短。
    """
    text = (text or "").strip()
    if not text:
        return "AI Agent 面试"
    try:
        import jieba.analyse
        tags = jieba.analyse.extract_tags(text, topK=top_k * 2)
        terms = [t for t in tags if t and t not in _JD_STOPWORDS]
        if terms:
            return " ".join(terms[:top_k])
    except Exception as e:  # noqa: BLE001
        logger.debug("jieba 关键词抽取不可用，退回截断原文: {}", e)
    return text[:600]


async def _prepare_interview(state: Dict[str, Any]) -> Optional[str]:
    """JD → 简历 → RAG → 规划；返回错误信息或 None。

    并行化：RAG 检索与「JD 解析 → 简历匹配」链之间**没有数据依赖**
    （检索只需原始 JD 文本 + 本地关键词抽取），因此并发执行。
    关键路径从 sum(JD, 简历, RAG) 压缩为 max(JD + 简历, RAG)。
    """
    sid = state["session_id"]

    async def _rag_task() -> str:
        query = extract_jd_terms(state.get("jd_text") or "")
        await _emit(sid, "stage", {"stage": "rag", "status": "start", "query": query[:60]})
        try:
            async with span(state, "rag_retrieve") as sp:
                sp["meta"] = {"query": query[:80]}
                ctx = await query_engine.search_for_agent(query, top_k=settings.rag_top_k)
            await _emit(sid, "stage", {"stage": "rag", "status": "done",
                                       "chars": len(ctx or "")})
            return ctx
        except Exception as e:  # noqa: BLE001
            logger.warning("RAG 检索失败（降级为无参考资料出题）: {}", e)
            await _emit(sid, "stage", {"stage": "rag", "status": "degraded",
                                       "reason": str(e)[:120]})
            return ""

    async def _profile_task() -> Optional[str]:
        await _emit(sid, "stage", {"stage": "jd_analyzer", "status": "start"})
        async with span(state, "jd_analyzer"):
            await jd_analyzer.run(state)
        if not state.get("jd_parsed"):
            return "岗位描述解析失败，请检查内容"
        await _emit(sid, "stage", {"stage": "jd_analyzer", "status": "done",
                                   "title": (state.get("jd_parsed") or {}).get("title", "")})
        if state.get("resume_text"):
            await _emit(sid, "stage", {"stage": "resume_analyzer", "status": "start"})
            async with span(state, "resume_analyzer"):
                await resume_analyzer.run(state)
            await _emit(sid, "stage", {"stage": "resume_analyzer", "status": "done"})
        return None

    rag_context, profile_err = await asyncio.gather(_rag_task(), _profile_task())
    state["rag_context"] = rag_context or ""
    if profile_err:
        return profile_err

    state["total_questions"] = state["total_rounds"]
    await _emit(sid, "stage", {"stage": "question_planner", "status": "start"})
    async with span(state, "question_planner"):
        await question_planner.run(state)
    if not state.get("question_plan"):
        return "题目规划失败，请重试"
    await _emit(sid, "stage", {"stage": "question_planner", "status": "done",
                               "rounds": len(state.get("question_plan") or [])})
    return None


async def start_interview(user: MaooUser, jd_text: str, resume_text: str,
                          total_rounds: int, difficulty: str) -> Dict[str, Any]:
    """启动面试，返回第一题。"""
    new_meter()  # 请求级计量器：本请求所有 LLM 调用的 token/成本都记在这里
    state = _new_state(user, jd_text, resume_text, total_rounds, difficulty)
    sid = state["session_id"]
    await _emit(sid, "interview_started", {"session_id": sid,
                                           "total_rounds": state["total_rounds"]})

    err = await _prepare_interview(state)
    if err:
        await _emit(sid, "error", {"stage": "prepare", "message": err})
        sse_manager.mark_done(_session_key(sid))
        return {"ok": False, "message": err, "session_id": sid}

    # 加载长期薄弱点
    profile = await long_term.get_profile(user.user_id)
    state["long_term_weaknesses"] = (profile or {}).get("persistent_weaknesses", [])[:5]

    # 出第一题
    await _emit(sid, "stage", {"stage": "interviewer.ask_question", "status": "start"})
    async with span(state, "interviewer.ask_question"):
        question = await interviewer.ask_question(state)
    state["current_question_text"] = question
    state["current_question"] = {
        "question": question, "idx": 0,
        "topic": (state["question_plan"][0] if state["question_plan"] else {}).get("topic", ""),
    }
    state["awaiting_answer"] = True

    _save_session(state)  # 首次写入：无条件
    await long_term.add_footprint(user.user_id, "start_interview", jd_text[:80])
    await _emit(sid, "question", {
        "question": question, "question_index": 0,
        "total_rounds": state["total_rounds"],
        "difficulty": state["current_difficulty"],
        "should_followup": False,
    })

    log_summary(state, "interview.start")
    return {
        "ok": True,
        "session_id": sid,
        "question": question,
        "question_index": 0,
        "total_rounds": state["total_rounds"],
        "difficulty": state["current_difficulty"],
        "jd_title": (state.get("jd_parsed") or {}).get("title", ""),
        "trace": summarize(state),
    }


async def answer_interview(user: MaooUser, session_id: str, answer: str) -> Dict[str, Any]:
    """提交回答 → 评分 → 决定下一步。

    并发保护：会话级写锁（同进程）+ 快照乐观锁（跨进程）。
    冲突时返回 `conflict=True`，路由层转 409，客户端重试即可，不会丢答题记录。
    """
    lock = _session_lock(session_id)
    if lock.locked():
        # 同一会话已有请求在写：直接快速失败，避免两路 LLM 调用白烧 token
        logger.warning("会话 {} 正在处理中，拒绝并发请求", session_id)
        return {"ok": False, "conflict": True, "message": "该面试正在处理中，请稍后重试"}

    async with lock:
        return await _answer_interview_locked(user, session_id, answer)


async def _answer_interview_locked(user: MaooUser, session_id: str,
                                   answer: str) -> Dict[str, Any]:
    new_meter()
    state = _load_session(session_id, user)
    if not state:
        return {"ok": False, "message": "会话不存在或已过期"}
    expected_version = state.get("_version")
    if state.get("interview_finished"):
        return {"ok": True, "interview_finished": True,
                "final_report": state.get("final_report"),
                "study_plan": state.get("study_plan"), "session_id": session_id}

    state["last_user_answer"] = answer
    state["awaiting_answer"] = False

    q_text = state.get("current_question_text", "")
    q_item = state.get("current_question") or {}

    # 评分
    async with span(state, "evaluator.score_one"):
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

    await _emit(session_id, "scored", {
        "score": score.get("correctness"),
        "is_correct": bool(score.get("is_correct")),
        "difficulty": state["current_difficulty"],
        "should_followup": should_followup,
    })

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
        async with span(state, "interviewer.ask_followup"):
            followup_q = await interviewer.ask_followup(state)
        state["current_question_text"] = followup_q
        state["current_question"] = {**q_item, "is_followup": True}
        state["awaiting_answer"] = True
        if not _save_session(state, expected_version):
            return _conflict(session_id)
        await _emit(session_id, "question", {
            "question": followup_q, "should_followup": True,
            "question_index": state["current_question_idx"],
            "total_rounds": state["total_rounds"],
            "difficulty": state["current_difficulty"],
        })
        log_summary(state, "interview.answer.followup")
        return {
            "ok": True, "session_id": session_id, "interview_finished": False,
            "should_followup": True, "question": followup_q,
            "question_index": state["current_question_idx"],
            "total_rounds": state["total_rounds"],
            "difficulty": state["current_difficulty"],
            "score": correctness,
            "trace": summarize(state),
        }

    # 下一题或结束
    next_idx = state["current_question_idx"] + 1
    if next_idx >= len(state.get("question_plan", [])) or state.get("force_finish"):
        return await _finish_interview(user, state, expected_version)

    state["current_question_idx"] = next_idx
    state["followup_count"] = 0
    async with span(state, "interviewer.ask_question"):
        next_q = await interviewer.ask_question(state)
    state["current_question_text"] = next_q
    state["current_question"] = {
        "question": next_q, "idx": next_idx,
        "topic": (state["question_plan"][next_idx] if next_idx < len(state.get("question_plan", [])) else {}).get("topic", ""),
    }
    state["awaiting_answer"] = True
    if not _save_session(state, expected_version):
        return _conflict(session_id)
    await _emit(session_id, "question", {
        "question": next_q, "should_followup": False,
        "question_index": next_idx,
        "total_rounds": state["total_rounds"],
        "difficulty": state["current_difficulty"],
    })
    log_summary(state, "interview.answer.next")
    return {
        "ok": True, "session_id": session_id, "interview_finished": False,
        "should_followup": False, "question": next_q,
        "question_index": next_idx,
        "total_rounds": state["total_rounds"],
        "difficulty": state["current_difficulty"],
        "score": correctness,
        "trace": summarize(state),
    }


def _conflict(session_id: str) -> Dict[str, Any]:
    """快照乐观锁冲突：不覆盖已有进度，交由客户端重试。"""
    logger.warning("会话 {} 快照版本冲突，本次写入被拒", session_id)
    return {"ok": False, "conflict": True,
            "message": "会话状态已变更（可能在其他页面提交过），请刷新后重试",
            "session_id": session_id}


async def _finish_interview(user: MaooUser, state: Dict[str, Any],
                            expected_version: Optional[int] = None) -> Dict[str, Any]:
    """面试结束：报告 + 复习计划 + 长期记忆。"""
    state["interview_finished"] = True
    sid = state["session_id"]
    await _emit(sid, "finishing", {"reason": "all_rounds_done"})

    async with span(state, "evaluator.generate_report"):
        report = await evaluator.generate_report(state)
    state["final_report"] = report
    state["weaknesses_to_remember"] = list(report.get("weaknesses", []))[:10]

    async with span(state, "study_planner.run"):
        await study_planner.run(state)

    # 长期记忆写入
    await long_term.save_report(user.user_id, state["session_id"], "interview", report)
    if state.get("weaknesses_to_remember"):
        await long_term.append_weaknesses(user.user_id, state["weaknesses_to_remember"])
    await long_term.add_footprint(user.user_id, "finish_interview",
                                  f"score={report.get('overall_score')}")

    _save_session(state, expected_version)
    await _emit(sid, "interview_finished", {
        "final_report": report, "study_plan": state.get("study_plan"),
    })
    sse_manager.mark_done(_session_key(sid))
    log_summary(state, "interview.finish")
    return {
        "ok": True, "session_id": state["session_id"], "interview_finished": True,
        "should_followup": False, "question": "",
        "question_index": state["current_question_idx"],
        "total_rounds": state["total_rounds"],
        "difficulty": state["current_difficulty"],
        "final_report": report,
        "study_plan": state.get("study_plan"),
        "trace": summarize(state),
    }


async def get_current_question(user: MaooUser, session_id: str) -> Optional[Dict[str, Any]]:
    """获取会话当前题目（供前端刷新/直达时恢复）。"""
    state = _load_session(session_id, user)
    if not state:
        return None
    if state.get("interview_finished"):
        return {
            "session_id": session_id, "interview_finished": True,
            "question": "", "question_index": state.get("current_question_idx", 0),
            "total_rounds": state.get("total_rounds", 0),
            "difficulty": state.get("current_difficulty", "medium"),
            "final_report": state.get("final_report"),
            "study_plan": state.get("study_plan"),
        }
    return {
        "session_id": session_id, "interview_finished": False,
        "question": state.get("current_question_text", ""),
        "should_followup": state.get("should_followup", False),
        "question_index": state.get("current_question_idx", 0),
        "total_rounds": state.get("total_rounds", 0),
        "difficulty": state.get("current_difficulty", "medium"),
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


def _save_session(state: Dict[str, Any], expected_version: Optional[int] = None) -> bool:
    """保存会话快照。

    expected_version=None → 首次写入（无条件）；
    否则走乐观锁 CAS，返回 False 表示版本冲突（调用方须返回 409 而非覆盖）。
    """
    ok = short_term_memory.save_snapshot(
        state["session_id"], state, expected_version=expected_version)
    if ok:
        # 本地状态推进版本号，便于同一请求内多次写
        state["_version"] = int(state.get("_version") or 0) + 1
    return ok


def _load_session(session_id: str, user: MaooUser) -> Optional[Dict[str, Any]]:
    state = short_term_memory.load_snapshot(session_id)
    if not state:
        return None
    # 会话隔离：校验属主
    if state.get("maoo_user_id") != user.user_id and not user.is_admin:
        return None
    return state
