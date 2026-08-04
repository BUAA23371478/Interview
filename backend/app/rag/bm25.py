"""
BM25 关键词检索。

- rank-bm25 + jieba 中文分词
- 语料缓存 pickle 到 data/bm25_corpus.pkl（缺失时返回空结果）
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.config import settings


def _tokenize(text: str) -> List[str]:
    try:
        import jieba
        return [w.strip() for w in jieba.cut(text) if w.strip()]
    except ImportError:
        import re
        return re.findall(r"[\w一-鿿]+", text.lower())


class BM25Retriever:
    def __init__(self, cache_path: Optional[Path] = None) -> None:
        self._cache_path = cache_path or settings.bm25_cache_path
        self._bm25 = None
        self._corpus: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self._cache_path.exists():
            logger.info("BM25 语料缓存不存在: {}", self._cache_path)
            return
        try:
            with open(self._cache_path, "rb") as fh:
                data = pickle.load(fh)
            self._corpus = data.get("corpus", [])
            from rank_bm25 import BM25Okapi
            tokenized = [_tokenize(d["text"]) for d in self._corpus]
            self._bm25 = BM25Okapi(tokenized) if tokenized else None
            logger.info("BM25 加载 {} 条语料", len(self._corpus))
        except Exception as e:  # noqa: BLE001
            logger.warning("BM25 加载失败: {}", e)
            self._bm25 = None

    @staticmethod
    def build_corpus_cache(nodes: List[Dict[str, Any]], cache_path: Optional[Path] = None) -> None:
        cache_path = cache_path or settings.bm25_cache_path
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "wb") as fh:
            pickle.dump({"corpus": nodes}, fh)
        logger.info("BM25 语料缓存已写入: {} 条", len(nodes))

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self._bm25 or not self._corpus:
            return []
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
                "doc_id": doc.get("doc_id", ""),
                "content": doc["text"],
                "metadata": doc.get("metadata", {}),
                "score": round(float(scores[idx]), 4),
                "source": "bm25",
            })
            if len(results) >= top_k:
                break
        return results


bm25_retriever = BM25Retriever()
