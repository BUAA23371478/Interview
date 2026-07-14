from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import get_db
from backend.repositories.interview_repo import InterviewRepo
from backend.repositories.practice_repo import PracticeRepo
from backend.services.history_service import HistoryService

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/practice")
async def practice_history(user_id: int = Header(alias="X-User-Id"), page: int = 1, limit: int = 20, db: AsyncSession = Depends(get_db)) -> dict:
    return await HistoryService(db).practice_history(user_id, page=page, limit=limit)


@router.get("/practice/{session_id:int}")
async def practice_detail(session_id: int, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    detail = await HistoryService(db).practice_detail(session_id, user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="会话不存在")
    return detail


@router.delete("/practice/{session_id:int}")
async def delete_practice(session_id: int, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    ok = await PracticeRepo(db).delete_session(session_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权操作")
    return {"status": "ok"}


@router.get("/practice/stats")
async def practice_stats(user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    return await HistoryService(db).practice_stats(user_id)


@router.get("/interview")
async def interview_history(user_id: int = Header(alias="X-User-Id"), page: int = 1, limit: int = 20, db: AsyncSession = Depends(get_db)) -> dict:
    return await HistoryService(db).interview_history(user_id, page=page, limit=limit)


@router.get("/interview/{interview_id:int}")
async def interview_detail(interview_id: int, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    detail = await HistoryService(db).interview_detail(interview_id, user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="会话不存在")
    return detail


@router.delete("/interview/{interview_id:int}")
async def delete_interview(interview_id: int, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    ok = await InterviewRepo(db).delete_session(interview_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权操作")
    return {"status": "ok"}
