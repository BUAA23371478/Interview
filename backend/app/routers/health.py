"""健康检查路由。"""
from __future__ import annotations

from fastapi import APIRouter

from app.llm import llm_client
from app.embedding import embedding_client
from app.schemas import HealthResponse

router = APIRouter(tags=["健康检查"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm="real" if llm_client.enabled else "mock",
        embedding="real" if embedding_client.enabled else "mock",
    )
