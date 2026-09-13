"""
Cross-Encoder 精排（rerank）客户端。

为什么需要它
------------
向量检索是「双塔」结构：query 与文档各自独立编码成向量，只比向量距离。
好处是能离线建索引、查询极快；代价是**丢失了 query 与文档之间的细粒度交互**——
否定（"不需要事务"）、条件（"仅在 MySQL 下"）、数字与专有名词的精确匹配，
双塔很难区分，Cross-Encoder 却可以，因为它把 (query, document) 拼接后一起过模型。

工程上的取舍：Cross-Encoder 无法预计算，必须对每个候选现场推理，
所以只对**召回的少量候选**（默认 20 条）做精排，整体仍是毫秒级。
这就是工业界标准的「召回 → 精排」两阶段结构。

本模块同时承担：
  - 与查询/候选的磁盘缓存（A/B 复测不重复调用）
  - 失败降级：精排异常时返回原序，绝不让检索整体失败
  - 探活与统计，供 /health/metrics 取证
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
from loguru import logger

from app.config import BACKEND_DIR, settings


class RerankResult:
    __slots__ = ("index", "score")

    def __init__(self, index: int, score: float) -> None:
        self.index = index
        self.score = score


def _cache_path() -> Path:
    if settings.embedding_cache_db:
        p = Path(settings.embedding_cache_db)
        base = p if p.is_absolute() else (BACKEND_DIR.parent / p)
        return base.with_name("rerank_cache.db")
    return settings.data_dir / "rerank_cache.db"


class RerankClient:
    """Cross-Encoder 精排客户端（OpenAI 兼容之外的 /rerank 协议）。

    多 provider 降级设计：
      - 主用 RERANK_* 配置（默认 SiliconFlow bge-reranker-v2-m3）
      - 备用列表 RERANK_FALLBACKS（json 字符串），如
        [{"provider": "aliyun", "base_url": "https://.../compatible-mode/v1",
          "model": "qwen3.7-text-rerank"}]
      - 主调用失败 → 自动按备用列表顺序尝试；全部失败才回退为融合原序
      - 缓存按 (provider, model) 分桶，避免不同模型的分数混用
    """

    def __init__(self) -> None:
        self._key = (settings.rerank_api_key or settings.embedding_api_key
                     or settings.llm_api_key or "").strip()
        self._base = settings.rerank_base_url.rstrip("/")
        self._model = settings.rerank_model
        self._fails = 0
        self._last_error = ""
        self._last_ms = 0.0
        self._calls = 0
        self._cache_hits = 0
        self._fallback_attempts = 0
        self._fallback_successes = 0
        self._provider_used = self._model
        self._db = self._init_cache()
        self._fallbacks = self._load_fallbacks()

    def _load_fallbacks(self) -> List[Tuple[str, str, str, str]]:
        """解析 RERANK_FALLBACKS 配置：(base_url, model, key, label)。

        base_url 是「API 根」：OpenAI 协议用 `{root}/rerank`，
        DashScope 原生用 `{root}/services/rerank/text-rerank/text-rerank`。
        """
        import json as _json
        out: List[Tuple[str, str, str, str]] = []
        raw = (getattr(settings, "rerank_fallbacks", "") or "").strip()
        if not raw:
            return out
        try:
            items = _json.loads(raw) if raw.startswith("[") else []
        except Exception:
            items = []
        for it in items:
            prov = str(it.get("provider", "")).strip()
            base = str(it.get("base_url", "")).strip().rstrip("/")
            model = str(it.get("model", "")).strip()
            if not (prov and base and model):
                continue
            key = settings.provider_key(prov) or str(it.get("api_key", "")).strip()
            if not key:
                continue
            label = f"{prov}/{model}"
            out.append((base, model, key, label))
        return out

    # ── 缓存 ────────────────────────────────────────────────────────
    def _init_cache(self) -> Optional[sqlite3.Connection]:
        try:
            path = _cache_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path), timeout=30.0, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS rk (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            conn.commit()
            return conn
        except Exception as e:  # noqa: BLE001
            logger.warning("精排缓存初始化失败: {}", e)
            return None

    def _ckey(self, query: str, docs: Sequence[str]) -> str:
        # 缓存按 model 分桶：不同模型的精排分数不可混用（量纲不同）。
        # 不依赖 _provider_used（跨调用会被状态污染），只用 (model, query, docs)。
        # 跨模型复用同一缓存不会自动失效——若切换默认模型，调用方应清空 rerank_cache.db。
        h = hashlib.sha256(
            (self._model + "\x00" + query + "\x00" + "\x00".join(docs)).encode("utf-8")
        ).hexdigest()
        return h

    def _cache_get(self, key: str) -> Optional[List[float]]:
        if self._db is None:
            return None
        try:
            row = self._db.execute("SELECT v FROM rk WHERE k=?", (key,)).fetchone()
            if row:
                self._cache_hits += 1
                return json.loads(row[0])
        except Exception:  # noqa: BLE001
            pass
        return None

    def _cache_put(self, key: str, scores: List[float]) -> None:
        if self._db is None:
            return
        try:
            self._db.execute("INSERT OR REPLACE INTO rk (k, v) VALUES (?, ?)",
                             (key, json.dumps(scores)))
            self._db.commit()
        except Exception:  # noqa: BLE001
            pass

    # ── 状态 ────────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return bool(self._key) and settings.rerank_enabled

    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": settings.rerank_enabled,
            "has_key": bool(self._key),
            "model": self._model,
            "provider": self._provider_used,
            "calls": self._calls,
            "fails": self._fails,
            "cache_hits": self._cache_hits,
            "last_ms": self._last_ms,
            "last_error": self._last_error,
            "candidates": settings.rerank_candidates,
            "fallback_attempts": self._fallback_attempts,
            "fallback_successes": self._fallback_successes,
            "fallback_providers": [lbl for _, _, _, lbl in self._fallbacks],
        }

    # ── 调用 ────────────────────────────────────────────────────────
    async def score(self, query: str, documents: Sequence[str]) -> Optional[List[float]]:
        """返回与 documents 等长的相关性分数；不可用/失败返回 None。

        多 provider 降级：主调用失败时按 RERANK_FALLBACKS 顺序尝试；
        全部失败才返回 None（调用方据此回退融合原序）。
        """
        if not self._key or not documents:
            return None
        key = self._ckey(query, documents)
        cached = self._cache_get(key)
        if cached is not None and len(cached) == len(documents):
            return cached

        # 依次尝试：主 → fallbacks
        attempts: List[Tuple[str, str, str, str, str]] = [
            (self._base, self._model, self._key, "primary", self._protocol(self._base))]
        for fb in self._fallbacks:
            attempts.append((fb[0], fb[1], fb[2], fb[3], self._protocol(fb[0])))

        last_err = ""
        for base, model, key_cred, label, protocol in attempts:
            url = self._endpoint_url(base, protocol)
            t0 = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=settings.rerank_timeout) as client:
                    self._calls += 1
                    self._provider_used = f"{label}:{model}"
                    if protocol == "openai":
                        payload = {"model": model, "query": query,
                                   "documents": list(documents),
                                   "top_n": len(documents), "return_documents": False}
                    else:  # dashscope 原生协议
                        docs_list = list(documents)
                        payload = {"model": model,
                                   "input": {"query": query, "documents": docs_list},
                                   "parameters": {"top_n": len(documents), "return_documents": False}}
                    resp = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {key_cred}",
                                 "Content-Type": "application/json"},
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                # 响应结构：openai -> {results: [...]}; dashscope -> {output: {results: [...]}}
                results = (data.get("results")
                           or (data.get("output") or {}).get("results")
                           or [])
                if not results:
                    raise RuntimeError(f"精排返回空结果: {str(data)[:200]}")
                scores = [0.0] * len(documents)
                for item in results:
                    idx = int(item.get("index", -1))
                    if 0 <= idx < len(scores):
                        scores[idx] = float(item.get("relevance_score", 0.0))
                self._last_ms = round((time.perf_counter() - t0) * 1000, 1)
                if label != "primary":
                    self._fallback_attempts += 1
                    self._fallback_successes += 1
                    # 不要把 self._model 改成 fallback 的 model —— 缓存 key 基于它，
                    # 改了会让后续调用查不到旧缓存。fallback 模型信息从 _provider_used 读取即可。
                self._cache_put(key, scores)
                return scores
            except Exception as e:  # noqa: BLE001
                last_err = f"{label} {type(e).__name__}: {e}"
                self._fails += 1
                logger.warning("精排 {} 失败，尝试下一个: {}", label, e)
                continue
        self._last_error = last_err or "no provider succeeded"
        return None

    @staticmethod
    def _endpoint_url(base_url: str, protocol: str) -> str:
        """按协议拼完整 URL。base_url 是 API 根（无路径尾巴）。"""
        if protocol == "dashscope":
            return f"{base_url}/services/rerank/text-rerank/text-rerank"
        return f"{base_url}/rerank"

    @staticmethod
    def _protocol(base_url: str) -> str:
        """根据 base_url 判断协议：
        - 'openai'        → OpenAI 兼容（payload 顶层 query/documents；POST /rerank）
        - 'dashscope'     → 阿里云 DashScope 原生（payload 在 input.*；URL 拼 services/rerank/...）
        """
        b = (base_url or "").lower()
        if "dashscope.aliyuncs.com" in b or "maas.aliyuncs.com" in b:
            return "dashscope"
        return "openai"

    async def probe(self) -> Dict[str, Any]:
        if not self._key:
            return {"ok": False, "error": "未配置 RERANK_API_KEY", "model": self._model}
        t0 = time.perf_counter()
        s = await self.score("什么是混合检索", ["混合检索结合向量与关键词", "红烧肉的做法"])
        dt = round((time.perf_counter() - t0) * 1000, 1)
        if s is None:
            return {"ok": False, "model": self._model, "error": self._last_error,
                    "latency_ms": dt}
        ok = len(s) == 2 and s[0] > s[1]
        return {"ok": ok, "model": self._model, "latency_ms": dt,
                "scores": [round(x, 4) for x in s],
                "sanity": "相关文档得分高于无关文档" if ok else "排序异常，请检查模型/额度"}

    # ── 重排 ────────────────────────────────────────────────────────
    async def rerank(self, query: str, hits: List[Dict[str, Any]],
                     top_k: int) -> Tuple[List[Dict[str, Any]], bool]:
        """对 hits 精排并截断到 top_k。返回 (结果, 是否成功应用精排)。"""
        if not self.enabled or len(hits) <= 1:
            return hits[:top_k], False
        cand = hits[: settings.rerank_candidates]
        docs = [h.get("content", "")[:2000] for h in cand]
        # 服务商对单请求文档数有上限，超限切批（同 query 不同文档，无法并行合并分数）
        batch = max(1, settings.rerank_batch)
        scores: List[Optional[float]] = [None] * len(cand)
        for i in range(0, len(cand), batch):
            part = docs[i:i + batch]
            got = await self.score(query, part)
            if got is not None:
                for j, s in enumerate(got):
                    scores[i + j] = s
        if all(s is None for s in scores):
            return hits[:top_k], False
        ranked = sorted(
            zip(cand, scores),
            key=lambda p: (-(p[1] if p[1] is not None else -1e9)),
        )
        out = []
        for h, s in ranked:
            item = dict(h)
            item["fusion_score"] = h.get("score", 0.0)
            if s is not None:
                item["rerank_score"] = round(float(s), 4)
                item["score"] = round(float(s), 4)
            item["source"] = (h.get("source", "") + "+rerank").lstrip("+")
            out.append(item)
        # 精排候选之外的原始结果按原序追加（保证召回不丢，只是排序靠后）
        tail = [h for h in hits if h not in cand]
        return (out + tail)[:top_k], True


rerank_client = RerankClient()
