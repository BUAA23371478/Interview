"""
混合检索：向量 + BM25 双路，RRF 融合。
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.config import settings
from app.rag.bm25 import BM25Retriever
from app.rag.vector_store import vector_store


def reciprocal_rank_fusion(
    vector_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    *,
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """RRF: score = w1/(k+rank1) + w2/(k+rank2)"""
    score_map: Dict[str, Dict[str, Any]] = {}
    for rank, r in enumerate(vector_results):
        rid = r["id"]
        score_map.setdefault(rid, {"doc": r, "rrf": 0.0})
        score_map[rid]["rrf"] += vector_weight / (k + rank + 1)
    for rank, r in enumerate(bm25_results):
        rid = r["id"]
        score_map.setdefault(rid, {"doc": r, "rrf": 0.0})
        score_map[rid]["rrf"] += bm25_weight / (k + rank + 1)
    merged = sorted(score_map.values(), key=lambda x: x["rrf"], reverse=True)
    out = []
    for m in merged:
        doc = m["doc"]
        out.append({
            "id": doc["id"],
            "doc_id": doc.get("doc_id", ""),
            "content": doc["content"],
            "metadata": doc.get("metadata", {}),
            "score": round(m["rrf"], 4),
            "source": "hybrid",
        })
    return out


class HybridRetriever:
    def __init__(self) -> None:
        self._bm25 = BM25Retriever()

    async def retrieve(self, query: str, top_k: int | None = None,
                       filter_meta: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        top_k = top_k or settings.rag_top_k
        vec_results = await vector_store.search(query, top_k=top_k * 2, filter_meta=filter_meta)
        bm25_results = self._bm25.retrieve(query, top_k=top_k * 2)
        merged = reciprocal_rank_fusion(
            vec_results,
            bm25_results,
            vector_weight=settings.rag_vector_weight,
            bm25_weight=settings.rag_bm25_weight,
            k=settings.rag_rrf_k,
        )
        return merged[:top_k]


hybrid_retriever = HybridRetriever()
