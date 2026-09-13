"""
混合检索：向量 + BM25 双路，RRF 融合。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from app.config import settings
from app.rag.bm25 import bm25_retriever
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
    """向量 + BM25 双路召回，RRF 融合。

    修复点：
      1. 复用全局单例 BM25 索引（初版每实例化一次就重建一份语料，内存与分词成本翻倍）；
      2. 两路召回并发执行（asyncio.gather），串行等待改为并行；
      3. BM25 结果也做 metadata 过滤——初版只过滤了向量路，
         导致 `{"status": "approved"}` 这类过滤形同虚设，未过审文档仍可能被关键词路召回。
    """

    async def retrieve(self, query: str, top_k: int | None = None,
                       filter_meta: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        top_k = top_k or settings.rag_top_k
        await bm25_retriever.ensure_loaded()

        vec_task = vector_store.search(query, top_k=top_k * 2, filter_meta=filter_meta)
        vec_results, bm25_results = await asyncio.gather(
            vec_task,
            asyncio.to_thread(bm25_retriever.retrieve, query, top_k * 2),
        )

        if filter_meta:
            bm25_results = [
                r for r in bm25_results
                if all(r.get("metadata", {}).get(k) == v for k, v in filter_meta.items())
            ]

        merged = reciprocal_rank_fusion(
            vec_results,
            bm25_results,
            vector_weight=settings.rag_vector_weight,
            bm25_weight=settings.rag_bm25_weight,
            k=settings.rag_rrf_k,
        )
        return merged[:top_k]

    def stats(self) -> Dict[str, Any]:
        return {"bm25": bm25_retriever.stats()}


hybrid_retriever = HybridRetriever()
