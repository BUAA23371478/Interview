"""
Embedding 客户端（OpenAI 兼容 /embeddings）。

相比初版的三处关键修正：
1. **不再永久降级**：API 失败只影响当前请求，并进入冷却期（cooldown）后自动恢复；
   初版一旦失败就把 _api_failed 置 True 且永不复位，整个进程静默退化为 mock 向量。
2. **维度显式校验**：mock(256 维) 与 bge-m3(1024 维) 混库时直接判定为不兼容，
   而不是在 cosine_similarity 里用 min(len) 静默截断比较（那会让检索质量无声崩塌）。
3. **查询向量 LRU 缓存**：同一 query 重复检索（追问、重试、多路复用）不再重复计费。
"""
from __future__ import annotations

import hashlib
import struct
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import httpx
from loguru import logger

from app.config import settings

MOCK_DIM = 256
MAGIC_F32 = b"F32/"
MAGIC_F64 = b"F64/"


def _mock_embed(text: str) -> List[float]:
    """确定性 mock：从文本哈希派生一个 256 维单位向量。"""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [float(b) for b in digest]  # 32 字节
    while len(vec) < MOCK_DIM:
        digest = hashlib.sha256(digest + text.encode("utf-8")).digest()
        vec.extend(float(b) for b in digest)
    vec = vec[:MOCK_DIM]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


class EmbeddingClient:
    """统一嵌入客户端。

    失败处理策略：每次失败记录 `_fail_until` 时间戳，冷却期内直接走 mock（不反复打外部 API），
    冷却期结束后自动恢复真实调用。既避免失败风暴，也不会永久丧失真实语义能力。
    """

    def __init__(self) -> None:
        self._api_key = settings.embedding_api_key or settings.llm_api_key
        self._base_url = settings.embedding_base_url
        self._model = settings.embedding_model
        self._dimension: Optional[int] = None
        self._fail_until: float = 0.0
        self._cache: "OrderedDict[str, Tuple[float, List[float]]]" = OrderedDict()
        self._cache_max = max(0, settings.embedding_cache_size)
        self._cache_ttl = settings.embedding_cache_ttl
        self._stats = {"hit": 0, "miss": 0, "fail": 0, "mock": 0}

    # ── 状态 ────────────────────────────────────────────────────────
    @property
    def cooling_down(self) -> bool:
        return time.time() < self._fail_until

    @property
    def enabled(self) -> bool:
        return bool(self._api_key) and not self.cooling_down

    @property
    def dimension(self) -> Optional[int]:
        return self._dimension

    @property
    def stats(self) -> Dict[str, object]:
        total = self._stats["hit"] + self._stats["miss"]
        out: Dict[str, object] = dict(self._stats)
        out["cache_total"] = total
        out["hit_rate"] = round(self._stats["hit"] / total, 3) if total else 0.0
        return out

    def _enter_cooldown(self, exc: Exception) -> None:
        self._fail_until = time.time() + settings.embedding_cooldown
        self._stats["fail"] += 1
        logger.warning("Embedding API 失败，进入 {}s 冷却（当前请求降级为纯关键词检索）：{}",
                       settings.embedding_cooldown, exc)

    # ── 缓存 ────────────────────────────────────────────────────────
    def _cache_get(self, text: str, *, count: bool = True) -> Optional[List[float]]:
        if self._cache_max <= 0:
            if count:
                self._stats["miss"] += 1
            return None
        item = self._cache.get(text)
        if item is None:
            if count:
                self._stats["miss"] += 1
            return None
        ts, vec = item
        if time.time() - ts > self._cache_ttl:
            self._cache.pop(text, None)
            if count:
                self._stats["miss"] += 1
            return None
        self._cache.move_to_end(text)
        if count:
            self._stats["hit"] += 1
        return vec

    def _cache_put(self, text: str, vec: List[float]) -> None:
        if self._cache_max <= 0:
            return
        self._cache[text] = (time.time(), vec)
        self._cache.move_to_end(text)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    # ── 调用 ────────────────────────────────────────────────────────
    async def embed(self, text: str) -> List[float]:
        cached = self._cache_get(text)
        if cached is not None:
            return cached
        if not self.enabled:
            self._stats["mock"] += 1
            return _mock_embed(text)
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": text},
                )
                resp.raise_for_status()
                data = resp.json()["data"][0]["embedding"]
                self._record_dim(len(data))
                self._cache_put(text, data)
                return data
        except Exception as e:  # noqa: BLE001
            self._enter_cooldown(e)
            self._stats["mock"] += 1
            return _mock_embed(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        todo = [t for t in texts if self._cache_get(t, count=False) is None]
        if todo and self.enabled:
            try:
                async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
                    resp = await client.post(
                        f"{self._base_url}/embeddings",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json={"model": self._model, "input": todo},
                    )
                    resp.raise_for_status()
                    items = sorted(resp.json()["data"], key=lambda x: x["index"])
                    vectors = [it["embedding"] for it in items]
                    if vectors:
                        self._record_dim(len(vectors[0]))
                    for t, v in zip(todo, vectors):
                        self._cache_put(t, v)
            except Exception as e:  # noqa: BLE001
                self._enter_cooldown(e)
        out: List[List[float]] = []
        for t in texts:
            hit = self._cache_get(t, count=False)
            if hit is None:
                self._stats["mock"] += 1
                hit = _mock_embed(t)
            out.append(hit)
        return out

    def _record_dim(self, dim: int) -> None:
        if self._dimension is None:
            self._dimension = dim
            logger.info("Embedding 维度探测: {}", dim)
        elif self._dimension != dim:
            logger.error("Embedding 维度变化: {} -> {}（向量索引需重建）", self._dimension, dim)

    def test_connection(self) -> dict:
        if not self._api_key:
            return {"ok": False, "model": self._model, "dimension": MOCK_DIM,
                    "error": "未配置 API Key，运行在 mock 模式"}
        if self.cooling_down:
            return {"ok": False, "model": self._model, "dimension": self._dimension or MOCK_DIM,
                    "error": f"API 处于冷却期（{settings.embedding_cooldown}s 后自动重试）"}
        return {"ok": True, "model": self._model, "dimension": self._dimension}


# ── 向量序列化：带格式头，兼容历史 float64 数据 ────────────────────────
def pack_vector(vec: List[float], dtype: str = "float32") -> bytes:
    """向量 → BLOB。

    float32 相比 float64 体积减半（1024 维 4KB vs 8KB），
    反序列化与内存拷贝开销同步减半；精度损失对余弦排序无实质影响。
    头部 4 字节魔数区分格式，历史无头数据按 float64 解析（向后兼容）。
    """
    n = len(vec)
    if dtype == "float64":
        return MAGIC_F64 + struct.pack(f">{n}d", *vec)
    return MAGIC_F32 + struct.pack(f">{n}f", *vec)


def unpack_vector(blob: bytes) -> List[float]:
    """BLOB → 向量（自动识别 float32 / float64 / 历史无头格式）。"""
    if blob[:4] == MAGIC_F32:
        n = (len(blob) - 4) // 4
        return list(struct.unpack(f">{n}f", blob[4:4 + n * 4]))
    if blob[:4] == MAGIC_F64:
        n = (len(blob) - 4) // 8
        return list(struct.unpack(f">{n}d", blob[4:4 + n * 8]))
    n = len(blob) // 8  # 历史数据：裸 float64
    return list(struct.unpack(f">{n}d", blob))


def blob_dim(blob: bytes) -> int:
    """从 BLOB 推断维度（不完整反序列化，用于快速校验）。"""
    if blob[:4] == MAGIC_F32:
        return (len(blob) - 4) // 4
    if blob[:4] == MAGIC_F64:
        return (len(blob) - 4) // 8
    return len(blob) // 8


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """余弦相似度。

    维度不一致时**抛错**而不是静默截断——初版用 min(len) 比较，
    会让 256 维 mock 向量与 1024 维真实向量之间的打分完全失去意义且无人察觉。
    """
    if len(a) != len(b):
        raise ValueError(f"向量维度不一致: {len(a)} vs {len(b)}（索引需重建）")
    n = len(a)
    dot = sum(a[i] * b[i] for i in range(n))
    na = sum(v * v for v in a) ** 0.5 or 1.0
    nb = sum(v * v for v in b) ** 0.5 or 1.0
    return dot / (na * nb)


embedding_client = EmbeddingClient()
