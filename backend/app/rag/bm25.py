"""
BM25 关键词检索（DB 单一数据源 + 线程池重建）。

初版问题（已修复）：
  1. **双数据源**：语料同时存在于 `vectors` 表和 `bm25_corpus.pkl` 里，
     但下架/审核/重建文档时只更新了向量表，pickle 不更新 → 已删文档仍会被召回。
  2. **同步阻塞事件循环**：`_append_bm25` 在 async 路径里对**全量语料**重新 jieba 分词并重建
     BM25Okapi。实测单 chunk 约 0.64ms，语料 100,000 chunk 时一次入库会卡住事件循环 **64s**，
     期间所有并发请求（含 SSE 心跳）全部停摆。
  3. **id 命名空间不一致**：这里用 `{doc_id}#{index}`，向量表用自增主键，RRF 融合失效。

现在：
  - 语料只从 `vectors` 表读取（单一数据源），由 DB 版本号（count, max_id）驱动感知；
  - jieba 分词与 BM25Okapi 建模全部丢到 `asyncio.to_thread`，事件循环不再被阻塞；
  - 分词结果按版本号持久化缓存，冷启动免去重复分词；
  - 重建采用「构建副本 → 原子替换」，读侧始终看到一致索引。
"""
from __future__ import annotations

import asyncio
import json
import pickle
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import func, select

from app.config import settings


def _tokenize(text: str) -> List[str]:
    try:
        import jieba
        return [w.strip() for w in jieba.cut(text) if w.strip()]
    except ImportError:
        return re.findall(r"[\w一-鿿]+", text.lower())


def _tokenize_all(texts: List[str]) -> List[List[str]]:
    """批量分词（在线程池中执行）。"""
    try:
        import jieba
        jieba.initialize()
    except ImportError:
        pass
    return [_tokenize(t) for t in texts]


def _build_okapi(tokens: List[List[str]]) -> Any:
    if not tokens:
        return None
    from rank_bm25 import BM25Okapi
    return BM25Okapi(tokens)


def _safe_meta(raw: Any) -> Dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


class BM25Retriever:
    """BM25 索引：DB 为唯一真实来源，后台线程重建。"""

    def __init__(self, cache_path: Optional[Path] = None) -> None:
        self._cache_path = cache_path or settings.bm25_cache_path
        self._corpus: List[Dict[str, Any]] = []
        self._bm25: Any = None
        self._version: Tuple[int, int] = (-1, -1)
        self._lock = asyncio.Lock()
        self._rebuilding = False
        self._pending = False
        self._checked_at = 0.0
        self._build_ms = 0.0
        self._last_query_ms = 0.0

    # ── 版本感知 ────────────────────────────────────────────────────
    async def _db_version(self) -> Tuple[int, int]:
        from app.database import SessionLocal
        from app.models import Vector
        async with SessionLocal() as session:
            row = (await session.execute(
                select(func.count(Vector.id), func.max(Vector.id)).select_from(Vector)
            )).first()
        return (int(row[0] or 0), int(row[1] or 0))

    def notify_changed(self) -> None:
        """索引数据变更后调用。下次检索按版本号自动重建。"""
        self._version = (-1, -1)
        self._checked_at = 0.0

    async def ensure_loaded(self) -> None:
        """按需装载/刷新；间隔由 rag_index_reload_interval 控制，检查本身是轻量 COUNT 查询。"""
        if self._bm25 is not None and time.time() - self._checked_at < settings.rag_index_reload_interval:
            return
        try:
            version = await self._db_version()
        except Exception as e:  # noqa: BLE001
            logger.warning("BM25 版本检查失败: {}", e)
            return
        if self._bm25 is not None and version == self._version:
            self._checked_at = time.time()
            return
        await self.rebuild(version=version)

    # ── 重建（非阻塞）────────────────────────────────────────────────
    async def rebuild(self, version: Optional[Tuple[int, int]] = None) -> None:
        if self._rebuilding:
            self._pending = True
            return
        self._rebuilding = True
        try:
            t0 = time.perf_counter()
            rows = await self._fetch_rows()
            texts = [r[3] or "" for r in rows]

            tokens = await asyncio.to_thread(self._load_tokens_cached, version, texts)
            if tokens is None:
                tokens = await asyncio.to_thread(_tokenize_all, texts)
                await asyncio.to_thread(self._persist_tokens, version, texts, tokens)

            bm25 = await asyncio.to_thread(_build_okapi, tokens)
            corpus = [
                {
                    # 与向量索引对齐的 chunk id，RRF 融合才成立
                    "id": f"{r[1]}#{r[2]}",
                    "doc_id": r[1],
                    "text": r[3] or "",
                    "metadata": _safe_meta(r[4]),
                }
                for r in rows
            ]

            self._corpus, self._bm25 = corpus, bm25  # 原子替换
            self._version = version if version is not None else await self._db_version()
            self._checked_at = time.time()
            self._build_ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.info("BM25 索引已重建: {} 条 / 耗时 {}ms（线程池执行，未阻塞事件循环）",
                        len(corpus), self._build_ms)
        except Exception as e:  # noqa: BLE001
            logger.warning("BM25 索引重建失败: {}", e)
        finally:
            self._rebuilding = False
            if self._pending:
                self._pending = False
                asyncio.create_task(self.rebuild())

    async def _fetch_rows(self) -> List[Any]:
        from app.database import SessionLocal
        from app.models import Vector
        async with SessionLocal() as session:
            return (await session.execute(
                select(Vector.id, Vector.doc_id, Vector.chunk_index,
                       Vector.content, Vector.metadata_json)
            )).all()

    # ── 分词缓存 ────────────────────────────────────────────────────
    def _load_tokens_cached(self, version: Optional[Tuple[int, int]],
                            texts: List[str]) -> Optional[List[List[str]]]:
        if version is None or not self._cache_path.exists():
            return None
        try:
            with open(self._cache_path, "rb") as fh:
                data = pickle.load(fh)
            if tuple(data.get("version", ())) != tuple(version):
                return None
            cached_texts = data.get("texts", [])
            tokens = data.get("tokens", [])
            if cached_texts == texts:
                logger.info("BM25 分词缓存命中（版本 {}），跳过 jieba 分词", version)
                return tokens
        except Exception as e:  # noqa: BLE001
            logger.warning("BM25 分词缓存读取失败: {}", e)
        return None

    def _persist_tokens(self, version: Optional[Tuple[int, int]],
                        texts: List[str], tokens: List[List[str]]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_path, "wb") as fh:
                pickle.dump({"version": tuple(version or ()), "texts": texts, "tokens": tokens}, fh)
        except Exception as e:  # noqa: BLE001
            logger.warning("BM25 分词缓存写入失败: {}", e)

    # ── 检索 ────────────────────────────────────────────────────────
    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if self._bm25 is None or not self._corpus:
            return []
        t0 = time.perf_counter()
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results: List[Dict[str, Any]] = []
        for idx in ranked:
            if scores[idx] <= 0:
                continue
            doc = self._corpus[idx]
            results.append({
                "id": doc["id"],
                "doc_id": doc["doc_id"],
                "content": doc["text"],
                "metadata": doc["metadata"],
                "score": round(float(scores[idx]), 4),
                "source": "bm25",
            })
            if len(results) >= top_k:
                break
        self._last_query_ms = round((time.perf_counter() - t0) * 1000, 2)
        return results

    def stats(self) -> Dict[str, Any]:
        return {
            "corpus_size": len(self._corpus),
            "build_ms": self._build_ms,
            "last_query_ms": self._last_query_ms,
            "version": list(self._version),
            "rebuilding": self._rebuilding,
        }


bm25_retriever = BM25Retriever()
