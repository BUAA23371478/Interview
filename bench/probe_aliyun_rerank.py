"""
Probe Aliyun qwen3.7-text-rerank on multiple URL+payload patterns.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from app.config import settings


async def try_call(url: str, key: str, payload: dict, label: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(url,
                            headers={"Authorization": f"Bearer {key}",
                                     "Content-Type": "application/json"},
                            json=payload)
        if r.status_code != 200:
            return {"label": label, "status": r.status_code, "body": r.text[:240]}
        data = r.json()
        # Aliyun dashscope 原生协议返回结构：output.results
        output = data.get("output") or {}
        results = output.get("results") or data.get("results") or []
        return {"label": label, "status": 200, "results_count": len(results),
                "first_score": results[0].get("relevance_score") if results else None,
                "sample_keys": list(data.keys())[:6],
                "output_keys": list(output.keys())[:6] if output else []}
    except Exception as e:
        return {"label": label, "exception": f"{type(e).__name__}: {e}"}


async def main() -> None:
    key = settings.provider_key("aliyun")

    # DashScope 原生协议：payload 在 input.* 下
    dashscope_payload = {
        "model": "qwen3.7-text-rerank",
        "input": {
            "query": "什么是混合检索",
            "documents": ["混合检索结合向量与关键词", "红烧肉的做法"]
        },
        "parameters": {"top_n": 2, "return_documents": False}
    }
    # OpenAI 兼容协议：payload 顶层 query/documents
    openai_payload = {
        "model": "qwen3.7-text-rerank",
        "query": "什么是混合检索",
        "documents": ["混合检索结合向量与关键词", "红烧肉的做法"],
        "top_n": 2, "return_documents": False
    }

    cases = [
        ("https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
         dashscope_payload, "dashscope-原生-input"),
        ("https://dashscope.aliyuncs.com/compatible-mode/v1/rerank",
         openai_payload, "dashscope-兼容-openai"),
        # maas 私域：先试原生协议
        ("https://llm-cfwa544aykj7ljbo.cn-beijing.maas.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
         dashscope_payload, "maas-原生-input"),
        ("https://llm-cfwa544aykj7ljbo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/rerank",
         openai_payload, "maas-兼容-openai"),
    ]

    for url, payload, label in cases:
        print(f"--- {label} ---")
        result = await try_call(url, key, payload, label)
        for k, v in result.items():
            if k != "label":
                print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())