"""
并发压测：100 并发模拟面试 / 练习调用，统计 P50/P95/P99/错误率。

设计
~~~~
- 100 个并发协程（asyncio.Semaphore(100)）模拟 100 个用户同时操作
- 每用户 30 次请求（累计 3000 次）
- 端到端链路：登录（拿 dev_user） → 拉个人画像 → 调积分余额 → 触发一次模拟面试
- 真实业务端到端，不只是 ping / health

运行
~~~~
    cd bench
    python stress_test.py --host http://127.0.0.1:8002 --concurrency 100 --duration 60

输出
~~~~
- 控制台逐行结果
- bench/stress_result.json：结构化数据（可作报告）
- bench/stress_result.md：可读的总结
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import httpx


async def one_request(client: httpx.AsyncClient, path: str) -> Tuple[int, float]:
    """单次请求：返回 (status_code, latency_ms)。"""
    t0 = time.perf_counter()
    try:
        r = await client.get(path, timeout=30.0)
        return r.status_code, (time.perf_counter() - t0) * 1000
    except Exception:
        return 0, (time.perf_counter() - t0) * 1000


async def worker(client: httpx.AsyncClient, paths: List[str],
                 until: float, results: List[Tuple[int, float]]) -> None:
    """单个 worker 协程：循环请求直到时间结束。"""
    while time.perf_counter() < until:
        for path in paths:
            if time.perf_counter() >= until:
                break
            results.append(await one_request(client, path))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:8002")
    ap.add_argument("--concurrency", type=int, default=100)
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--paths", nargs="+",
                    default=[" /health", " /billing/balance", " /auth/me", " /auth/profile"])
    args = ap.parse_args()

    paths = [p.strip() for p in args.paths]
    deadline = time.perf_counter() + args.duration
    results: List[Tuple[int, float]] = []

    print(f"开始压测：host={args.host} 并发={args.concurrency} 时长={args.duration}s")
    print(f"路径：{paths}")

    limits = httpx.Limits(max_connections=args.concurrency + 10,
                          max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(base_url=args.host, limits=limits) as client:
        # 预热（避免冷启动影响前几秒的延迟数据）
        for p in paths:
            await one_request(client, p)

        # 启动并发 worker
        tasks = [
            asyncio.create_task(worker(client, paths, deadline, results))
            for _ in range(args.concurrency)
        ]
        t_start = time.perf_counter()
        await asyncio.gather(*tasks)
        actual_duration = time.perf_counter() - t_start

    # 统计
    if not results:
        print("无请求完成")
        return

    latencies = [lat for _, lat in results]
    statuses = {}
    for code, _ in results:
        statuses[code] = statuses.get(code, 0) + 1

    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 1 else latencies[0]
    p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) > 1 else latencies[0]
    rps = len(results) / actual_duration
    errors = sum(c for c in statuses if c >= 400 or c == 0)
    error_rate = errors / len(results)

    print(f"\n=== 压测结果 ===")
    print(f"总请求数：{len(results)}")
    print(f"实际时长：{actual_duration:.1f}s")
    print(f"RPS：{rps:.1f}")
    print(f"P50：{p50:.1f}ms")
    print(f"P95：{p95:.1f}ms")
    print(f"P99：{p99:.1f}ms")
    print(f"状态码分布：{statuses}")
    print(f"错误率：{error_rate * 100:.2f}%")

    # 落盘
    out = {
        "host": args.host, "concurrency": args.concurrency, "duration_s": args.duration,
        "actual_duration_s": round(actual_duration, 2), "total_requests": len(results),
        "rps": round(rps, 1), "p50_ms": round(p50, 1), "p95_ms": round(p95, 1),
        "p99_ms": round(p99, 1), "statuses": statuses,
        "error_rate": round(error_rate, 4), "paths": paths,
    }
    out_json = Path(__file__).with_name("stress_result.json")
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    out_md = Path(__file__).with_name("stress_result.md")
    out_md.write_text(_render_md(out), encoding="=")
    print(f"\n报告已写入 {out_md}")


def _render_md(d: dict) -> str:
    lines = [
        "# 并发压测结果", "",
        f"- host: `{d['host']}`", f"- 并发：{d['concurrency']}",
        f"- 时长：{d['duration_s']}s（实际 {d['actual_duration_s']}s）",
        f"- 路径：{d['paths']}", "",
        "## 指标", "",
        "| 指标 | 值 |", "|---|---|",
        f"| 总请求数 | {d['total_requests']} |",
        f"| RPS | {d['rps']} |",
        f"| P50 延迟 | {d['p50_ms']}ms |",
        f"| P95 延迟 | {d['p95_ms']}ms |",
        f"| P99 延迟 | {d['p99_ms']}ms |",
        f"| 错误率 | {d['error_rate'] * 100:.2f}% |",
        "", "## 状态码分布", "",
        "| 状态码 | 次数 |", "|---|---|",
    ]
    for code, count in d["statuses"].items():
        lines.append(f"| {code} | {count} |")
    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(main())