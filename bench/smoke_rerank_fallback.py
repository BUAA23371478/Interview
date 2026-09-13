"""Smoke test: primary rerank (SiliconFlow) fails → fallback (Aliyun) succeeds."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.rag.rerank import rerank_client


async def main() -> None:
    # 1) primary 调用（如果 SiliconFlow 已 401/429，会自动切到 Aliyun）
    scores = await rerank_client.score(
        "什么是混合检索",
        ["混合检索结合向量与关键词", "红烧肉的做法"]
    )
    print(f"primary+fallback score: {scores}")
    print(f"stats: {rerank_client.stats()}")

    # 2) 主动禁用 primary key（模拟主 provider 完全不可用）
    orig_key = rerank_client._key
    orig_fb = list(rerank_client._fallbacks)
    try:
        rerank_client._key = "sk-invalid-on-purpose"
        # 强制重置缓存（用新 key 重新试）
        scores = await rerank_client.score(
            "向量召回与关键词召回怎么配合",
            ["RRF 融合按名次倒数加权", "番茄炒蛋需要大火收汁"]
        )
        print(f"primary-broken+fallback score: {scores}")
        print(f"stats: {rerank_client.stats()}")
    finally:
        rerank_client._key = orig_key
        rerank_client._fallbacks = orig_fb


if __name__ == "__main__":
    asyncio.run(main())