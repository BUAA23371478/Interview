"""面试路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import MaooUser, require_login
from app.schemas import (HistoryResponse, InterviewAnswerRequest,
                         InterviewAnswerResponse, InterviewStartRequest,
                         InterviewStartResponse, ReportResponse)
from app.services import interview_service

router = APIRouter(prefix="/interview", tags=["模拟面试"])


@router.post("/start", response_model=InterviewStartResponse)
async def start_interview(req: InterviewStartRequest,
                          user: MaooUser = Depends(require_login)) -> InterviewStartResponse:
    result = await interview_service.start_interview(
        user, req.jd_text, req.resume_text, req.total_rounds, req.difficulty)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "启动失败"))
    return InterviewStartResponse(**result)


@router.post("/answer", response_model=InterviewAnswerResponse)
async def answer_interview(req: InterviewAnswerRequest,
                           user: MaooUser = Depends(require_login)) -> InterviewAnswerResponse:
    result = await interview_service.answer_interview(user, req.session_id, req.answer)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "提交失败"))
    return InterviewAnswerResponse(**result)


@router.get("/report/{session_id}", response_model=ReportResponse)
async def get_report(session_id: str,
                     user: MaooUser = Depends(require_login)) -> ReportResponse:
    data = await interview_service.get_report(user, session_id)
    if not data:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ReportResponse(**data)


@router.get("/history", response_model=HistoryResponse)
async def history(user: MaooUser = Depends(require_login)) -> HistoryResponse:
    items = await interview_service.list_history(user)
    return HistoryResponse(items=items)
