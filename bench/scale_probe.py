"""
规模化检索探针：用真实代码路径测量 vector_store.search 在不同语料规模下的延迟分布。

架构：driver 进程按规模逐个 spawn worker 子进程（避免 SQLAlchemy engine / SQLite 文件句柄复用问题）。

用法:
  python bench/scale_probe.py --sizes 500,5000,20000 --queries 10
  python bench/scale_probe.py --worker --n 5000 --db <path> --queries 10   # 内部使用
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

DIM = 1024
DEFAULT_SIZES = "500,5000,20000"


# ── worker：在独立进程内完成「建库 → 灌数据 → 测真实 search」 ────────────
async def worker(n: int, db: Path, dim: int, queries: int) -> dict:
    import numpy as np

    from app.database import SessionLocal, engine, init_db
    from app.embedding import embedding_client, pack_vector
    from app.models import Vector
    from app.rag.vector_store import vector_store

    await init_db()

    rng = np.random.default_rng(42)
    t0 = time.perf_counter()
    async with SessionLocal() as session:
        for i in range(n):
            session.add(Vector(
                doc_id=f"doc:{(i // 10) + 1}",
                chunk_index=i % 10,
                chunk_count=10,
                content=f"chunk-{i} 混合检索 RRF 融合 BM25 向量召回" * 5,
                embedding=pack_vector(rng.random(dim).tolist()),
                metadata_json=json.dumps({"doc_title": f"doc{(i // 10) + 1}",
                                          "category": "RAG", "status": "approved"}),
            ))
            if (i + 1) % 2000 == 0:
                await session.commit()
        await session.commit()
    write_s = time.perf_counter() - t0

    qvecs = np.random.default_rng(7).random((queries, dim))
    counter = {"i": 0}

    async def fake_embed(_text: str):
        v = qvecs[counter["i"] % queries].tolist()
        counter["i"] += 1
        return v

    embedding_client.embed = fake_embed  # type: ignore[assignment]

    await vector_store.search("warmup", top_k=5)  # 预热

    lat = []
    for _ in range(queries):
        t = time.perf_counter()
        await vector_store.search("混合检索如何做 RRF 融合", top_k=5)
        lat.append((time.perf_counter() - t) * 1000)
    lat.sort()

    await engine.dispose()

    return {
        "n": n,
        "p50_ms": round(statistics.median(lat), 1),
        "p95_ms": round(lat[max(0, int(len(lat) * 0.95) - 1)], 1),
        "min_ms": round(lat[0], 1),
        "max_ms": round(lat[-1], 1),
        "write_s": round(write_s, 1),
    }


def _driver(sizes: list[int], queries: int, dim: int, out: Path) -> None:
    rows: list[dict] = []
    tmp_root = Path(tempfile.mkdtemp(prefix="ragprobe_"))

    for n in sizes:
        db = tmp_root / f"probe_{n}.db"
        proc = subprocess.run(
            [sys.executable, str(Path(__file__)), "--worker",
             "--n", str(n), "--db", str(db), "--queries", str(queries), "--dim", str(dim)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        marker = [ln for ln in (proc.stdout or "").splitlines() if ln.startswith("__RESULT__")]
        if not marker:
            print(f"N={n} 失败: exit={proc.returncode}\n{(proc.stderr or '')[-800:]}")
            continue
        stat = json.loads(marker[0][len("__RESULT__"):])
        rows.append(stat)
        print(f"N={stat['n']:>7,}  p50={stat['p50_ms']:>9.1f}ms  p95={stat['p95_ms']:>9.1f}ms"
              f"  (灌数据 {stat['write_s']}s)")

    lines = [
        "# 规模化检索延迟实测（真实 VectorStore.search 路径）",
        "",
        f"命令: `python bench/scale_probe.py --sizes {','.join(str(s) for s in sizes)}"
        f" --queries {queries} --dim {dim}`",
        "",
        f"环境: Python {sys.version.split()[0]}, 向量维度 {dim}, 逻辑核 {os.cpu_count()}",
        "",
        "| chunk 数 | P50 | P95 | 最小 | 最大 | 灌数据耗时 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['n']:,} | {r['p50_ms']:.1f}ms | {r['p95_ms']:.1f}ms | "
                     f"{r['min_ms']:.1f}ms | {r['max_ms']:.1f}ms | {r['write_s']}s |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n结果已写入 {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default=DEFAULT_SIZES)
    ap.add_argument("--queries", type=int, default=10)
    ap.add_argument("--dim", type=int, default=DIM)
    ap.add_argument("--out", default="")
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--db", default="")
    args = ap.parse_args()

    if args.worker:
        stat = asyncio.run(worker(args.n, Path(args.db), args.dim, args.queries))
        print("__RESULT__" + json.dumps(stat))
        return

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    out = Path(args.out) if args.out else Path(__file__).with_name("scale_result.md")
    _driver(sizes, args.queries, args.dim, out)


if __name__ == "__main__":
    main()
