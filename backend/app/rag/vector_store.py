"""
向量存储：与业务数据同库（SQLAlchemy ORM，生产用 MySQL / 本地用 SQLite）。

表结构（models.Vector）：
    vectors(id, doc_id, chunk_index, chunk_count, content, embedding BLOB, metadata_json)

- 生产（平台托管 MySQL）：向量表与 documents 等业务表同库，容器重启不丢失
- 本地（SQLite）：向量表在 interview.db 内
- 同一套接口：index_document / search / delete_document / total_count 等
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.embedding import cosine_similarity, embedding_client, pack_vector, unpack_vector
from app.models import Vector


class VectorStore:
    """基于 ORM 的向量存储（与业务库同库）。"""

    async def index_document(self, doc_id: str, chunks: List[str], metadata: Dict[str, Any]) -> int:
        """分块向量化入库，返回 chunk 数。"""
        if not chunks:
            return 0
        vectors = await embedding_client.embed_batch(chunks)
        async with SessionLocal() as session:
            for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
                session.add(Vector(
                    doc_id=doc_id,
                    chunk_index=i,
                    chunk_count=len(chunks),
                    content=chunk,
                    embedding=pack_vector(vec),
                    metadata_json=json.dumps(metadata, ensure_ascii=False),
                ))
            await session.commit()
        return len(chunks)

    async def search(self, query: str, top_k: int = 5,
                     filter_meta: Optional[Dict[str, Any]] = None,
                     similarity_threshold: float = 0.0) -> List[Dict[str, Any]]:
        """余弦检索。"""
        qvec = await embedding_client.embed(query)
        async with SessionLocal() as session:
            rows = (await session.execute(select(Vector))).scalars().all()
        results: List[Dict[str, Any]] = []
        for row in rows:
            try:
                meta = json.loads(row.metadata_json or "{}")
            except json.JSONDecodeError:
                meta = {}
            if filter_meta:
                skip = False
                for k, v in filter_meta.items():
                    if meta.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue
            vec = unpack_vector(row.embedding)
            score = cosine_similarity(qvec, vec)
            if score >= similarity_threshold:
                results.append({
                    "id": str(row.id),
                    "doc_id": row.doc_id,
                    "content": row.content,
                    "metadata": meta,
                    "score": round(score, 4),
                    "source": "vector",
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def delete_document(self, doc_id: str) -> int:
        async with SessionLocal() as session:
            res = await session.execute(delete(Vector).where(Vector.doc_id == doc_id))
            await session.commit()
            return res.rowcount or 0

    async def document_chunk_count(self, doc_id: str) -> int:
        async with SessionLocal() as session:
            row = (await session.execute(
                select(Vector).where(Vector.doc_id == doc_id)
            )).scalars().first()
            return row.chunk_count if row else 0

    async def total_count(self) -> int:
        from sqlalchemy import func
        async with SessionLocal() as session:
            return (await session.execute(select(func.count()).select_from(Vector))).scalar() or 0

    async def list_doc_ids(self) -> List[str]:
        async with SessionLocal() as session:
            rows = (await session.execute(select(Vector.doc_id).distinct())).scalars().all()
            return list(rows)


vector_store = VectorStore()
