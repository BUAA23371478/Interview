from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import get_db
from backend.llm.client import UnifiedLLMClient
from backend.schemas.request import InterviewCreateRequest, SubmitInterviewAnswerRequest
from backend.schemas.response import InterviewCreateResponse, InterviewReportResponse
from backend.services.interview_service import InterviewService
from backend.sse.manager import sse_manager

router = APIRouter(prefix="/api/interview", tags=["interview"])
llm_client = UnifiedLLMClient()


@router.post("/create", response_model=InterviewCreateResponse)
async def create_interview(req: InterviewCreateRequest, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> InterviewCreateResponse:
    service = InterviewService(db, llm_client, sse_manager)
    session = await service.create_session(user_id, req.jd, req.resume, req.total_rounds)
    return InterviewCreateResponse(sessionId=str(session.id))


@router.get("/{session_id:int}/stream")
async def interview_stream(session_id: int, user_id: int = Query(alias="user_id"), db: AsyncSession = Depends(get_db)):
    service = InterviewService(db, llm_client, sse_manager)
    return EventSourceResponse(service.stream_session(session_id, user_id), media_type="text/event-stream")


@router.post("/{session_id:int}/answer")
async def submit_interview_answer(session_id: int, req: SubmitInterviewAnswerRequest, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    service = InterviewService(db, llm_client, sse_manager)
    await service.submit_answer(session_id, user_id, req.answer)
    return {"status": "ok"}


@router.get("/{session_id:int}/report", response_model=InterviewReportResponse)
async def get_report(session_id: int, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> InterviewReportResponse:
    service = InterviewService(db, llm_client, sse_manager)
    result = await service.get_report(session_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="报告未生成或面试尚未完成")
    return InterviewReportResponse(**result)


@router.get("/{session_id:int}/status")
async def get_interview_status(session_id: int, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    service = InterviewService(db, llm_client, sse_manager)
    status = service.get_status(session_id, user_id)
    if not status:
        raise HTTPException(status_code=404, detail="会话不存在")
    return status
