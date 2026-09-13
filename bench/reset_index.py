"""
索引库清理与重建（数据卫生）。

背景：早期版本的 scale_probe 曾把**合成基准向量**写进开发库
（content 形如 `chunk-123 混合检索 RRF 融合 BM25 向量召回...`，doc_id 指向不存在的文档），
导致：文档表为空、向量表有 2 万余条孤儿数据。后果是检索结果被假内容污染，
且任何质量评测都失去意义。

本脚本做三件事：
  1. 体检：报告 documents / vectors 行数、孤儿向量数、内容特征样本
  2. 清理：删除**孤儿向量**（doc_id 无对应文档）+ 删除孤立的合成文档
  3. 重建：按当前 embedding 模型重建种子知识库索引

运行：
    python bench/reset_index.py --dry-run     # 只看体检结果
    python bench/reset_index.py --apply       # 执行清理与重建
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        args.dry_run = True

    from sqlalchemy import delete, func, select

    from app.config import settings
    from app.database import SessionLocal, init_db
    from app.embedding import blob_dim, embedding_client
    from app.models import Document, Vector
    from app.rag.bm25 import bm25_retriever
    from app.rag.vector_store import vector_store
    from app.services.kb_service import ensure_seed_indexed

    await init_db()
    print(f"数据库：{settings.effective_database_url.split('@')[-1]}")

    async with SessionLocal() as s:
        n_doc = (await s.execute(select(func.count()).select_from(Document))).scalar() or 0
        n_seed = (await s.execute(
            select(func.count()).select_from(Document).where(Document.is_seed == 1)
        )).scalar() or 0
        n_by_status = (await s.execute(
            select(Document.status, func.count()).group_by(Document.status)
        )).all()
        n_vec = (await s.execute(select(func.count()).select_from(Vector))).scalar() or 0
        vec_doc_ids = set(
            (await s.execute(select(Vector.doc_id).distinct())).scalars().all())
        doc_ids = {f"doc:{i}" for i in
                   (await s.execute(select(Document.id))).scalars().all()}
        orphan_doc_ids = sorted(vec_doc_ids - doc_ids)
        orphan_rows = 0
        if orphan_doc_ids:
            chunk = 200
            for i in range(0, len(orphan_doc_ids), chunk):
                part = orphan_doc_ids[i:i + chunk]
                orphan_rows += (await s.execute(
                    select(func.count()).select_from(Vector)
                    .where(Vector.doc_id.in_(part))
                )).scalar() or 0
        sample = (await s.execute(
            select(Vector.content).limit(3)
        )).scalars().all()
        dims = (await s.execute(select(Vector.embedding).limit(1))).scalars().first()

    print(f"documents: {n_doc}（seed={n_seed}，按状态 {dict(n_by_status)}）")
    print(f"vectors:   {n_vec}（维度 {blob_dim(dims) if dims else 0}）")
    print(f"孤儿向量:  {orphan_rows} 条，涉及 {len(orphan_doc_ids)} 个不存在的 doc_id")
    if orphan_doc_ids:
        print(f"  示例: {orphan_doc_ids[:5]}")
    print("内容样本:")
    for c in sample:
        print(f"  - {(c or '')[:70]!r}")

    if not args.apply:
        print("\n（--dry-run：未做任何修改；加 --apply 执行清理与重建）")
        return

    async with SessionLocal() as s:
        if orphan_doc_ids:
            for i in range(0, len(orphan_doc_ids), 200):
                part = orphan_doc_ids[i:i + 200]
                await s.execute(delete(Vector).where(Vector.doc_id.in_(part)))
        await s.commit()
    print(f"已清理孤儿向量 {orphan_rows} 条")

    # 维度不一致则整体清空重建（避免 256/1024 混库）
    probe = await embedding_client.probe()
    dim = int(probe.get("dimension") or 0)
    vec_dim = blob_dim(dims) if dims else 0
    if vec_dim and dim and vec_dim != dim:
        async with SessionLocal() as s:
            await s.execute(delete(Vector))
            await s.commit()
        print(f"维度不一致（库 {vec_dim} vs 模型 {dim}）→ 已清空全部向量")

    await ensure_seed_indexed()
    await bm25_retriever.ensure_loaded()
    await vector_store.reload()
    st = await vector_store.stats()
    print(f"重建完成：{st.get('loaded_chunks')} chunks / {st.get('index_dim')} 维 / "
          f"{st.get('index_kind')} / {st.get('index_memory_mb')}MB")
    print(f"BM25：{bm25_retriever.stats()}")


if __name__ == "__main__":
    asyncio.run(main())
