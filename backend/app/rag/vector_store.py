"""
向量存储：SQLite 内嵌向量库（余弦相似度）。

表结构：
    vectors(id, doc_id, chunk_index, chunk_count, content, embedding BLOB, metadata_json)

- 零外部依赖，适合单机部署（MAOO 平台不托管向量数据库）
- mock 嵌入模式下同样工作（确定性向量）
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.config import settings
from app.embedding import cosine_similarity, embedding_client, pack_vector, unpack_vector


class VectorStore:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or str(settings.data_dir / "vectors.db")
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vectors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    chunk_index INTEGER DEFAULT 0,
                    chunk_count INTEGER DEFAULT 0,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    metadata_json TEXT DEFAULT '{}'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vectors_doc ON vectors(doc_id)")

    async def index_document(self, doc_id: str, chunks: List[str], metadata: Dict[str, Any]) -> int:
        """分块向量化入库，返回 chunk 数。"""
        if not chunks:
            return 0
        vectors = await embedding_client.embed_batch(chunks)
        with self._conn() as conn:
            for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
                conn.execute(
                    "INSERT INTO vectors (doc_id, chunk_index, chunk_count, content, embedding, metadata_json)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (doc_id, i, len(chunks), chunk, pack_vector(vec), json.dumps(metadata, ensure_ascii=False)),
                )
        return len(chunks)

    async def search(self, query: str, top_k: int = 5,
                     filter_meta: Optional[Dict[str, Any]] = None,
                     similarity_threshold: float = 0.0) -> List[Dict[str, Any]]:
        """余弦检索。"""
        qvec = await embedding_client.embed(query)
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM vectors").fetchall()
        results: List[Dict[str, Any]] = []
        for row in rows:
            meta = json.loads(row["metadata_json"] or "{}")
            if filter_meta:
                skip = False
                for k, v in filter_meta.items():
                    if meta.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue
            vec = unpack_vector(row["embedding"])
            score = cosine_similarity(qvec, vec)
            if score >= similarity_threshold:
                results.append({
                    "id": str(row["id"]),
                    "doc_id": row["doc_id"],
                    "content": row["content"],
                    "metadata": meta,
                    "score": round(score, 4),
                    "source": "vector",
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete_document(self, doc_id: str) -> int:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM vectors WHERE doc_id = ?", (doc_id,))
            return cur.rowcount

    def document_chunk_count(self, doc_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM vectors WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            return int(row["c"]) if row else 0

    def total_count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM vectors").fetchone()
            return int(row["c"]) if row else 0

    def list_doc_ids(self) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT DISTINCT doc_id FROM vectors").fetchall()
            return [r["doc_id"] for r in rows]


vector_store = VectorStore()
