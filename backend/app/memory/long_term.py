"""
长期记忆（SQLite）：用户画像 + 薄弱点 + 错题本 + 学习足迹 + 历史。

所有方法均通过异步会话操作，带容错（失败记录日志不崩溃）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Report, User, UserProfile, WrongAnswer


async def _get_profile(session, maoo_user_id: int) -> UserProfile:
    profile = (await session.execute(
        select(UserProfile).where(UserProfile.maoo_user_id == maoo_user_id)
    )).scalar_one_or_none()
    if profile is None:
        profile = UserProfile(maoo_user_id=maoo_user_id)
        session.add(profile)
        await session.flush()
    return profile


async def get_or_create_user(session, maoo_user_id: int, username: str = "", role: str = "user") -> User:
    user = (await session.execute(
        select(User).where(User.maoo_user_id == maoo_user_id)
    )).scalar_one_or_none()
    if user is None:
        user = User(maoo_user_id=maoo_user_id, username=username, role=role)
        session.add(user)
        await session.flush()
    else:
        if username and username != user.username:
            user.username = username
        if role and role != user.role:
            user.role = role
    return user


async def get_profile(maoo_user_id: int) -> Optional[Dict[str, Any]]:
    try:
        async with SessionLocal() as session:
            p = await _get_profile(session, maoo_user_id)
            await session.commit()
            return _profile_to_dict(p)
    except Exception as e:  # noqa: BLE001
        logger.warning("get_profile 失败: {}", e)
        return None


async def update_profile(maoo_user_id: int, **fields: Any) -> Optional[Dict[str, Any]]:
    try:
        async with SessionLocal() as session:
            p = await _get_profile(session, maoo_user_id)
            for k, v in fields.items():
                if hasattr(p, k) and v is not None:
                    setattr(p, k, v)
            await session.commit()
            return _profile_to_dict(p)
    except Exception as e:  # noqa: BLE001
        logger.warning("update_profile 失败: {}", e)
        return None


def _profile_to_dict(p: UserProfile) -> Dict[str, Any]:
    return {
        "maoo_user_id": p.maoo_user_id,
        "total_interviews": p.total_interviews or 0,
        "total_practices": p.total_practices or 0,
        "avg_score": round(p.avg_score or 0.0, 1),
        "persistent_weaknesses": list(p.persistent_weaknesses or []),
        "tech_strengths": list(p.tech_strengths or []),
        "radar_scores": dict(p.radar_scores or {}),
        "wrong_book": list(p.wrong_book or []),
        "learning_footprint": list(p.learning_footprint or [])[-50:],
    }


async def append_weaknesses(maoo_user_id: int, weaknesses: List[str]) -> None:
    """合并并去重薄弱点（最多保留 50 条）。"""
    if not weaknesses:
        return
    try:
        async with SessionLocal() as session:
            p = await _get_profile(session, maoo_user_id)
            existing = list(p.persistent_weaknesses or [])
            for w in weaknesses:
                w = (w or "").strip()
                if w and w not in existing:
                    existing.append(w)
            p.persistent_weaknesses = existing[:50]
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("append_weaknesses 失败: {}", e)


async def merge_radar_scores(maoo_user_id: int, new_scores: Dict[str, float]) -> None:
    """按指数移动平均合并雷达分数。"""
    if not new_scores:
        return
    try:
        async with SessionLocal() as session:
            p = await _get_profile(session, maoo_user_id)
            radar = dict(p.radar_scores or {})
            for k, v in new_scores.items():
                old = radar.get(k, 0.0)
                radar[k] = round(old * 0.5 + float(v) * 0.5, 1)
            p.radar_scores = radar
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("merge_radar_scores 失败: {}", e)


async def add_footprint(maoo_user_id: int, action: str, detail: str = "") -> None:
    try:
        async with SessionLocal() as session:
            p = await _get_profile(session, maoo_user_id)
            fp = list(p.learning_footprint or [])
            fp.append({"ts": datetime.now(timezone.utc).isoformat(), "action": action, "detail": detail})
            p.learning_footprint = fp[-100:]
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("add_footprint 失败: {}", e)


async def save_report(maoo_user_id: int, session_id: str, mode: str, report: Dict[str, Any]) -> None:
    try:
        async with SessionLocal() as session:
            session.add(Report(maoo_user_id=maoo_user_id, session_id=session_id, mode=mode, report_json=report))
            p = await _get_profile(session, maoo_user_id)
            if mode == "interview":
                p.total_interviews = (p.total_interviews or 0) + 1
            else:
                p.total_practices = (p.total_practices or 0) + 1
            overall = report.get("overall_score") or report.get("avg_score") or 0
            prev = p.avg_score or 0.0
            count = (p.total_interviews or 0) + (p.total_practices or 0)
            p.avg_score = round((prev * (count - 1) + float(overall)) / count, 1) if count else float(overall)
            # 更新薄弱点
            weaknesses = report.get("weaknesses") or []
            if weaknesses:
                existing = list(p.persistent_weaknesses or [])
                for w in weaknesses:
                    w = (w or "").strip()
                    if w and w not in existing:
                        existing.append(w)
                p.persistent_weaknesses = existing[:50]
            # 更新雷达
            dims = report.get("dimension_scores") or {}
            if dims:
                radar = dict(p.radar_scores or {})
                for k, v in dims.items():
                    try:
                        radar[k] = round(float(v), 1)
                    except (TypeError, ValueError):
                        pass
                p.radar_scores = radar
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("save_report 失败: {}", e)


async def record_wrong_answer(
    maoo_user_id: int, session_id: str, topic: str,
    question: str, answer: str, reference: str, score: float,
) -> None:
    try:
        async with SessionLocal() as session:
            session.add(WrongAnswer(
                maoo_user_id=maoo_user_id, session_id=session_id, topic=topic,
                question=question, answer=answer, reference=reference, score=float(score),
            ))
            p = await _get_profile(session, maoo_user_id)
            wb = list(p.wrong_book or [])
            wb.append({
                "session_id": session_id, "topic": topic, "question": question[:200],
                "score": float(score), "added_at": datetime.now(timezone.utc).isoformat(),
            })
            p.wrong_book = wb[-200:]
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("record_wrong_answer 失败: {}", e)


async def list_reports(maoo_user_id: int, mode: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        async with SessionLocal() as session:
            q = select(Report).where(Report.maoo_user_id == maoo_user_id)
            if mode:
                q = q.where(Report.mode == mode)
            q = q.order_by(Report.id.desc()).limit(limit)
            rows = (await session.execute(q)).scalars().all()
            return [{
                "session_id": r.session_id, "mode": r.mode,
                "report": r.report_json, "created_at": r.created_at,
            } for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("list_reports 失败: {}", e)
        return []


async def list_wrong_answers(maoo_user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    try:
        async with SessionLocal() as session:
            q = (select(WrongAnswer).where(WrongAnswer.maoo_user_id == maoo_user_id)
                 .order_by(WrongAnswer.id.desc()).limit(limit))
            rows = (await session.execute(q)).scalars().all()
            return [{
                "id": r.id, "session_id": r.session_id, "topic": r.topic,
                "question": r.question, "answer": r.answer, "reference": r.reference,
                "score": r.score, "reviewed": r.reviewed, "note": r.note,
                "created_at": r.created_at,
            } for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("list_wrong_answers 失败: {}", e)
        return []


async def update_wrong_answer(maoo_user_id: int, wrong_id: int, *, reviewed: Optional[int] = None, note: Optional[str] = None) -> None:
    try:
        async with SessionLocal() as session:
            row = (await session.execute(
                select(WrongAnswer).where(
                    WrongAnswer.id == wrong_id, WrongAnswer.maoo_user_id == maoo_user_id)
            )).scalar_one_or_none()
            if row:
                if reviewed is not None:
                    row.reviewed = reviewed
                if note is not None:
                    row.note = note
                await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("update_wrong_answer 失败: {}", e)
