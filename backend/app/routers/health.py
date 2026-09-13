"""健康检查路由。"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from app.config import settings
from app.gateway.breaker import llm_breaker
from app.gateway.router import TASK_POLICY
from app.llm import llm_client
from app.embedding import embedding_client
from app.observability import spend_ledger
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


@router.get("/health/providers")
async def providers_probe() -> Dict[str, Any]:
    """主动探活三个外部依赖（LLM / Embedding / Rerank）。

    与 /health（只读缓存状态）的区别：本接口**真实发起一次调用**，
    用于上线自检、故障定位与评测取证。会消耗极少量额度，因此不做默认调用。
    """
    from app.rag.rerank import rerank_client
    return {
        "llm": await llm_client.probe(),
        "embedding": await embedding_client.probe(),
        "rerank": await rerank_client.probe(),
    }


@router.get("/health/metrics")
async def metrics() -> Dict[str, Any]:
    """检索层与运行时可观测指标。

    用于：容量规划（当前索引规模/内存占用）、性能归因（索引构建耗时、
    上次查询延迟）、降级判断（embedding 是否处于失败冷却）、成本管控
    （预算已用比例、被护栏拒绝的调用数）。
    """
    return {
        "retrieval": {
            "vector": await vector_store.stats(),
            "bm25": bm25_retriever.stats(),
            "index_type_config": settings.rag_index_type,
            "ann_threshold": settings.rag_ann_threshold,
            "fusion": {
                "mode": settings.rag_fusion_mode,
                "weights": {"vector": settings.rag_vector_weight,
                            "bm25": settings.rag_bm25_weight},
            },
            "rerank": {
                "enabled": settings.rerank_enabled,
                "candidates": settings.rerank_candidates,
            },
        },
        "embedding": embedding_client.stats,
        "llm": {**llm_client.stats(), "breakers": llm_breaker.snapshot()},
        "routing": {
            "tasks": {t: {"primary": s.primary, "fallbacks": list(s.fallbacks)}
                      for t, s in TASK_POLICY.items()},
        },
        "sse": {"active_channels": len(sse_manager._connections)},  # noqa: SLF001
        "budget": spend_ledger.snapshot(),
    }
