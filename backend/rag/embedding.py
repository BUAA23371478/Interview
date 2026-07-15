"""文本向量化客户端。

优先使用 DeepSeek Embedding API，失败时自动回退到 Mock embedding。
"""

from __future__ import annotations

import hashlib
from typing import Any

import httpx
from loguru import logger

from backend.config import settings


class EmbeddingClient:
    """文本向量化客户端。

    - 优先调用 LLM 提供商的 Embedding API
    - API 首次失败后自动回退到 Mock embedding，后续不再重试（避免日志轰炸）
    - Mock 模式基于 SHA-256 哈希生成确定性向量，保证同一文本每次向量一致
    """

    def __init__(self) -> None:
        # Embedding 优先用独立配置，未配则 fallback 到 LLM 的 key/url
        self._api_key = settings.embedding_api_key or settings.llm_api_key
        self._base_url = (
            settings.embedding_base_url.rstrip("/")
            if settings.embedding_base_url
            else settings.llm_base_url.rstrip("/")
        )
        self._model = settings.embedding_model
        self._enabled = bool(self._api_key)
        self._dimension = 1536
        self._api_failed = False

    async def embed(self, text: str) -> list[float]:
        """将单段文本向量化。"""
        if not self._enabled or self._api_failed:
            return self._mock_embed(text)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "input": text,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    embedding = data["data"][0]["embedding"]
                    logger.debug(f"Embedding 成功 dim={len(embedding)}")
                    return embedding
                else:
                    # 首次失败：打一条 warning，之后静默回退
                    if not self._api_failed:
                        logger.warning(
                            f"Embedding API 不可用（{response.status_code}），"
                            "后续将使用 Mock embedding。"
                            "如需真实向量检索，请检查 LLM 提供商是否支持 Embedding API。"
                        )
                    self._api_failed = True
                    return self._mock_embed(text)
        except Exception as e:
            if not self._api_failed:
                logger.warning(f"Embedding API 调用失败: {e}，后续使用 Mock embedding。")
            self._api_failed = True
            return self._mock_embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量向量化（一次 API 调用处理多条，远快于逐条请求）。"""
        if not self._enabled or self._api_failed:
            return [self._mock_embed(t) for t in texts]

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "input": texts,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    embeddings = [item["embedding"] for item in data["data"]]
                    logger.debug(f"Batch Embedding 成功 count={len(embeddings)} dim={len(embeddings[0])}")
                    return embeddings
                else:
                    if not self._api_failed:
                        logger.warning(
                            f"Embedding API 不可用（{response.status_code}），"
                            "后续将使用 Mock embedding。"
                            "如需真实向量检索，请在 .env 中配置 EMBEDDING_BASE_URL / EMBEDDING_MODEL。"
                        )
                    self._api_failed = True
                    return [self._mock_embed(t) for t in texts]
        except Exception as e:
            if not self._api_failed:
                logger.warning(f"Embedding API 调用失败: {e}，后续使用 Mock embedding。")
            self._api_failed = True
            return [self._mock_embed(t) for t in texts]

    @property
    def dimension(self) -> int:
        return self._dimension

    # ------------------------------------------------------------------
    # Mock embedding
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_embed(text: str) -> list[float]:
        """基于 SHA-256 哈希生成确定性伪向量（256 维）。

        同一文本每次生成的向量一致，可用于功能验证。
        """
        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [(hash_bytes[i % 32] / 127.5) - 1.0 for i in range(256)]
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


# 全局单例
embedding_client = EmbeddingClient()
