"""面试路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.deps import MaooUser, require_login
from app.schemas import (HistoryResponse, InterviewAnswerRequest,
                         InterviewAnswerResponse, InterviewStartRequest,
                         InterviewStartResponse, ReportResponse)
from app.services import interview_service
from app.sse.emitter import (parse_last_event_id, sse_format, sse_manager)

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
        # 并发冲突用 409 明确语义：客户端可安全重试（幂等重放不会丢答题记录）
        if result.get("conflict"):
            raise HTTPException(status_code=409,
                                detail=result.get("message", "会话正在处理中，请稍后重试"))
        raise HTTPException(status_code=400, detail=result.get("message", "提交失败"))
    return InterviewAnswerResponse(**result)


@router.get("/current/{session_id}")
async def get_current(session_id: str,
                      user: MaooUser = Depends(require_login)) -> dict:
    """获取会话当前题目（前端刷新/直达时恢复第一题）。"""
    data = await interview_service.get_current_question(user, session_id)
    if not data:
        raise HTTPException(status_code=404, detail="会话不存在")
    return data


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


@router.get("/stream/{session_id}")
async def stream_session(session_id: str, request: Request,
                         user: MaooUser = Depends(require_login)) -> StreamingResponse:
    """订阅某场面试的事件流（SSE）。

    支持断线重连：浏览器/客户端会自动带上 `Last-Event-ID` 请求头，
    服务端据此回放该序号之后的所有事件，不丢进度、不重复推送。
    """
    key = interview_service._session_key(session_id)  # noqa: SLF001
    conn = await sse_manager.connect(key, user.user_id, resume=True)
    last_id = parse_last_event_id(
        request.headers.get("Last-Event-ID") or request.query_params.get("last_event_id"))

    async def _gen():
        async for ev in sse_manager.stream_events(key, conn, last_event_id=last_id):
            yield sse_format(ev["event"], ev["data"], ev.get("id"))

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 反向代理禁用缓冲，否则流式会被攒批
        },
    )
