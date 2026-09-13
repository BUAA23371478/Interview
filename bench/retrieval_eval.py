"""
检索质量评测 v2（真实 bge-m3 向量 + 真实 Cross-Encoder 精排）。

与 v1 的本质差别
----------------
v1 用「哈希词袋向量」替身（当时没有 embedding key），只能验证融合机制是否生效，
绝对数值没有意义。v2 用生产同款 bge-m3（1024 维）+ bge-reranker-v2-m3，
结论可以直接作为线上依据。

评测设计
--------
四个查询类型，覆盖从「字面重合」到「纯语义」的连续谱：

| 类型 | 构造方式 | 考察点 |
|---|---|---|
| title      | 文档标题 | 字面通道即可命中，作为上限参照 |
| section    | 文档小标题 | 中等难度 |
| paraphrase | LLM 改写提问（刻意避免与标题同词） | **纯语义通道能力** |
| scenario   | LLM 生成的真实面试场景问句 | 端到端实际使用形态 |

指标（文档级 known-item retrieval）：
  Recall@1/5、MRR@10、nDCG@10

指标口径必须是**文档级去重**：一篇文档有多个分块，若不去重，
「同一篇文档占满 top5」会被算成高召回，而实际上系统只找到了一篇文档。

对照方案：
  vector / bm25 / rrf / score_norm / score_norm+rerank / rrf+rerank
并对两种融合模式做权重网格搜索——用数据而不是直觉定权重。

成本：向量与检索结果全部走本地缓存（embed_cache.db / rerank_cache.db），
     首次运行后重复评测不再产生外部调用费用。

运行：
    python bench/retrieval_eval.py                  # 全量
    python bench/retrieval_eval.py --rebuild        # 强制重建向量索引
    python bench/retrieval_eval.py --regen-queries  # 重新生成 LLM 改写查询
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

OUT_MD = Path(__file__).with_name("retrieval_eval_result.md")
OUT_JSON = Path(__file__).with_name("retrieval_eval_raw.json")
QUERY_CACHE = Path(__file__).with_name("_queries_multi.json")

CANDIDATES = 20      # 每路召回候选数
K_RECALL = 5         # 主 Recall 指标
K_METRIC = 10        # MRR / nDCG 截断


# ══ 指标 ══════════════════════════════════════════════════════════════
def recall_at(ranked_docs: Sequence[str], gold: str, k: int) -> float:
    return 1.0 if gold in list(ranked_docs)[:k] else 0.0


def mrr_at(ranked_docs: Sequence[str], gold: str, k: int) -> float:
    for i, d in enumerate(list(ranked_docs)[:k]):
        if d == gold:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at(ranked_docs: Sequence[str], gold: str, k: int) -> float:
    for i, d in enumerate(list(ranked_docs)[:k]):
        if d == gold:
            return 1.0 / math.log2(i + 2)
    return 0.0


def dedup_docs(hits: Sequence[Dict[str, Any]], k: int) -> List[str]:
    """chunk 级结果 → 文档级去重序列（保留首次出现的名次）。"""
    seen: List[str] = []
    for h in hits:
        did = h.get("doc_id") or h.get("metadata", {}).get("doc_id", "")
        if did and did not in seen:
            seen.append(did)
        if len(seen) >= k:
            break
    return seen


# ══ 语料与索引 ════════════════════════════════════════════════════════
async def ensure_real_index(rebuild: bool) -> Dict[str, Any]:
    """确保向量索引由**真实 embedding** 构建（维度与当前模型一致）。"""
    from sqlalchemy import delete, func, select

    from app.database import SessionLocal, init_db
    from app.embedding import blob_dim, embedding_client
    from app.models import Vector
    from app.rag.bm25 import bm25_retriever
    from app.rag.vector_store import vector_store
    from app.services.kb_service import ensure_seed_indexed

    await init_db()
    probe = await embedding_client.probe()
    if not probe.get("ok"):
        raise SystemExit(f"Embedding 不可用，无法进行质量评测：{probe.get('error')}")
    dim = int(probe["dimension"])

    async with SessionLocal() as s:
        blob = (await s.execute(select(Vector.embedding).limit(1))).scalars().first()
    existing_dim = blob_dim(blob) if blob else 0
    if (rebuild or (existing_dim not in (0, dim))) and existing_dim:
        async with SessionLocal() as s:
            n = (await s.execute(select(func.count()).select_from(Vector))).scalar() or 0
            await s.execute(delete(Vector))
            await s.commit()
        print(f"索引维度 {existing_dim} 与模型维度 {dim} 不一致 → 清空 {n} 条向量重建")

    t0 = time.perf_counter()
    await ensure_seed_indexed()
    await bm25_retriever.ensure_loaded()
    await vector_store.reload()
    build_s = round(time.perf_counter() - t0, 2)

    return {"embedding_dim": dim, "embedding_model": probe.get("model"),
            "index": await vector_store.stats(), "bm25": bm25_retriever.stats(),
            "build_s": build_s}


async def load_docs() -> List[Dict[str, Any]]:
    """载入全部已收录文档（不限种子）。

    为什么不只评种子文档：真实语料是「种子 + 用户上传」的混合库，
    只评种子会严重高估检索效果——真实使用中要在一片大得多的语料里找对文档。
    """
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Document
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(Document.id, Document.title, Document.category, Document.content_text)
            .where(Document.status == "approved")
            .order_by(Document.id)
        )).all()
    return [{"doc_id": f"doc:{r[0]}", "title": r[1] or "", "category": r[2] or "",
             "content": r[3] or ""} for r in rows]


# ══ 查询集构建 ════════════════════════════════════════════════════════
def _headings(content: str, limit: int = 6) -> List[str]:
    out: List[str] = []
    for line in (content or "").splitlines():
        line = line.strip()
        if line.startswith("#"):
            head = line.lstrip("#").strip().split("：")[0].strip()
            if 3 <= len(head) <= 30:
                out.append(head)
        if len(out) >= limit:
            break
    return out


async def _llm_queries_for_doc(doc: Dict[str, Any], n: int = 3) -> List[Dict[str, str]]:
    """让 LLM 生成「语义型查询」：措辞刻意不与原标题/小标题重合。"""
    from app.llm import llm_client
    heads = _headings(doc["content"], 8)
    excerpt = (doc["content"] or "")[:1500]
    system = (
        "你是技术面试官。根据给定文档，生成用户可能提出的**检索式提问**。要求：\n"
        "1. 用自然语言口语化表达，**避免直接照抄文档标题或小标题的用词**；\n"
        "2. 每个提问独立可查询，能明确指向这篇文档的主题；\n"
        '3. 输出严格 JSON：{"queries": ["问题1", "问题2"]}\n'
    )
    user = (f"文档标题：{doc['title']}\n小标题：{'、'.join(heads)}\n"
            f"正文节选：\n{excerpt}\n\n请生成 {n} 个提问。")
    try:
        data = await llm_client.chat_with_json(system, user, temperature=0.6)
        qs = data.get("queries") or []
        return [{"q": str(q).strip(), "gold": doc["doc_id"], "type": "paraphrase"}
                for q in qs if 6 <= len(str(q).strip()) <= 60][:n]
    except Exception as e:  # noqa: BLE001
        print(f"  paraphrase 生成失败（{doc['title']}）: {type(e).__name__}: {e}")
        return []


async def _scenario_queries(docs: List[Dict[str, Any]], n: int = 12) -> List[Dict[str, str]]:
    """生成「面试场景型」查询：模拟真实出题时交给检索的 query 形态。"""
    from app.llm import llm_client
    titles = [f"{d['doc_id']}｜{d['title']}（{d['category']}）" for d in docs]
    system = (
        "你是面试官。下面是知识库的文档清单（id｜标题（分类））。"
        "请生成若干条「面试官考察某主题时会写下的检索关键词组合」，"
        "例如「向量召回与关键词召回怎么配合 权重怎么定 线上效果」。"
        '必须使用清单中真实存在的文档 id 作为 gold。输出严格 JSON：'
        '{"items": [{"q": "查询词", "gold": "doc:12"}]}\n'
    )
    user = "\n".join(titles[:60]) + f"\n\n请生成 {n} 条。"
    try:
        data = await llm_client.chat_with_json(system, user, temperature=0.6)
        items = data.get("items") or []
        valid = {d["doc_id"] for d in docs}
        return [{"q": str(it.get("q", "")).strip(), "gold": str(it.get("gold", "")),
                 "type": "scenario"}
                for it in items if str(it.get("gold", "")) in valid
                and 6 <= len(str(it.get("q", "")).strip()) <= 80]
    except Exception as e:  # noqa: BLE001
        print(f"  scenario 生成失败: {type(e).__name__}: {e}")
        return []


async def build_queries(docs: List[Dict[str, Any]], regen: bool) -> List[Dict[str, str]]:
    if QUERY_CACHE.exists() and not regen:
        cached = json.loads(QUERY_CACHE.read_text(encoding="utf-8"))
        # 空缓存（例如上一次因语料为 0 而生成失败）不能当有效缓存复用
        if cached:
            print(f"复用查询缓存 {QUERY_CACHE.name}（{len(cached)} 条）")
            return cached
    if not docs:
        raise SystemExit("语料为空，无法构建评测集：请先确认库中存在 approved 文档")

    from app.llm import llm_model_ctx
    out: List[Dict[str, str]] = []
    for d in docs:
        if 4 <= len(d["title"]) <= 40:
            out.append({"q": d["title"], "gold": d["doc_id"], "type": "title"})
        for h in _headings(d["content"], 3):
            out.append({"q": h, "gold": d["doc_id"], "type": "section"})

    token = llm_model_ctx.set("deepseek-flash")
    try:
        for i, d in enumerate(docs):
            out.extend(await _llm_queries_for_doc(d, 3))
            if (i + 1) % 10 == 0:
                print(f"  paraphrase 进度 {i + 1}/{len(docs)}")
        out.extend(await _scenario_queries(docs, 12))
    finally:
        llm_model_ctx.reset(token)

    by_q: Dict[str, set] = {}
    type_of: Dict[str, str] = {}
    for item in out:
        by_q.setdefault(item["q"], set()).add(item["gold"])
        type_of.setdefault(item["q"], item["type"])
    final = [{"q": q, "gold": next(iter(g)), "type": type_of[q]}
             for q, g in by_q.items() if len(g) == 1]
    QUERY_CACHE.write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已生成查询集并存缓存：{len(final)} 条")
    return final


# ══ 检索变体 ══════════════════════════════════════════════════════════
async def _raw_both(query: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    from app.rag.bm25 import bm25_retriever
    from app.rag.vector_store import vector_store
    await bm25_retriever.ensure_loaded()
    vec, bm = await asyncio.gather(
        vector_store.search(query, top_k=CANDIDATES),
        asyncio.to_thread(bm25_retriever.retrieve, query, CANDIDATES),
    )
    return vec, bm


async def run_variant(name: str, query: str) -> List[Dict[str, Any]]:
    from app.rag.hybrid import reciprocal_rank_fusion, score_norm_fusion
    from app.rag.rerank import rerank_client

    vec, bm = await _raw_both(query)
    if name == "vector":
        return vec
    if name == "bm25":
        return bm
    if name == "rrf":
        return reciprocal_rank_fusion(vec, bm)
    if name == "score_norm":
        return score_norm_fusion(vec, bm, vector_weight=0.35, bm25_weight=0.65)
    if name in ("score_norm+rerank", "rrf+rerank", "rerank_only"):
        if name == "rrf+rerank":
            base = reciprocal_rank_fusion(vec, bm)
        elif name == "rerank_only":
            base = vec + bm
        else:
            base = score_norm_fusion(vec, bm, vector_weight=0.35, bm25_weight=0.65)
        ranked, applied = await rerank_client.rerank(query, base, top_k=K_METRIC)
        if not applied and name != "rerank_only":
            print(f"  ⚠️ 精排未应用（{name}）")
        return ranked
    raise ValueError(name)


# ══ 主流程 ════════════════════════════════════════════════════════════
async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--regen-queries", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--docs", type=int, default=40,
                    help="抽样多少篇文档生成查询集（检索仍在全量语料上进行）")
    ap.add_argument("--rerank", type=int, default=1, help="1=启用精排（需 RERANK_API_KEY）")
    ap.add_argument("--queries-file", type=str, default="",
                    help="外部查询集 JSON（覆盖 LLM 自动生成）；含 q/gold/type/expected_doc_title")
    args = ap.parse_args()

    from app.config import settings
    from app.observability import init_budget, new_meter, spend_ledger

    settings.rerank_enabled = bool(args.rerank)
    init_budget()
    new_meter()

    info = await ensure_real_index(args.rebuild)
    docs_all = await load_docs()
    # 抽样只影响「生成哪些查询」；检索与评测仍在**全量语料**上进行，
    # 这样质量指标反映的是「在一整片语料里找对文档」的真实难度。
    import random as _random
    if args.docs and len(docs_all) > args.docs:
        docs = _random.Random(20260913).sample(docs_all, args.docs)
    else:
        docs = docs_all
    print(f"语料 {len(docs_all)} 篇 / {info['index'].get('loaded_chunks')} chunks / "
          f"{info['embedding_dim']} 维 / 索引 {info['index'].get('index_kind')} / "
          f"构建 {info['build_s']}s")
    print(f"查询集抽样文档 {len(docs)} 篇（检索语料仍为全量 {len(docs_all)} 篇）")

    queries = await build_queries(docs, args.regen_queries)
    # 若指定外部查询集，覆盖自动生成的；同时把 title-based gold 解析成 doc_id
    if args.queries_file:
        qf = Path(args.queries_file)
        if not qf.is_absolute():
            qf = Path(__file__).parent / qf
        raw = json.loads(qf.read_text(encoding="utf-8"))
        # 建立 title → doc_id 映射
        title_to_id = {d["title"]: d["doc_id"] for d in docs_all}
        resolved = []
        skipped = 0
        for it in raw:
            q = str(it.get("q", "")).strip()
            if not q:
                continue
            gold = str(it.get("gold", ""))
            expected_title = str(it.get("expected_doc_title", ""))
            # 优先按 title 解析
            if expected_title and expected_title in title_to_id:
                gold = title_to_id[expected_title]
            elif gold and gold in title_to_id.values():
                pass  # 已经是 doc:N
            elif gold and gold in title_to_id:
                gold = title_to_id[gold]
            else:
                skipped += 1
                continue
            resolved.append({"q": q, "gold": gold, "type": it.get("type", "title")})
        queries = resolved
        print(f"使用外部查询集 {qf.name}（原始 {len(raw)} 条 / 解析 {len(queries)} 条 / 跳过 {skipped}）")
    if args.limit:
        queries = queries[: args.limit]
    by_type: Dict[str, int] = {}
    for q in queries:
        by_type[q["type"]] = by_type.get(q["type"], 0) + 1
    print(f"评测集 {len(queries)} 条 → {by_type}")

    variants = ["vector", "bm25", "rrf", "score_norm"]
    if settings.rerank_enabled:
        variants += ["score_norm+rerank", "rrf+rerank"]

    per_variant: Dict[str, Dict[str, float]] = {}
    per_type: Dict[str, Dict[str, Dict[str, float]]] = {}
    raw: Dict[str, Any] = {"variants": {}}

    for v in variants:
        r1s: List[float] = []
        r5s: List[float] = []
        mrrs: List[float] = []
        ndcgs: List[float] = []
        type_acc: Dict[str, Dict[str, List[float]]] = {}
        for q in queries:
            hits = await run_variant(v, q["q"])
            ranked = dedup_docs(hits, K_METRIC)
            g = q["gold"]
            r5 = recall_at(ranked, g, K_RECALL)
            r1 = recall_at(ranked, g, 1)
            mr = mrr_at(ranked, g, K_METRIC)
            nd = ndcg_at(ranked, g, K_METRIC)
            r1s.append(r1); r5s.append(r5); mrrs.append(mr); ndcgs.append(nd)
            acc = type_acc.setdefault(q["type"], {"r5": [], "r1": [], "mrr": []})
            acc["r5"].append(r5); acc["r1"].append(r1); acc["mrr"].append(mr)
        per_variant[v] = {"recall1": statistics.mean(r1s),
                          "recall5": statistics.mean(r5s),
                          "mrr": statistics.mean(mrrs),
                          "ndcg": statistics.mean(ndcgs)}
        per_type[v] = {t: {"n": len(a["r5"]), "recall1": statistics.mean(a["r1"]),
                           "recall5": statistics.mean(a["r5"]),
                           "mrr": statistics.mean(a["mrr"])}
                       for t, a in type_acc.items()}
        m = per_variant[v]
        print(f"  {v:<20} R@1={m['recall1']:.3f} R@5={m['recall5']:.3f} "
              f"MRR={m['mrr']:.4f} nDCG={m['ndcg']:.4f}")
        raw["variants"][v] = m

    print("权重网格搜索中...")
    from app.rag.hybrid import reciprocal_rank_fusion, score_norm_fusion
    pairs: Dict[str, Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]] = {}
    for q in queries:
        pairs[q["q"]] = await _raw_both(q["q"])

    grid: List[Dict[str, Any]] = []
    for mode in ("score_norm", "rrf"):
        for vw in (0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0):
            bw = round(1.0 - vw, 2)
            r5s, mrrs = [], []
            for q in queries:
                vec, bm = pairs[q["q"]]
                fused = (score_norm_fusion(vec, bm, vector_weight=vw, bm25_weight=bw)
                         if mode == "score_norm"
                         else reciprocal_rank_fusion(vec, bm,
                                                     vector_weight=vw, bm25_weight=bw))
                ranked = dedup_docs(fused, K_METRIC)
                r5s.append(recall_at(ranked, q["gold"], K_RECALL))
                mrrs.append(mrr_at(ranked, q["gold"], K_METRIC))
            grid.append({"mode": mode, "vector_weight": vw, "bm25_weight": bw,
                         "recall5": round(statistics.mean(r5s), 4),
                         "mrr": round(statistics.mean(mrrs), 4)})
    grid.sort(key=lambda x: (x["recall5"], x["mrr"]), reverse=True)
    for g in grid[:6]:
        print(f"  {g['mode']:<11} vw={g['vector_weight']:<5} bw={g['bm25_weight']:<5} "
              f"R@5={g['recall5']:.3f} MRR={g['mrr']:.4f}")

    snap = spend_ledger.snapshot()
    lines: List[str] = [
        "# 检索质量评测 v2（真实 bge-m3 + 真实 Cross-Encoder 精排）", "",
        f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", "",
        "## 环境与语料", "",
        f"- Embedding：`{info['embedding_model']}`，{info['embedding_dim']} 维",
        f"- Rerank：`{settings.rerank_model}`（候选 {settings.rerank_candidates}，"
        f"本轮启用={settings.rerank_enabled}）",
        f"- 语料：{len(docs)} 篇文档 / {info['index'].get('loaded_chunks')} chunks / "
        f"索引类型 {info['index'].get('index_kind')}",
        f"- 评测集：{len(queries)} 条 → {by_type}",
        f"- 指标口径：**文档级去重**（同一文档多个分块只记一次名次），"
        f"每路取 {CANDIDATES} 个候选",
        "",
        "## 总体结果", "",
        "| 方案 | Recall@1 | Recall@5 | MRR@10 | nDCG@10 |", "|---|---|---|---|---|",
    ]
    for v in variants:
        m = per_variant[v]
        lines.append(f"| {v} | {m['recall1'] * 100:.1f}% | {m['recall5'] * 100:.1f}% | "
                     f"{m['mrr']:.4f} | {m['ndcg']:.4f} |")

    types = ["title", "section", "paraphrase", "scenario"]
    lines += ["", "## 分查询类型（Recall@5 / MRR）", "",
              "| 方案 | " + " | ".join(f"{t} R@5 / MRR" for t in types) + " |",
              "|---" * (len(types) + 1) + "|"]
    for v in variants:
        cells = []
        for t in types:
            d = per_type[v].get(t)
            cells.append(f"{d['recall5'] * 100:.1f}% / {d['mrr']:.3f}" if d else "-")
        lines.append(f"| {v} | " + " | ".join(cells) + " |")

    lines += ["", "## 融合权重网格（前 6）", "",
              "| 融合模式 | vector 权重 | bm25 权重 | Recall@5 | MRR@10 |",
              "|---|---|---|---|---|"]
    for g in grid[:6]:
        lines.append(f"| {g['mode']} | {g['vector_weight']} | {g['bm25_weight']} | "
                     f"{g['recall5'] * 100:.1f}% | {g['mrr']:.4f} |")

    lines += ["", "## 成本", "",
              f"- 累计外部花费：¥{snap['spent_yuan']}（上限 ¥{snap['cap_yuan']}）",
              "- 向量与精排结果均有本地缓存，重复评测不再产生调用费用", ""]

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    raw["meta"] = {"docs": len(docs), "queries": len(queries), "by_type": by_type,
                   "index": info["index"], "bm25": info["bm25"],
                   "grid_top": grid[:6], "spent_yuan": snap["spent_yuan"]}
    OUT_JSON.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n报告已写入 {OUT_MD}")


if __name__ == "__main__":
    asyncio.run(main())
