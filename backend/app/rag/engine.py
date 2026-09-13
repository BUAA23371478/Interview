"""
RAG 查询引擎：混合检索 → （可选 Cross-Encoder 精排）→ 组装 Agent 上下文。

两阶段结构（工业标准「召回 → 精排」）：
  阶段一 召回：向量 + BM25 双路，各自取 CANDIDATES 条，融合后得到候选集（快、广）
  阶段二 精排：Cross-Encoder 对 (query, 候选) 逐条打分重排（慢、准）

为什么精排必须单独一层：双塔向量模型把 query 与文档**分开**编码，
丢掉了两者之间的词级交互，对否定、条件、数字、专有名词的区分能力很弱；
Cross-Encoder 把两者拼起来一起过模型，精度显著更高，但无法预计算，
所以只能用在召回后的少量候选上。

对外提供：
    hybrid_query(query, top_k)              -> List[hit]（仅召回+融合，最快）
    full_query(query, top_k)                -> List[hit]（召回+融合+精排，最准）
    search_for_agent(query, top_k)          -> str（prompt-ready 上下文）
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from loguru import logger

from app.config import settings
from app.llm import llm_client, parse_json_response
from app.rag.hybrid import hybrid_retriever
from app.rag.rerank import rerank_client


def _fmt_hit(hit: Dict[str, Any]) -> Dict[str, Any]:
    meta = hit.get("metadata", {})
    return {
        "id": hit.get("id", ""),
        "doc_id": hit.get("doc_id", ""),
        "content": hit.get("content", ""),
        "doc_title": meta.get("doc_title", ""),
        "category": meta.get("category", ""),
        "score": hit.get("score", 0.0),
        "rerank_score": hit.get("rerank_score"),
        "source": hit.get("source", ""),
    }


class QueryEngine:
    def __init__(self) -> None:
        self._last_rerank_applied = False

    async def hybrid_query(self, query: str, top_k: int | None = None,
                           filter_meta: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        hits = await hybrid_retriever.retrieve(query, top_k=top_k, filter_meta=filter_meta)
        return [_fmt_hit(h) for h in hits]

    async def full_query(self, query: str, top_k: int | None = None,
                         filter_meta: Dict[str, Any] | None = None,
                         use_rerank: bool | None = None) -> List[Dict[str, Any]]:
        """召回 → 精排 → 截断。精排不可用时自动回退为融合原序（不影响可用性）。"""
        top_k = top_k or settings.rag_top_k
        want = settings.rerank_enabled if use_rerank is None else use_rerank
        pool = top_k * 3 if want else top_k
        candidates = await hybrid_retriever.retrieve(query, top_k=pool,
                                                     filter_meta=filter_meta)
        if not candidates:
            self._last_rerank_applied = False
            return []
        if not want:
            self._last_rerank_applied = False
            return [_fmt_hit(h) for h in candidates[:top_k]]

        ranked, applied = await rerank_client.rerank(query, candidates, top_k=top_k)
        self._last_rerank_applied = applied
        if not applied:
            logger.debug("精排未应用（未启用/无 Key/调用失败），返回融合原序")
        return [_fmt_hit(h) for h in ranked[:top_k]]

    async def _llm_rerank(self, query: str, candidates: List[Dict[str, Any]],
                          top_k: int) -> List[Dict[str, Any]]:
        """LLM listwise 精排（备选方案）。

        与 Cross-Encoder 的取舍：LLM 能利用语义与指令理解，但需要把候选全文塞进
        上下文（token 成本随候选数线性增长、延迟高、且只能输出名次无法给分数）；
        Cross-Encoder 更便宜更快且分数可校准。默认不用，留作对照实验。
        """
        try:
            docs = candidates[: settings.rerank_candidates]
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
            seen = {d["id"] for d in ranked}
            ranked.extend(d for d in docs if d["id"] not in seen)
            return ranked[:top_k]
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM rerank 失败，保持原序: {}", e)
            return candidates

    async def search_for_agent(self, query: str, top_k: int | None = None,
                               filter_meta: Dict[str, Any] | None = None) -> str:
        """返回 prompt-ready 的知识库上下文文本。

        给 Agent 出题用的参考资料走**精排后**的结果：出题只看 top_k 条，
        把最相关的挤进这 5 条，比多给 10 条噪音更有价值。
        """
        hits = await self.full_query(query, top_k=top_k, filter_meta=filter_meta)
        if not hits:
            return ""
        parts = []
        for h in hits:
            title = h.get("doc_title") or h.get("category") or ""
            header = f"[{title}]" if title else ""
            parts.append(f"{header}\n{h['content']}")
        return "\n\n---\n\n".join(parts)

    def stats(self) -> Dict[str, Any]:
        return {"last_rerank_applied": self._last_rerank_applied,
                "rerank": rerank_client.stats()}


query_engine = QueryEngine()
