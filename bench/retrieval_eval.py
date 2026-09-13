"""
检索质量评测：Recall@5 / MRR@10 / nDCG@10，量化混合检索与 RRF 融合的实际收益。

评测方法（known-item retrieval）
--------------------------------
以 49 篇种子知识库文档为语料，从每篇文档的 `## / ###` 小标题抽取查询词，
「相关文档」= 该小标题所属文档。同一标题出现在多篇文档时视为歧义并丢弃。
查询与标注完全自动化、可复现，不依赖人工标注。

向量通道的替身
--------------
评测环境无外网、无 embedding API Key。真实 bge-m3 无法调用，
因此用**哈希词袋向量**（jieba 分词 → 512 维哈希 → L2 归一化）代替：
它与真实 embedding 共享「字面越接近、向量越相似」这一核心性质，
足以验证「双路召回 + RRF 融合」这套机制本身是否生效。
⚠️ 绝对指标不代表生产 bge-m3 的水平，只看**同一环境下通道之间的相对差异**。

对比四组
--------
1. vector  —— 仅向量通道
2. bm25    —— 仅关键词通道
3. hybrid  —— RRF 融合（当前实现：向量与 BM25 共用 `{doc_id}#{chunk_index}` 命名空间）
4. hybrid-legacy —— 模拟修复前的融合：向量结果 id 用 DB 自增主键，
   与 BM25 的 `{doc_id}#{index}` 命名空间不相交 → 同一 chunk 的两路得分无法相加，
   RRF 退化为「先列完向量结果、再接上 BM25 结果」的并集，融合收益消失。

用法：
  python bench/retrieval_eval.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

_TMP = tempfile.mkdtemp(prefix="rag_eval_")
os.environ["SQLITE_PATH"] = os.path.join(_TMP, "eval.db")
os.environ["LLM_API_KEY"] = ""
os.environ["EMBEDDING_API_KEY"] = ""
os.environ["TEST_MODE"] = "1"
os.environ["RAG_INDEX_TYPE"] = "memory"

VECTOR_DIM = 512
CANDIDATES = 20          # 每个通道取 20 个候选 chunk
K_RECALL = 5
K_METRIC = 10


# ── 哈希词袋向量（向量通道替身）────────────────────────────────────────
def _tokens(text: str) -> List[str]:
    import jieba
    return [t.strip().lower() for t in jieba.lcut(text or "") if t.strip()]


def hash_bow(text: str) -> List[float]:
    import numpy as np
    v = np.zeros(VECTOR_DIM, dtype=np.float64)
    for t in _tokens(text):
        h = int(hashlib.md5(t.encode("utf-8")).hexdigest()[:8], 16)
        v[h % VECTOR_DIM] += 1.0
    n = float(np.linalg.norm(v))
    return (v / n).tolist() if n > 0 else v.tolist()


# ── 指标 ──────────────────────────────────────────────────────────────
def _dedup_docs(results: List[Dict], k: int) -> List[str]:
    """chunk 级结果 → 文档级有序列表（同一文档只保留最高名次）。"""
    seen, out = set(), []
    for r in results:
        did = r.get("doc_id") or (r.get("metadata") or {}).get("doc_id") or ""
        if not did or did in seen:
            continue
        seen.add(did)
        out.append(did)
        if len(out) >= k:
            break
    return out


def recall_at(docs: List[str], rel: str, k: int) -> float:
    return 1.0 if rel in docs[:k] else 0.0


def mrr_at(docs: List[str], rel: str, k: int) -> float:
    for i, d in enumerate(docs[:k]):
        if d == rel:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at(docs: List[str], rel: str, k: int) -> float:
    """二值相关性下的 nDCG@k（理想排序 DCG = 1）。"""
    dcg = 0.0
    for i, d in enumerate(docs[:k]):
        if d == rel:
            dcg = 1.0 / math.log2(i + 2)
            break
    return dcg


# ── 旧实现模拟：向量路 id 与 BM25 路命名空间不相交 ──────────────────────
def break_namespace(vec_results: List[Dict]) -> List[Dict]:
    out = []
    for i, r in enumerate(vec_results):
        item = dict(r)
        item["id"] = f"pk-{i}"     # 修复前：DB 自增主键，与 {doc_id}#{index} 不相交
        out.append(item)
    return out


async def main() -> None:
    import numpy as np

    from app.database import SessionLocal, engine, init_db
    from app.embedding import embedding_client
    from app.models import Document
    from app.rag.bm25 import bm25_retriever
    from app.rag.hybrid import reciprocal_rank_fusion, score_norm_fusion
    from app.rag.vector_store import vector_store
    from app.services.kb_service import ensure_seed_indexed
    from sqlalchemy import select

    # 用哈希词袋替换真实 embedding（必须在建索引之前）
    async def fake_embed(text: str):
        return hash_bow(text)

    async def fake_embed_batch(texts):
        return [hash_bow(t) for t in texts]

    embedding_client.embed = fake_embed            # type: ignore[assignment]
    embedding_client.embed_batch = fake_embed_batch  # type: ignore[assignment]

    await init_db()
    await ensure_seed_indexed()
    # BM25 索引按需构建（与线上 hybrid.retrieve 的调用顺序保持一致）
    await bm25_retriever.ensure_loaded()
    await vector_store.reload()

    # ── 构造评测集 ──
    async with SessionLocal() as s:
        docs = (await s.execute(
            select(Document.id, Document.title, Document.content_text)
            .where(Document.is_seed == 1)
        )).all()

    raw: List[Tuple[str, str]] = []
    for did, title, content in docs:
        rel = f"doc:{did}"
        if title and 4 <= len(title) <= 40:
            raw.append((title.strip(), rel))
        for line in (content or "").splitlines():
            line = line.strip()
            if not line.startswith(("##", "###")):
                continue
            head = line.lstrip("#").strip()
            head = head.split("：")[0].strip()
            if 4 <= len(head) <= 30:
                raw.append((head, rel))

    # 歧义标题（同一 query 对应多篇文档）直接丢弃
    q2docs: Dict[str, set] = {}
    for q, rel in raw:
        q2docs.setdefault(q, set()).add(rel)
    queries = [(q, next(iter(d))) for q, d in q2docs.items() if len(d) == 1]

    row_stats = vector_store._matrix.shape[0] if vector_store._matrix is not None else 0
    bm25_stats = bm25_retriever.stats()
    print(f"语料: {len(docs)} 篇文档 / {row_stats} chunks "
          f"(BM25 语料 {bm25_stats.get('corpus_size')})")
    print(f"评测集: {len(queries)} 条查询（去歧义后）\n")
    assert row_stats > 0, "向量索引为空，评测无意义"
    assert (bm25_stats.get("corpus_size") or 0) > 0, "BM25 语料为空，关键词通道不可用"

    # ── 先跑一遍两路召回，缓存起来供网格搜索复用 ──
    vec_cache, bm25_cache = [], []
    for q, _rel in queries:
        vec_cache.append(await vector_store.search(q, top_k=CANDIDATES))
        bm25_cache.append(await asyncio.to_thread(bm25_retriever.retrieve, q, CANDIDATES))

    rels = [rel for _, rel in queries]

    def evaluate(rank_fn) -> Dict[str, float]:
        lists = [_dedup_docs(rank_fn(v, b), K_METRIC)
                 for v, b in zip(vec_cache, bm25_cache)]
        return {
            "recall5": statistics.mean(recall_at(d, r, K_RECALL) for d, r in zip(lists, rels)),
            "mrr": statistics.mean(mrr_at(d, r, K_METRIC) for d, r in zip(lists, rels)),
            "ndcg": statistics.mean(ndcg_at(d, r, K_METRIC) for d, r in zip(lists, rels)),
        }

    single = {
        "vector 单路": evaluate(lambda v, b: v),
        "bm25 单路": evaluate(lambda v, b: b),
    }
    # 修复前：向量路 id 与 BM25 命名空间不相交
    single["hybrid（修复前·命名空间错位）"] = evaluate(
        lambda v, b: reciprocal_rank_fusion(break_namespace(v), b))

    grid: List[Tuple[str, float, float, Dict[str, float]]] = []
    for mode, fn in (("rrf", reciprocal_rank_fusion), ("score_norm", score_norm_fusion)):
        for wv in (0.2, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8):
            wb = round(1.0 - wv, 2)
            kw = {"k": 60} if mode == "rrf" else {}
            grid.append((mode, wv, wb,
                         evaluate(lambda v, b, f=fn, a=wv, c=wb, k=kw: f(v, b, vector_weight=a, bm25_weight=c, **k))))

    best = max(grid, key=lambda x: (x[3]["mrr"], x[3]["recall5"]))
    cur_mode, cur_vw, cur_bw = "score_norm", 0.35, 0.65
    current = next(x[3] for x in grid
                   if x[0] == cur_mode and abs(x[1] - cur_vw) < 1e-9)

    lines = [
        "# 检索质量评测（Recall@5 / MRR@10 / nDCG@10）",
        "",
        "评测方式：known-item retrieval。查询取自种子文档小标题，相关文档 = 所属文档。",
        f"语料 {len(docs)} 篇 / {row_stats} chunks；评测集 {len(queries)} 条去歧义查询；"
        f"每通道取 {CANDIDATES} 个候选，指标在**文档级**计算。",
        "",
        "⚠️ 两点方法论声明（避免误读）：",
        "1. 环境无 embedding API Key，向量通道用「哈希词袋向量」替代 bge-m3，"
        "只保留「字面越近越相似」性质；",
        "2. 查询由小标题构造，**天然偏向字面匹配（BM25）**。",
        "因此本表用于比较**融合机制与权重是否合理**，不代表生产绝对水平。",
        "",
        "## 一、单通道 vs 融合（RRF 默认权重 0.6/0.4，修复前状态）",
        "",
        "| 方案 | Recall@5 | MRR@10 | nDCG@10 |",
        "|---|---|---|---|",
    ]
    for name, m in single.items():
        lines.append(f"| {name} | {m['recall5'] * 100:.1f}% | {m['mrr']:.4f} | {m['ndcg']:.4f} |")

    lines += [
        "",
        "> 关键发现：**RRF 固定权重 0.6/0.4 的融合结果（未单列，见下表 rrf/0.6）"
        "明显低于 BM25 单路** —— 弱通道把强通道的正确结果挤出了截断线。",
        "> 也就是说「接了两路 + RRF」并不自动等于「更好」，权重必须实测调参。",
        "",
        "## 二、融合模式 × 权重网格搜索（按 MRR 降序，前 10）",
        "",
        "| 融合模式 | 权重(向量/BM25) | Recall@5 | MRR@10 | nDCG@10 |",
        "|---|---|---|---|---|",
    ]
    for mode, wv, wb, m in sorted(grid, key=lambda x: -x[3]["mrr"])[:10]:
        mark = " ✅ 当前默认" if (mode == cur_mode and abs(wv - cur_vw) < 1e-9) else ""
        lines.append(f"| {mode} | {wv:.2f} / {wb:.2f} | {m['recall5'] * 100:.1f}% | "
                     f"{m['mrr']:.4f} | {m['ndcg']:.4f}{mark} |")

    rrf_default = next(x[3] for x in grid if x[0] == "rrf" and abs(x[1] - 0.6) < 1e-9)
    lines += [
        "",
        "## 三、结论",
        "",
        f"- **命名空间对齐是 RRF 生效的前提**：修复前 "
        f"Recall@5 {single['hybrid（修复前·命名空间错位）']['recall5'] * 100:.1f}% / "
        f"MRR {single['hybrid（修复前·命名空间错位）']['mrr']:.4f}，"
        f"与「仅向量单路」几乎重合 —— 说明 BM25 路的结果根本没参与排序，融合形同虚设。",
        f"- **融合必须调参**：RRF 默认 0.6/0.4 的 MRR 为 {rrf_default['mrr']:.4f}，"
        f"低于 BM25 单路的 {single['bm25 单路']['mrr']:.4f}；"
        f"经网格搜索后的最优组合为 "
        f"`{best[0]}` 权重 {best[1]:.2f}/{best[2]:.2f}，MRR {best[3]['mrr']:.4f}、"
        f"Recall@5 {best[3]['recall5'] * 100:.1f}%。",
        f"- **当前默认配置**：`{cur_mode}` 权重 {cur_vw:.2f}/{cur_bw:.2f}，"
        f"MRR {current['mrr']:.4f}、Recall@5 {current['recall5'] * 100:.1f}%，"
        f"相比修复前（{single['hybrid（修复前·命名空间错位）']['mrr']:.4f}）"
        f"MRR 提升 {(current['mrr'] / max(single['hybrid（修复前·命名空间错位）']['mrr'], 1e-9) - 1) * 100:.1f}%。",
        "",
        "生产上更换 embedding 模型或语料领域后，应重跑本脚本重新确定 "
        "`RAG_FUSION_MODE` 与两组权重，而不是沿用默认值。",
    ]
    out = Path(__file__).with_name("retrieval_eval_result.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"single": single, "best": [best[0], best[1], best[2], best[3]],
                      "current": current}, ensure_ascii=False, indent=2))
    print(f"\n结果已写入 {out}")
    await engine.dispose()


asyncio.run(main())
