"""
模型可用性 + 流式行为探测。

回答两个必须用实测而非文档回答的问题：

1. **端点列出 ≠ 账号可用**
   阿里云聚合端点 /models 返回 249 个 id，但实际只有部分对本账号开通，
   未开通的会返回 400 "The product is not activated"。
   静态白名单会导致路由把请求打到必然失败的模型上 → 降级链在起跑线就断了。

2. **思考模式模型在流式下的输出形态**
   DeepSeek V4 系列默认启用思考模式。若只读 delta.content 而忽略
   delta.reasoning_content，会出现「流式一个字都不返回」——
   接口 200、无异常、静默空回答，是最难发现的一类线上故障。

运行：
    python bench/probe_models.py                 # 探测默认候选集
    python bench/probe_models.py --models a,b,c  # 指定候选
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

OUT = Path(__file__).with_name("model_availability.md")
JSON_OUT = Path(__file__).with_name("model_availability.json")

# 候选集：覆盖三家端点上的主力文本模型（阿里云上同时试「带厂商前缀」与「裸名」两种写法）
ALIYUN_CANDIDATES = [
    "deepseek-v4-flash", "deepseek-v4-pro",            # 裸名（聚合端点自有部署）
    "vanchin/deepseek-v4-pro", "vanchin/deepseek-v3.2-think",
    "qwen3.8-flash", "qwen3.8-max", "qwen3.8-max-0902", "qwen3.8-27b",
    "qwen3.7-plus", "qwen3.7-flash", "qwen3.7-max",
    "kimi-k3", "kimi-k2.6",
    "ZHIPU/GLM-5.3", "ZHIPU/GLM-5.3-Flash", "glm-5.2", "glm-5",
    "MiniMax/MiniMax-M3", "stepfun/step-3.7-flash",
]
DEEPSEEK_CANDIDATES = ["deepseek-flash", "deepseek-v4-pro"]
SILICONFLOW_CANDIDATES = [
    "deepseek-ai/DeepSeek-V4-Flash", "deepseek-ai/DeepSeek-V4-Pro",
    "Qwen/Qwen3.8-27B", "zai-org/GLM-5.3",
]


async def probe_one(client: Any, model: str) -> Dict[str, Any]:
    """最小代价探活：1 次调用，max_tokens=16，禁用思考。"""
    t0 = time.perf_counter()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "只回复两个字：正常"}],
            temperature=0.0,
            max_tokens=16,
            extra_body={"thinking": {"type": "disabled"}},
        )
        dt = round((time.perf_counter() - t0) * 1000, 1)
        msg = resp.choices[0].message
        text = (getattr(msg, "content", "") or "").strip()
        reason = (getattr(msg, "reasoning_content", "") or "")
        return {"model": model, "ok": bool(text), "latency_ms": dt,
                "reply": text[:40], "reasoning_chars": len(reason),
                "usage": (resp.usage.model_dump() if getattr(resp, "usage", None) else {})}
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        # 400「未开通」与「模型不存在」是两类不同问题，报告里要区分
        if "not activated" in msg:
            kind = "not_activated"
        elif "does not exist" in msg or "not found" in msg or "404" in msg:
            kind = "not_found"
        elif "401" in msg or "authentication" in msg.lower():
            kind = "auth"
        else:
            kind = "error"
        return {"model": model, "ok": False, "kind": kind,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "error": msg[:220]}


async def probe_stream_behavior(client: Any, model: str) -> Dict[str, Any]:
    """流式行为：分别统计 delta.content / delta.reasoning_content 的产出。

    这是「流式静默空回答」的判定实验：若 content=0 而 reasoning>0，
    说明模型在思考模式下把输出预算全用在了推理上。
    """
    out = {"model": model, "content_chars": 0, "reasoning_chars": 0,
           "ttft_content_ms": None, "ttft_any_ms": None, "total_ms": 0.0,
           "content_preview": "", "thinking_disabled": {}, "thinking_default": {}}

    async def run(disable_thinking: bool, max_tokens: int) -> Dict[str, Any]:
        kw: Dict[str, Any] = {}
        if disable_thinking:
            kw["extra_body"] = {"thinking": {"type": "disabled"}}
        t0 = time.perf_counter()
        c_chars = r_chars = 0
        ttft_c = ttft_a = None
        preview = ""
        async for chunk in await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "用一句话解释什么是 RAG。"}],
                temperature=0.0, max_tokens=max_tokens, stream=True,
                stream_options={"include_usage": True}, **kw):
            ch = chunk.choices[0] if chunk.choices else None
            if ch is None:
                continue
            d = getattr(ch, "delta", None)
            if d is None:
                continue
            c = getattr(d, "content", None) or ""
            r = getattr(d, "reasoning_content", None) or ""
            if (c or r) and ttft_a is None:
                ttft_a = round((time.perf_counter() - t0) * 1000, 1)
            if c:
                if ttft_c is None:
                    ttft_c = round((time.perf_counter() - t0) * 1000, 1)
                c_chars += len(c)
                preview += c
            r_chars += len(r)
        return {"content_chars": c_chars, "reasoning_chars": r_chars,
                "ttft_content_ms": ttft_c, "ttft_any_ms": ttft_a,
                "total_ms": round((time.perf_counter() - t0) * 1000, 1),
                "content_preview": preview[:60]}

    try:
        a = await run(True, 256)      # 关闭思考
        b = await run(False, 64)      # 默认（思考开启）+ 小预算
        c = await run(False, 768)     # 默认（思考开启）+ 充足预算
        out.update({"thinking_disabled": a, "thinking_default": b,
                    "thinking_default_large": c})
        out["content_chars"] = a["content_chars"]
        out["content_preview"] = a["content_preview"]
        out["ttft_content_ms"] = a["ttft_content_ms"]
        out["total_ms"] = a["total_ms"]
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="", help="逗号分隔，覆盖默认候选集")
    args = ap.parse_args()

    from openai import AsyncOpenAI

    from app.config import settings
    from app.observability import init_budget, spend_ledger

    init_budget()

    endpoints = [
        ("deepseek", settings.provider_base_url("deepseek", "https://api.deepseek.com/v1"),
         settings.provider_key("deepseek"), DEEPSEEK_CANDIDATES),
        ("aliyun", settings.provider_base_url("aliyun", ""),
         settings.provider_key("aliyun"),
         [m.strip() for m in args.models.split(",")] if args.models else ALIYUN_CANDIDATES),
        ("siliconflow", "https://api.siliconflow.cn/v1",
         settings.provider_key("siliconflow"), SILICONFLOW_CANDIDATES),
    ]

    results: Dict[str, List[Dict[str, Any]]] = {}
    lines: List[str] = ["# 模型可用性探测（真实调用）", "",
                        f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", ""]

    for name, base, key, cands in endpoints:
        if not key or not base or not cands:
            continue
        client = AsyncOpenAI(api_key=key, base_url=base, timeout=40, max_retries=0)
        got: List[Dict[str, Any]] = []
        lines.append(f"## {name} `{base}`")
        lines.append("")
        lines.append("| 模型 | 可用 | 延迟 | 回复 | 判定 |")
        lines.append("|---|---|---|---|---|")
        for m in cands:
            r = await probe_one(client, m)
            got.append(r)
            mark = "✅" if r.get("ok") else "❌"
            note = "-" if r.get("ok") else (r.get("kind") or r.get("error", "")[:60])
            lines.append(f"| `{m}` | {mark} | {r['latency_ms']} ms | "
                         f"{r.get('reply', '')} | {note} |")
        lines.append("")
        results[name] = got

    # ── 流式行为实验 ──
    lines.append("## 流式输出形态实验（思考模式的影响）")
    lines.append("")
    ds_base = settings.provider_base_url("deepseek", "https://api.deepseek.com/v1")
    ds = AsyncOpenAI(api_key=settings.provider_key("deepseek"), base_url=ds_base,
                     timeout=60, max_retries=0)
    stream_res: List[Dict[str, Any]] = []
    for m in ("deepseek-flash", "deepseek-v4-pro"):
        r = await probe_stream_behavior(ds, m)
        stream_res.append(r)
        lines.append(f"### {m}")
        lines.append("")
        for label, keyname in (("关闭思考 + 256 token", "thinking_disabled"),
                               ("默认(思考开启) + 64 token", "thinking_default"),
                               ("默认(思考开启) + 768 token", "thinking_default_large")):
            v = r.get(keyname) or {}
            lines.append(f"- {label}：正文 {v.get('content_chars')} 字 / "
                         f"思维链 {v.get('reasoning_chars')} 字 / "
                         f"正文首字 {v.get('ttft_content_ms')} ms / "
                         f"总 {v.get('total_ms')} ms"
                         + (f" / 预览「{v.get('content_preview')}」" if v.get("content_preview") else ""))
        lines.append("")
    lines.append("")
    lines.append(f"**本轮花费 ¥{spend_ledger.total:.5f}**（上限 ¥{spend_ledger.cap_yuan}）")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    JSON_OUT.write_text(json.dumps({"availability": results, "stream": stream_res,
                                    "spent_yuan": spend_ledger.total},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {OUT}")
    print(f"spent: ¥{spend_ledger.total:.5f}")


if __name__ == "__main__":
    asyncio.run(main())
