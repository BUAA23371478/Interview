"""健康检查路由。"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from app.config import settings
from app.llm import llm_client
from app.embedding import embedding_client
from app.rag.bm25 import bm25_retriever
from app.rag.vector_store import vector_store
from app.schemas import HealthResponse
from app.sse.emitter import sse_manager

router = APIRouter(tags=["健康检查"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm="real" if llm_client.enabled else "mock",
        embedding="real" if embedding_client.enabled else "mock",
    )


@router.get("/health/metrics")
async def metrics() -> Dict[str, Any]:
    """检索层与运行时可观测指标。

    用于：容量规划（当前索引规模/内存占用）、性能归因（索引构建耗时、
    上次查询延迟）、降级判断（embedding 是否处于失败冷却）。
    """
    return {
        "retrieval": {
            "vector": await vector_store.stats(),
            "bm25": bm25_retriever.stats(),
            "index_type_config": settings.rag_index_type,
            "ann_threshold": settings.rag_ann_threshold,
        },
        "embedding": embedding_client.stats(),
        "llm": llm_client.stats(),
        "sse": {"active_channels": len(sse_manager._connections)},  # noqa: SLF001
    }
