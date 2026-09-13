"""
外部依赖探活与基线测量（真实调用，会产生极少量费用）。

测量对象：
  1. Embedding（SiliconFlow bge-m3）——维度、单条/批量延迟、缓存命中效果
  2. Reranker（bge-reranker-v2-m3）——可用性、相关性判别正确性、单次延迟
  3. LLM 各 provider / 各调用风格 —— 连通性、首字延迟、吞吐、JSON 结构化稳定性
  4. 跨 provider 凭据隔离 —— 这是「降级链是否真的可用」的前提

运行：
    python bench/probe_providers.py            # 全量
    python bench/probe_providers.py --list     # 只列出各端点可用模型

安全：全程只读 settings，绝不打印任何 API Key；所有费用记入统一成本流水，
      超出 LLM_BUDGET_YUAN 后后续调用会被护栏直接拒绝。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Windows 控制台默认 GBK，直接 print "¥" 会 UnicodeEncodeError 中断脚本
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

OUT = Path(__file__).with_name("probe_result.md")
CATALOG = Path(__file__).with_name("model_catalog.json")


def _mask(key: str) -> str:
    """只显示足以辨认的程度，其余打码。"""
    if not key:
        return "(空)"
    return f"{key[:8]}…{key[-4:]}（长度 {len(key)}）"


async def list_endpoint_models(base_url: str, key: str, timeout: float = 20.0) -> Dict[str, Any]:
    import httpx
    url = f"{base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                return {"ok": False, "status": r.status_code, "body": (r.text or "")[:200]}
            data = r.json().get("data") or []
            return {"ok": True, "count": len(data),
                    "ids": [d.get("id") for d in data]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def probe_embedding(rows: List[str]) -> Dict[str, Any]:
    from app.embedding import embedding_client
    res = await embedding_client.probe()
    rows.append(f"| embedding 探活 | {'✅' if res.get('ok') else '❌'} | "
                f"{res.get('model')} | 维度 {res.get('dimension')} | "
                f"{res.get('latency_ms')} ms | {res.get('error', '')} |")
    if not res.get("ok"):
        return res

    # 单条 vs 批量 vs 缓存命中
    texts = [f"批量延迟测试样本 {i}：混合检索 RRF 融合与向量召回" for i in range(32)]
    t0 = time.perf_counter()
    await embedding_client.embed_many(texts)
    batch_ms = round((time.perf_counter() - t0) * 1000, 1)
    t0 = time.perf_counter()
    await embedding_client.embed_many(texts)          # 第二次应全部命中缓存
    cached_ms = round((time.perf_counter() - t0) * 1000, 1)
    t0 = time.perf_counter()
    await embedding_client.embed("单条延迟测试：RAG 混合检索")
    single_ms = round((time.perf_counter() - t0) * 1000, 1)
    rows.append(f"| embedding 批量 32 条（冷） | ✅ | - | {len(texts)} 条 | "
                f"{batch_ms} ms（{round(batch_ms/len(texts), 1)} ms/条） | - |")
    rows.append(f"| embedding 批量 32 条（缓存命中） | ✅ | - | {len(texts)} 条 | "
                f"{cached_ms} ms | 加速 {round(batch_ms/max(cached_ms,0.01),1)}× |")
    rows.append(f"| embedding 单条 | ✅ | - | 1 条 | {single_ms} ms | - |")

    # 语义质量抽查：相关句对相似度必须高于无关句对
    base = await embedding_client.embed("什么是混合检索")
    near = await embedding_client.embed("混合检索结合向量召回与关键词检索两路")
    far = await embedding_client.embed("番茄炒蛋的家常做法")
    from app.embedding import cosine_similarity
    s_near = cosine_similarity(base, near) if base and near else 0.0
    s_far = cosine_similarity(base, far) if base and far else 0.0
    ok = s_near > s_far
    rows.append(f"| embedding 语义判别 | {'✅' if ok else '❌'} | - | 相关 {s_near:.4f} / "
                f"无关 {s_far:.4f} | 差值 {s_near - s_far:.4f} | "
                f"{'相关句更接近，语义有效' if ok else '语义判别异常'} |")
    res.update({"batch_cold_ms": batch_ms, "batch_cached_ms": cached_ms,
                "single_ms": single_ms, "sim_relevant": round(s_near, 4),
                "sim_irrelevant": round(s_far, 4), "semantic_ok": ok})
    return res


async def probe_rerank(rows: List[str]) -> Dict[str, Any]:
    from app.rag.rerank import rerank_client
    res = await rerank_client.probe()
    rows.append(f"| rerank 探活 | {'✅' if res.get('ok') else '❌'} | {res.get('model')} | "
                f"打分 {res.get('scores')} | {res.get('latency_ms')} ms | "
                f"{res.get('error', res.get('sanity', ''))} |")
    return res


async def probe_llm(rows: List[str]) -> List[Dict[str, Any]]:
    from app.config import settings
    from app.gateway.registry import MODELS
    from app.llm import llm_client, llm_model_ctx
    from app.observability import current_meter

    # 目标模型直接取自注册表——注册表本身以端点 /models 的真实 id 为准，
    # 避免探活脚本与线上配置各写一份模型名而互相漂移。
    targets = [m.id for m in MODELS]
    out: List[Dict[str, Any]] = []
    for mid in targets:
        token = llm_model_ctx.set(mid)
        try:
            t0 = time.perf_counter()
            try:
                # 结构化稳定性检查：要求返回严格 JSON
                data = await llm_client.chat_with_json(
                    "你只输出 JSON，不要解释。",
                    '返回 {"ok": true, "topic": "RAG"} 这个 JSON 对象。',
                    temperature=0.0)
                dt = (time.perf_counter() - t0) * 1000
                ok = bool(data.get("ok") is True or data.get("topic"))
                rows.append(f"| LLM {mid} | {'✅' if ok else '⚠️'} | "
                            f"{llm_client.target()[1]} | JSON 解析{'成功' if data else '失败'} | "
                            f"{round(dt, 1)} ms | {json.dumps(data, ensure_ascii=False)[:60]} |")
                out.append({"model": mid, "ok": ok, "latency_ms": round(dt, 1),
                            "json": data})
            except Exception as e:  # noqa: BLE001
                rows.append(f"| LLM {mid} | ❌ | - | - | - | "
                            f"{type(e).__name__}: {str(e)[:90]} |")
                out.append({"model": mid, "ok": False, "error": str(e)[:200]})
        finally:
            llm_model_ctx.reset(token)

    # 流式首字延迟（TTFT）—— 交互式体验最关键的指标
    stream_model = MODELS[0].id
    token = llm_model_ctx.set(stream_model)
    try:
        t0 = time.perf_counter()
        ttft: Optional[float] = None
        chars = 0
        async for chunk in llm_client.chat_stream(
                "你是面试官。", "用一句话解释什么是 RAG。", max_tokens=64):
            if ttft is None and chunk:
                ttft = (time.perf_counter() - t0) * 1000
            chars += len(chunk)
        total = (time.perf_counter() - t0) * 1000
        rows.append(f"| LLM 流式（TTFT/总时长） | ✅ | - | 首字 {round(ttft or 0, 1)} ms | "
                    f"总计 {round(total, 1)} ms / {chars} 字 | "
                    f"吞吐 {round(chars / max(total / 1000, 0.01), 1)} 字/秒 |")
        out.append({"stream_ttft_ms": round(ttft or 0, 1),
                    "stream_total_ms": round(total, 1), "chars": chars})
    except Exception as e:  # noqa: BLE001
        rows.append(f"| LLM 流式 | ❌ | - | - | - | {type(e).__name__}: {str(e)[:80]} |")
    finally:
        llm_model_ctx.reset(token)

    meter = current_meter()
    if meter is not None:
        rows.append(f"| **本轮探活合计** | - | - | {meter.snapshot()['total_tokens']} tokens | "
                    f"¥{meter.snapshot()['cost_yuan']} | "
                    f"{json.dumps(meter.snapshot()['by_model'], ensure_ascii=False)} |")
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="只列出各端点可用模型")
    args = ap.parse_args()

    from app.config import settings
    from app.observability import init_budget, new_meter, spend_ledger

    init_budget()
    new_meter()

    lines: List[str] = []
    lines.append("# 外部依赖探活与延迟基线（真实调用）")
    lines.append("")
    lines.append(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"- 成本护栏上限：¥{settings.llm_budget_yuan}，"
                 f"本轮开始前已用：¥{spend_ledger.total:.4f}")
    lines.append(f"- DeepSeek key：{_mask(settings.provider_key('deepseek'))}")
    lines.append(f"- Aliyun key：{_mask(settings.provider_key('aliyun'))}")
    lines.append(f"- Embedding：{settings.embedding_model} @ {settings.embedding_base_url}")
    lines.append(f"- Rerank：{settings.rerank_model} @ {settings.rerank_base_url}")
    lines.append("")

    # ── 端点模型清单 ──
    lines.append("## 各端点可用模型（/models）")
    lines.append("")
    lines.append("| provider | base_url | 结果 |")
    lines.append("|---|---|---|")
    providers = {
        "deepseek": (settings.provider_base_url("deepseek", "https://api.deepseek.com/v1"),
                     settings.provider_key("deepseek")),
        "aliyun": (settings.provider_base_url("aliyun",
                                              "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                   settings.provider_key("aliyun")),
        "siliconflow": (settings.embedding_base_url, settings.embedding_api_key),
    }
    listing: Dict[str, Any] = {}
    for name, (base, key) in providers.items():
        info = await list_endpoint_models(base, key, timeout=30.0)
        listing[name] = info
        if info.get("ok"):
            shown = ", ".join(str(i) for i in (info.get("ids") or [])[:14])
            tail = " …" if (info.get("count") or 0) > 14 else ""
            lines.append(f"| {name} | `{base}` | ✅ {info.get('count')} 个：{shown}{tail} |")
        else:
            lines.append(f"| {name} | `{base}` | ❌ {info.get('status') or info.get('error')} |")
    lines.append("")

    # 完整目录落盘：模型注册表要以「端点真实提供的 id」为准，
    # 凭文档或记忆写死模型名会在调用时 404（本次就踩到了：配置写 deepseek-v4-flash，
    # 而端点实际只暴露 deepseek-flash / deepseek-v4-pro）。
    catalog: Dict[str, Any] = {}
    for name, (base, _key) in providers.items():
        info = listing.get(name) or {}
        catalog[name] = {"base_url": base, "count": info.get("count") or 0,
                         "ids": info.get("ids") or [],
                         "error": None if info.get("ok") else (info.get("error") or info.get("status"))}
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.list:
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return

    # ── 逐项探活 ──
    lines.append("## 探活结果")
    lines.append("")
    lines.append("| 项目 | 结果 | 模型/端点 | 指标 | 延迟 | 备注 |")
    lines.append("|---|---|---|---|---|---|")
    await probe_embedding(lines)
    await probe_rerank(lines)
    await probe_llm(lines)
    lines.append("")

    lines.append("## 成本")
    lines.append("")
    snap = spend_ledger.snapshot()
    lines.append(f"- 本轮累计花费：¥{snap['spent_yuan']}")
    lines.append(f"- 剩余额度：¥{snap['remaining_yuan']}")
    lines.append(f"- 被护栏拒绝次数：{snap['denied_calls']}")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps({"listing": listing, "budget": snap,
                             "embedding": __import__("app.embedding", fromlist=["x"])
                             .embedding_client.stats},
                            ensure_ascii=False, indent=1)[:4000])
    lines.append("```")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"结果已写入 {OUT}")
    print(f"本轮花费 ¥{snap['spent_yuan']}（上限 ¥{snap['cap_yuan']}）")


if __name__ == "__main__":
    asyncio.run(main())
