"""练习路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import MaooUser, require_login
from app.schemas import (HistoryResponse, PracticeAnswerRequest,
                         PracticeAnswerResponse, PracticeStartRequest,
                         PracticeStartResponse, ReportResponse)
from app.services import practice_service

router = APIRouter(prefix="/practice", tags=["专项练习"])


@router.post("/start", response_model=PracticeStartResponse)
async def start_practice(req: PracticeStartRequest,
                         user: MaooUser = Depends(require_login)) -> PracticeStartResponse:
    result = await practice_service.start_practice(
        user, req.topic, req.difficulty, req.company_style, req.total_rounds)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "启动失败"))
    return PracticeStartResponse(**result)


@router.post("/answer", response_model=PracticeAnswerResponse)
async def answer_practice(req: PracticeAnswerRequest,
                          user: MaooUser = Depends(require_login)) -> PracticeAnswerResponse:
    result = await practice_service.answer_practice(user, req.session_id, req.answer)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "提交失败"))
    return PracticeAnswerResponse(
        session_id=result["session_id"],
        finished=result.get("finished", False),
        score=result.get("score", 0.0),
        is_correct=result.get("is_correct", False),
        feedback=result.get("feedback", ""),
        reference=result.get("reference", ""),
        question=result.get("question", ""),
        question_index=result.get("question_index", 0),
        total_rounds=result.get("total_rounds", 0),
        difficulty=result.get("difficulty", "medium"),
        wrong_book_prompt=result.get("wrong_book_prompt", False),
        report=result.get("report"),
    )


@router.get("/report/{session_id}", response_model=ReportResponse)
async def get_report(session_id: str,
                     user: MaooUser = Depends(require_login)) -> ReportResponse:
    data = await practice_service.get_report(user, session_id)
    if not data:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ReportResponse(**data)


@router.get("/history", response_model=HistoryResponse)
async def history(user: MaooUser = Depends(require_login)) -> HistoryResponse:
    items = await practice_service.list_history(user)
    return HistoryResponse(items=items)
