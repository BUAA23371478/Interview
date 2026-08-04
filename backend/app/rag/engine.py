"""
RAG 查询引擎：混合检索 → （可选 LLM 精排）→ 组装 Agent 上下文。

对外提供：
    hybrid_query(query, top_k)              -> List[hit]
    full_query(query, top_k, use_rerank)    -> List[hit]（含 LLM 精排）
    search_for_agent(query, top_k)          -> str（prompt-ready 上下文）
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from loguru import logger

from app.config import settings
from app.llm import llm_client, parse_json_response
from app.rag.hybrid import hybrid_retriever


def _fmt_hit(hit: Dict[str, Any]) -> Dict[str, Any]:
    meta = hit.get("metadata", {})
    return {
        "id": hit.get("id", ""),
        "doc_id": hit.get("doc_id", ""),
        "content": hit.get("content", ""),
        "doc_title": meta.get("doc_title", ""),
        "category": meta.get("category", ""),
        "score": hit.get("score", 0.0),
    }


class QueryEngine:
    async def hybrid_query(self, query: str, top_k: int | None = None,
                           filter_meta: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        hits = await hybrid_retriever.retrieve(query, top_k=top_k, filter_meta=filter_meta)
        return [_fmt_hit(h) for h in hits]

    async def full_query(self, query: str, top_k: int | None = None,
                         filter_meta: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        """混合检索 + 可选 LLM 精排。"""
        top_k = top_k or settings.rag_top_k
        candidates = await hybrid_retriever.retrieve(query, top_k=top_k * 3, filter_meta=filter_meta)
        if settings.rag_use_rerank and len(candidates) > 1:
            candidates = await self._rerank(query, candidates, top_k=top_k)
        return [_fmt_hit(h) for h in candidates[:top_k]]

    async def _rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        try:
            docs = candidates[: settings.rag_max_candidates_for_rerank]
            doc_text = "\n".join(f"[{d['id']}] {d['content'][:300]}" for d in docs)
            system = (
                "你是相关性评估专家。针对用户 Query，对以下候选文档按相关性从高到低排序。"
                "只需返回排序后的 id 列表（JSON 数组），不要任何多余文字。"
            )
            user = f"Query: {query}\n候选文档:\n{doc_text}"
            raw = await llm_client.chat(system, user, temperature=0.2)
            parsed = parse_json_response(raw)
            if isinstance(parsed, list):
                order = [str(i) for i in parsed]
            elif isinstance(parsed, dict):
                order = [str(i) for i in (parsed.get("order") or parsed.get("ids") or [])]
            else:
                order = []
            by_id = {d["id"]: d for d in docs}
            ranked = [by_id[i] for i in order if i in by_id]
            # 追加未被排序的候选
            seen = {d["id"] for d in ranked}
            ranked.extend(d for d in docs if d["id"] not in seen)
            return ranked[:top_k]
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM rerank 失败，保持原序: {}", e)
            return candidates

    async def search_for_agent(self, query: str, top_k: int | None = None,
                               filter_meta: Dict[str, Any] | None = None) -> str:
        """返回 prompt-ready 的知识库上下文文本。"""
        hits = await self.hybrid_query(query, top_k=top_k, filter_meta=filter_meta)
        if not hits:
            return ""
        parts = []
        for h in hits:
            title = h.get("doc_title") or h.get("category") or ""
            header = f"[{title}]" if title else ""
            parts.append(f"{header}\n{h['content']}")
        return "\n\n---\n\n".join(parts)


query_engine = QueryEngine()
