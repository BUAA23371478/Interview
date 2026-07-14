from fastapi import APIRouter, Depends, Header, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import get_db
from backend.llm.client import UnifiedLLMClient
from backend.schemas.request import PracticeStartRequest, SubmitAnswerRequest
from backend.schemas.response import PracticeStartResponse, PracticeStatsResponse
from backend.services.history_service import HistoryService
from backend.services.practice_service import PracticeService
from backend.sse.manager import sse_manager

router = APIRouter(prefix="/api/practice", tags=["practice"])
llm_client = UnifiedLLMClient()


# ---- 注意：静态路由 /stats 必须在 /{session_id} 动态路由之前定义 ----

@router.get("/stats", response_model=PracticeStatsResponse)
async def practice_stats(user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> PracticeStatsResponse:
    stats = await HistoryService(db).practice_stats(user_id)
    return PracticeStatsResponse(**stats)


@router.post("/start", response_model=PracticeStartResponse)
async def start_practice(req: PracticeStartRequest, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> PracticeStartResponse:
    service = PracticeService(db, llm_client, sse_manager)
    session = await service.create_session(user_id, req.topic, req.max_questions)
    return PracticeStartResponse(sessionId=str(session.id))


@router.get("/{session_id:int}/status")
async def practice_status(session_id: int, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    service = PracticeService(db, llm_client, sse_manager)
    status = service.get_status(session_id, user_id)
    if not status:
        return {"phase": "error", "difficulty": 3, "questionIndex": 0, "topic": ""}
    return status


@router.get("/{session_id:int}/stream")
async def practice_stream(session_id: int, user_id: int = Query(alias="user_id")):
    # SSE 长连接不持有 DB session，避免 SQLite 锁表
    service = PracticeService(None, llm_client, sse_manager)
    return EventSourceResponse(service.stream_session(session_id, user_id), media_type="text/event-stream")


@router.post("/{session_id:int}/answer")
async def submit_answer(session_id: int, req: SubmitAnswerRequest, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    service = PracticeService(db, llm_client, sse_manager)
    await service.submit_answer(session_id, user_id, req.answer, req.time_spent_seconds)
    return {"status": "ok"}


@router.post("/{session_id:int}/next")
async def next_question(session_id: int, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    service = PracticeService(db, llm_client, sse_manager)
    await service.request_next(session_id, user_id)
    return {"status": "ok"}


@router.post("/{session_id:int}/skip")
async def skip_question(session_id: int, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    """跳过当前题目（不了解），直接查看参考答案，不调 LLM 评估。"""
    service = PracticeService(db, llm_client, sse_manager)
    await service.skip_question(session_id, user_id)
    return {"status": "ok"}
