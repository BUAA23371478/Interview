"""
Embedding 客户端（OpenAI 兼容 /embeddings）。

- 未配置 key 或调用失败时启用确定性 mock（SHA-256 派生 256 维单位向量）
- 维度在运行时从 API 响应探测
"""
from __future__ import annotations

import hashlib
import struct
from typing import List, Optional

import httpx
from loguru import logger

from app.config import settings

MOCK_DIM = 256


def _mock_embed(text: str) -> List[float]:
    """确定性 mock：从文本哈希派生一个 256 维单位向量。"""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [float(b) for b in digest]  # 32 字节
    # 扩到 256 维：用 digest 作为种子做多次扩展
    while len(vec) < MOCK_DIM:
        digest = hashlib.sha256(digest + text.encode("utf-8")).digest()
        vec.extend(float(b) for b in digest)
    vec = vec[:MOCK_DIM]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


class EmbeddingClient:
    """统一嵌入客户端。"""

    def __init__(self) -> None:
        self._api_key = settings.embedding_api_key or settings.llm_api_key
        self._base_url = settings.embedding_base_url
        self._model = settings.embedding_model
        self._dimension: Optional[int] = None
        self._api_failed = False

    @property
    def enabled(self) -> bool:
        return bool(self._api_key) and not self._api_failed

    async def embed(self, text: str) -> List[float]:
        if not self._api_key or self._api_failed:
            return _mock_embed(text)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": text},
                )
                resp.raise_for_status()
                data = resp.json()["data"][0]["embedding"]
                self._dimension = len(data)
                return data
        except Exception as e:  # noqa: BLE001
            self._api_failed = True
            logger.warning("Embedding API 失败，切换到 mock：{}", e)
            return _mock_embed(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not self._api_key or self._api_failed:
            return [_mock_embed(t) for t in texts]
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": texts},
                )
                resp.raise_for_status()
                items = sorted(resp.json()["data"], key=lambda x: x["index"])
                vectors = [it["embedding"] for it in items]
                if vectors:
                    self._dimension = len(vectors[0])
                return vectors
        except Exception as e:  # noqa: BLE001
            self._api_failed = True
            logger.warning("Embedding batch API 失败，切换到 mock：{}", e)
            return [_mock_embed(t) for t in texts]

    def test_connection(self) -> dict:
        if not self._api_key:
            return {"ok": False, "model": self._model, "dimension": MOCK_DIM, "error": "未配置 API Key，运行在 mock 模式"}
        if self._api_failed:
            return {"ok": False, "model": self._model, "dimension": MOCK_DIM, "error": "API 调用失败，已降级 mock"}
        return {"ok": True, "model": self._model, "dimension": self._dimension}


def pack_vector(vec: List[float]) -> bytes:
    """向量 → BLOB。"""
    return struct.pack(f">{len(vec)}d", *vec)


def unpack_vector(blob: bytes) -> List[float]:
    """BLOB → 向量。"""
    n = len(blob) // 8
    return list(struct.unpack(f">{n}d", blob))


def cosine_similarity(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = sum(v * v for v in a[:n]) ** 0.5 or 1.0
    nb = sum(v * v for v in b[:n]) ** 0.5 or 1.0
    return dot / (na * nb)


embedding_client = EmbeddingClient()
