"""
检索层规模化性能基准（Benchmark Probe）

用途：量化当前实现在不同语料规模下的检索/索引开销，作为优化前后的对照基线。
用法：python bench/retrieval_bench.py   → 结果写入 bench/result.md

被测的真实代码路径：
  A. app/rag/vector_store.py:45-78    全表 select + Python 逐条 cosine_similarity
  B. app/embedding.py:96-112          struct.unpack BLOB（float64）+ 纯 Python 余弦
  C. app/services/kb_service.py:138   _append_bm25：入库时全量重建 BM25（jieba + BM25Okapi）

依赖：numpy, rank-bm25, jieba
"""
from __future__ import annotations

import gc
import os
import struct
import time
from pathlib import Path
from typing import Callable, Dict, List

import numpy as np

DIM = 1024  # bge-m3 输出维度
KB_SEED = Path(__file__).resolve().parents[1] / "backend" / "data" / "kb_seed"
OUT = Path(__file__).with_name("result.md")
RESULTS: List[str] = []


def log(line: str = "") -> None:
    RESULTS.append(line)
    print(line)


def timed(fn: Callable[[], object], repeat: int = 1) -> float:
    best = float("inf")
    for _ in range(repeat):
        gc.collect()
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def fmt(sec: float) -> str:
    if sec < 1e-3:
        return f"{sec * 1e6:.0f}us"
    if sec < 1:
        return f"{sec * 1e3:.1f}ms"
    return f"{sec:.2f}s"


# ── 复刻当前实现 ─────────────────────────────────────────────────────

def pack_f64(vec) -> bytes:
    return struct.pack(f">{len(vec)}d", *vec)


def unpack_f64(blob: bytes):
    n = len(blob) // 8
    return list(struct.unpack(f">{n}d", blob))


def cosine_sim_pyloop(a, b) -> float:
    """复刻 app/embedding.py:107-112（注意 min(len) 静默截断）。"""
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = sum(v * v for v in a[:n]) ** 0.5 or 1.0
    nb = sum(v * v for v in b[:n]) ** 0.5 or 1.0
    return dot / (na * nb)


def bench_blob_unpack(n: int) -> float:
    rng = np.random.default_rng(0)
    blobs = [pack_f64(rng.random(DIM)) for _ in range(n)]
    t = timed(lambda: [unpack_f64(b) for b in blobs])
    del blobs
    return t


def bench_pyloop(n: int) -> float:
    rng = np.random.default_rng(0)
    q = rng.random(DIM)
    vecs = [rng.random(DIM).tolist() for _ in range(n)]
    t = timed(lambda: [cosine_sim_pyloop(q, v) for v in vecs])
    del vecs
    return t


def bench_numpy(n: int) -> float:
    """优化方案：float32 矩阵向量化 + argpartition 取 top-k。"""
    rng = np.random.default_rng(0)
    q = rng.random(DIM).astype(np.float32)
    mat = rng.random((n, DIM), dtype=np.float32)
    nq = float(np.linalg.norm(q))

    def run():
        sims = mat @ q / (np.linalg.norm(mat, axis=1) * nq + 1e-9)
        np.argpartition(sims, -5)[-5:]

    t = timed(run, repeat=3)
    del mat
    return t


def bench_faiss(n: int) -> float:
    """优化方案：HNSW ANN 索引（若已安装 faiss）。"""
    import faiss

    rng = np.random.default_rng(0)
    mat = rng.random((n, DIM), dtype=np.float32)
    index = faiss.IndexHNSWFlat(DIM, 32)
    index.hnsw.efConstruction = 200
    index.add(mat)
    index.hnsw.efSearch = 64
    q = rng.random((1, DIM), dtype=np.float32)

    def run():
        index.search(q, 5)

    t = timed(run, repeat=5)
    del mat, index
    return t


def kb_stats() -> None:
    log("## 0 知识库现状实测")
    log()
    if not KB_SEED.exists():
        log(f"- 目录不存在: {KB_SEED}")
        return
    files = sorted(KB_SEED.glob("*.md"))
    per_doc = [(f.name, len(f.read_text(encoding="utf-8", errors="ignore"))) for f in files]
    per_doc.sort(key=lambda x: -x[1])
    total_chars = sum(c for _, c in per_doc)
    # 复刻 loader.split_text：chunk_size=800 / overlap=100 → 步进 700
    est_chunks = sum(max(1, -(-(c - 800) // 700)) if c > 800 else 1 for _, c in per_doc)
    log(f"- 文档数: **{len(files)}** 篇")
    log(f"- 总字符: **{total_chars:,}**（平均 {total_chars // max(len(files), 1):,} 字符/篇）")
    log(f"- 按 chunk_size=800/overlap=100 估算: **约 {est_chunks:,} 个 chunk**")
    if per_doc:
        log(f"- 最大单篇: {per_doc[0][0]}（{per_doc[0][1]:,} 字符）")
    log()
    ratio = 10_000 / max(len(files), 1)
    log("同比例外推到 10000 篇：")
    log(f"- 总字符 约 {int(total_chars * ratio):,}")
    log(f"- chunk 数 约 {int(est_chunks * ratio):,}")
    log(f"- 向量存储 float64 约 {est_chunks * ratio * DIM * 8 / 1024**3:.1f} GB"
        f"（float32 约 {est_chunks * ratio * DIM * 4 / 1024**3:.1f} GB）")
    log()


def main() -> None:
    log("# 检索层规模化性能基准")
    log()
    log(f"环境: Python {os.sys.version.split()[0]}, numpy {np.__version__}, "
        f"维度 {DIM}, 逻辑核 {os.cpu_count()}")
    log()

    kb_stats()

    log("## 1 BLOB 反序列化（每次查询固定开销）")
    log()
    log("| chunk 数 | float64 BLOB 全量 unpack | 单条均摊 |")
    log("|---|---|---|")
    for n in (1_000, 10_000, 20_000):
        t = bench_blob_unpack(n)
        log(f"| {n:,} | {fmt(t)} | {fmt(t / n)} |")
    log()

    log("## 2 纯 Python 余弦扫描（当前实现）")
    log()
    log("| chunk 数 | 扫描耗时 | 单条均摊 |")
    log("|---|---|---|")
    pyloop: Dict[int, float] = {}
    for n in (500, 2_000, 8_000):
        t = bench_pyloop(n)
        pyloop[n] = t
        log(f"| {n:,} | {fmt(t)} | {fmt(t / n)} |")
    per_vec = pyloop[8_000] / 8_000
    log()
    log(f"单条约 {per_vec * 1e6:.1f}us，线性外推：")
    log()
    log("| 外推 chunk 数 | 纯 Python 扫描（推算） |")
    log("|---|---|")
    for n in (20_000, 100_000, 200_000):
        log(f"| {n:,} | {fmt(per_vec * n)} |")
    log()

    log("## 3 优化方案对比")
    log()
    log("| chunk 数 | 向量化 float32 | 相比纯 Python 加速 | HNSW ANN | 相比纯 Python 加速 |")
    log("|---|---|---|---|---|")
    for n in (1_000, 10_000, 50_000, 100_000):
        t_np = bench_numpy(n)
        base = per_vec * n
        try:
            t_ann = bench_faiss(n)
            ann_cell, ann_speed = fmt(t_ann), f"{base / t_ann:.0f}x"
        except Exception:  # noqa: BLE001
            ann_cell, ann_speed = "n/a", "n/a"
        log(f"| {n:,} | {fmt(t_np)} | {base / t_np:.0f}x | {ann_cell} | {ann_speed} |")
    log()

    log("## 4 BM25 全量重建（kb_service._append_bm25，同步阻塞事件循环）")
    log()
    try:
        import jieba
        from rank_bm25 import BM25Okapi

        _ = jieba.lcut("预热词典")
        chunk_text = "混合检索通过向量与 BM25 双路召回，再以 RRF 融合排序后交给大模型生成。" * 10

        log("| 语料 chunk 数 | jieba 分词 | BM25Okapi 建模 | 合计阻塞 |")
        log("|---|---|---|---|")
        measured: Dict[int, float] = {}
        for n in (1_000, 5_000):
            corpus = [chunk_text] * n
            t_tok = timed(lambda: [jieba.lcut(t) for t in corpus])
            tokens = [jieba.lcut(t) for t in corpus]
            t_bm = timed(lambda: BM25Okapi(tokens))
            measured[n] = t_tok + t_bm
            log(f"| {n:,} | {fmt(t_tok)} | {fmt(t_bm)} | {fmt(t_tok + t_bm)} |")
            del corpus, tokens
        unit = measured[5_000] / 5_000
        log()
        log(f"单 chunk 约 {unit * 1e3:.2f}ms，线性外推：")
        log()
        for n in (20_000, 100_000, 200_000):
            log(f"- {n:,} chunks：**{fmt(unit * n)}** / 次入库")
    except Exception as e:  # noqa: BLE001
        log(f"跳过（依赖缺失: {e}）")
    log()

    log("## 5 SQLite 全表拉取（与业务同库存储）")
    log()
    try:
        import sqlite3
        import tempfile

        for n in (5_000, 20_000):
            path = os.path.join(tempfile.gettempdir(), f"vecbench_{n}.db")
            if os.path.exists(path):
                os.remove(path)
            con = sqlite3.connect(path)
            con.execute("CREATE TABLE vectors (id INTEGER PRIMARY KEY, content TEXT, embedding BLOB)")
            rng = np.random.default_rng(1)
            payload = [("x" * 400, pack_f64(rng.random(DIM))) for _ in range(n)]
            con.executemany("INSERT INTO vectors (content, embedding) VALUES (?, ?)", payload)
            con.commit()
            t_fetch = timed(lambda: con.execute("SELECT * FROM vectors").fetchall())
            size_mb = os.path.getsize(path) / 1024 / 1024
            con.close()
            os.remove(path)
            log(f"- {n:,} 行（库文件 {size_mb:.1f} MB）: 全表 fetchall = {fmt(t_fetch)}")
    except Exception as e:  # noqa: BLE001
        log(f"- 跳过（{e}）")

    OUT.write_text("\n".join(RESULTS) + "\n", encoding="utf-8")
    print(f"\n结果已写入 {OUT}")


if __name__ == "__main__":
    main()
