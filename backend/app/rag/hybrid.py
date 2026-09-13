"""
混合检索：向量 + BM25 双路，融合排序。

融合模式（`RAG_FUSION_MODE`）
----------------------------
1. `rrf`（默认）：Reciprocal Rank Fusion，只用名次、不用分数。
   优点是对两路分数量纲不敏感；缺点是**权重必须调**——
   若某一路在当前语料上明显更强，固定权重会让弱通道把强通道的正确结果挤下去。
   实测（bench/retrieval_eval_result.md）：在「查询=小标题」的评测集上，
   BM25 单路 Recall@5 98.0%，而 0.6/0.4 的 RRF 融合只有 53.3% —— 融合反而更差。
2. `score_norm`：两路各自 min-max 归一化后加权求和。
   对「某一路整体更强」的语料更稳，权重同样可配。

结论：**融合不是免费的**，权重必须用 `bench/retrieval_eval.py` 按目标语料实测确定，
因此权重与模式都做成配置项，而不是写死在代码里。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from app.config import settings
from app.rag.bm25 import bm25_retriever
from app.rag.vector_store import vector_store

FUSION_RRF = "rrf"
FUSION_SCORE_NORM = "score_norm"


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


def _minmax(values: List[float]) -> List[float]:
    """min-max 归一化；全等时统一给 0.0（该通道不提供区分度）。"""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def score_norm_fusion(
    vector_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    *,
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> List[Dict[str, Any]]:
    """两路各自 min-max 归一化后加权求和，保留分数量纲信息。

    与 RRF 的差异：RRF 里第 1 名与第 20 名只差 (1/61 - 1/80)，
    弱通道的「第 1 名」也会压过强通道的「第 5 名」；
    score_norm 保留了「这一路的置信度有多高」，强通道的优势能真实体现。
    """
    out: Dict[str, Dict[str, Any]] = {}

    def _accumulate(results: List[Dict[str, Any]], weight: float) -> None:
        if not results:
            return
        normed = _minmax([float(r.get("score", 0.0) or 0.0) for r in results])
        for r, s in zip(results, normed):
            item = out.setdefault(r["id"], {"doc": r, "score": 0.0})
            item["score"] += weight * s

    _accumulate(vector_results, vector_weight)
    _accumulate(bm25_results, bm25_weight)

    merged = sorted(out.values(), key=lambda x: x["score"], reverse=True)
    return [{
        "id": m["doc"]["id"],
        "doc_id": m["doc"].get("doc_id", ""),
        "content": m["doc"]["content"],
        "metadata": m["doc"].get("metadata", {}),
        "score": round(m["score"], 4),
        "source": "hybrid",
    } for m in merged]


def fuse(vector_results: List[Dict[str, Any]], bm25_results: List[Dict[str, Any]],
         *, mode: str = "", vector_weight: float | None = None,
         bm25_weight: float | None = None) -> List[Dict[str, Any]]:
    """按配置选择融合算法（统一入口，便于 A/B）。"""
    mode = mode or getattr(settings, "rag_fusion_mode", FUSION_RRF)
    vw = settings.rag_vector_weight if vector_weight is None else vector_weight
    bw = settings.rag_bm25_weight if bm25_weight is None else bm25_weight
    if mode == FUSION_SCORE_NORM:
        return score_norm_fusion(vector_results, bm25_results,
                                 vector_weight=vw, bm25_weight=bw)
    return reciprocal_rank_fusion(vector_results, bm25_results,
                                  vector_weight=vw, bm25_weight=bw,
                                  k=settings.rag_rrf_k)


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

        merged = fuse(vec_results, bm25_results)
        return merged[:top_k]

    def stats(self) -> Dict[str, Any]:
        return {
            "bm25": bm25_retriever.stats(),
            "fusion_mode": getattr(settings, "rag_fusion_mode", FUSION_RRF),
            "weights": {"vector": settings.rag_vector_weight,
                        "bm25": settings.rag_bm25_weight},
        }


hybrid_retriever = HybridRetriever()
