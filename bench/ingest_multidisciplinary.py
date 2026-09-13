"""批量入库多学科种子文档到知识库（含向量索引）。

将 backend/data/kb_seed/<学科>/*.md 全部读入：
  - 在 Document 表创建 approved + is_seed=1 的记录
  - 向量与 BM25 自动重建
  - chunk_count 写入数据库

幂等：已存在（按 filename）则重建索引；不存在则新建。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Document
from app.services.kb_service import _index_doc_chunks, _sha256, split_text, extract_text_from_bytes
from loguru import logger

SEED_DIR = ROOT / "backend" / "data" / "kb_seed"

# 学科目录 → 展示名（与子表 KB_CATEGORY 兼容）
SUBJECT_LABELS = {
    "cs":          "计算机·软件·开发",
    "testing":     "测试",
    "product":     "产品",
    "industrial":  "工业设计",
    "economics":   "经济学",
    "english":     "英语",
    "law":         "法学",
    "philosophy":  "哲学",
}


async def ingest_one(category: str, label: str, file_path: Path) -> Dict[str, Any]:
    """入库一篇文档（含向量+BM25 索引）。"""
    content = extract_text_from_bytes(file_path.read_bytes(), file_path.name)
    content_hash = _sha256(content)
    async with SessionLocal() as s:
        existing = (await s.execute(
            select(Document).where(Document.filename == file_path.name)
        )).scalar_one_or_none()

        if existing:
            doc = existing
            doc.title = file_path.stem
            doc.category = label
            doc.content_text = content
            doc.char_count = len(content)
            doc.file_size = file_path.stat().st_size
            doc.status = "approved"
            doc.is_seed = 1
            await s.commit()
            await s.refresh(doc)
        else:
            doc = Document(
                maoo_user_id=0,
                filename=file_path.name,
                title=file_path.stem,
                category=label,
                file_type="md",
                file_size=file_path.stat().st_size,
                char_count=len(content),
                status="approved",
                is_seed=1,
                original_hash=content_hash,
                content_text=content,
            )
            s.add(doc)
            await s.commit()
            await s.refresh(doc)

        meta = {"doc_title": doc.title, "category": label,
                "status": "approved", "doc_id": f"doc:{doc.id}"}
        chunks = split_text(content)
        cc = await _index_doc_chunks(doc.id, chunks, meta)
        doc.chunk_count = cc
        await s.commit()
        return {"id": doc.id, "title": doc.title, "category": label,
                "chunks": cc, "chars": len(content)}


async def main() -> None:
    if not SEED_DIR.exists():
        logger.error(f"seed 目录不存在: {SEED_DIR}")
        return
    await init_db()
    summary: Dict[str, int] = {}
    files: List[Path] = []
    for sub in sorted(SEED_DIR.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name not in SUBJECT_LABELS:
            logger.warning(f"未知学科目录: {sub.name}（跳过）")
            continue
        for f in sorted(sub.glob("*.md")):
            files.append((sub.name, SUBJECT_LABELS[sub.name], f))
    logger.info(f"待入库: {len(files)} 篇（{len(SUBJECT_LABELS)} 个学科）")
    for i, (sub, label, fp) in enumerate(files, 1):
        try:
            r = await ingest_one(sub, label, fp)
            summary.setdefault(sub, 0)
            summary[sub] += 1
            logger.info(f"[{i}/{len(files)}] {label} / {r['title']} → {r['chunks']} chunks")
        except Exception as e:  # noqa: BLE001
            logger.error(f"入库失败 {fp}: {e}")
    logger.info(f"完成：{dict(summary)}, 共 {sum(summary.values())} 篇")


if __name__ == "__main__":
    asyncio.run(main())
