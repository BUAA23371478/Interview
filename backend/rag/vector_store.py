"""向量数据库模块。

优先使用 Chroma（需 C++ Build Tools），不可用时自动回退到 SQLite 纯 Python 实现。

功能:
- 文档分块（RecursiveCharacterTextSplitter + 中文优化分隔符）
- 向量化存储（DeepSeek Embedding API / Mock fallback）
- 语义检索（Top-K 余弦相似度查询 + 分类过滤）

设计文档参考：PLAN.md 第二章
"""

from __future__ import annotations

import json as _json
import math
import os
import sqlite3
from typing import Any

from loguru import logger

from backend.rag.embedding import embedding_client

# ---------------------------------------------------------------------------
# 数据目录
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "rag")
KNOWLEDGE_COLLECTION = "knowledge_base"

# ---------------------------------------------------------------------------
# 文本分块器
# ---------------------------------------------------------------------------

# 尝试导入 langchain text splitter，不可用时使用简易回退
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    _DEFAULT_SPLITTER = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=[
            "\n\n", "\n", "。", "！", "？", "；", "，",
            ".", "!", "?", ";", " ", "",
        ],
        length_function=len,
    )
except ImportError:
    _DEFAULT_SPLITTER = None


def _split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """文本分块：优先使用 LangChain，不可用时使用简易分块。"""
    if _DEFAULT_SPLITTER is not None:
        return _DEFAULT_SPLITTER.split_text(text)

    # 简易回退：按自然段落 + 句子边界分块
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < len(text) else end
    return chunks if chunks else [text]


# ===================================================================
# 纯 Python SQLite 向量存储（无需 C++ 编译，跨平台）
# ===================================================================


class SimpleVectorStore:
    """基于 SQLite 的纯 Python 向量存储。

    不需要 C++ 编译工具，不依赖 chromadb。
    使用余弦相似度进行语义检索。
    """

    def __init__(self, persist_dir: str | None = None) -> None:
        persist_dir = persist_dir or DATA_DIR
        os.makedirs(persist_dir, exist_ok=True)

        self._db_path = os.path.join(persist_dir, "vectors.db")
        self._emb_client = embedding_client
        self._init_db()

        logger.info(f"SimpleVectorStore 初始化完成 db={self._db_path}")

    def _init_db(self) -> None:
        """初始化 SQLite 表结构。"""
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_id ON vectors(doc_id)")
        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    @staticmethod
    def _embedding_to_bytes(embedding: list[float]) -> bytes:
        """将向量序列化为紧凑 float 数组。"""
        import struct
        return struct.pack(f">{len(embedding)}d", *embedding)

    @staticmethod
    def _bytes_to_embedding(data: bytes) -> list[float]:
        """从紧凑字节反序列化向量。"""
        import struct
        n = len(data) // 8
        return list(struct.unpack(f">{n}d", data))

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算两个向量的余弦相似度。"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ------------------------------------------------------------------
    # 索引
    # ------------------------------------------------------------------

    async def index_document(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """索引文档：分块 → 向量化 → 存入 SQLite。"""
        if not text.strip():
            logger.warning(f"文档 {doc_id} 内容为空，跳过索引")
            return 0

        chunks = _split_text(text)
        if not chunks:
            logger.warning(f"文档 {doc_id} 分块后无内容")
            return 0

        logger.info(f"文档 {doc_id} 分块完成: {len(chunks)} chunks")

        conn = self._get_conn()

        # 删除旧索引
        conn.execute("DELETE FROM vectors WHERE doc_id = ?", (doc_id,))

        # 逐块向量化
        batch_size = 20
        total = 0
        meta_json_base = _json.dumps(metadata or {}, ensure_ascii=False)

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            embeddings = await self._emb_client.embed_batch(batch)

            rows = []
            for j, chunk in enumerate(batch):
                idx = i + j
                rows.append((
                    f"{doc_id}_{idx}",
                    doc_id,
                    idx,
                    len(chunks),
                    chunk,
                    self._embedding_to_bytes(embeddings[j]),
                    meta_json_base,
                ))

            conn.executemany(
                "INSERT OR REPLACE INTO vectors (id, doc_id, chunk_index, chunk_count, content, embedding, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            total += len(batch)

        conn.commit()
        conn.close()

        logger.info(f"文档 {doc_id} 索引完成: {total} chunks")
        return total

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
        similarity_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        """语义检索：向量化查询 → 余弦相似度排序 → Top-K。"""
        if not query.strip():
            return []

        query_embedding = await self._emb_client.embed(query)

        conn = self._get_conn()

        # 加载所有向量（知识库数据量不大时可行；后续可加 IVF 索引优化）
        if filter:
            # 简单分类过滤：在 metadata_json 中匹配
            rows = conn.execute(
                "SELECT id, doc_id, chunk_index, content, embedding, metadata_json FROM vectors"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, doc_id, chunk_index, content, embedding, metadata_json FROM vectors"
            ).fetchall()

        conn.close()

        if not rows:
            return []

        # 计算余弦相似度
        scored: list[tuple[float, dict]] = []
        for row in rows:
            _, doc_id, chunk_idx, content, emb_bytes, meta_json = row
            embedding = self._bytes_to_embedding(emb_bytes)
            similarity = self._cosine_similarity(query_embedding, embedding)

            if similarity < similarity_threshold:
                continue

            # 分类过滤
            if filter:
                try:
                    meta = _json.loads(meta_json) if meta_json else {}
                except _json.JSONDecodeError:
                    meta = {}
                match = True
                for k, v in filter.items():
                    if meta.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            meta = {}
            try:
                meta = _json.loads(meta_json) if meta_json else {}
            except _json.JSONDecodeError:
                pass

            scored.append((similarity, {
                "content": content,
                "metadata": {**meta, "doc_id": doc_id, "chunk_index": chunk_idx},
                "score": round(similarity, 4),
            }))

        # 排序 + Top-K
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [item for _, item in scored[:top_k]]

        logger.debug(f"检索完成 query='{query[:50]}...' top_k={top_k} results={len(results)}")
        return results

    # ------------------------------------------------------------------
    # 管理
    # ------------------------------------------------------------------

    async def delete_document(self, doc_id: str) -> bool:
        """删除文档的所有索引。"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM vectors WHERE doc_id = ?", (doc_id,))
        count = cursor.fetchone()[0]
        if count > 0:
            conn.execute("DELETE FROM vectors WHERE doc_id = ?", (doc_id,))
            conn.commit()
            logger.info(f"删除文档索引 {doc_id}: {count} chunks")
        conn.close()
        return count > 0

    async def reindex_document(
        self, doc_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> int:
        """重建索引。"""
        await self.delete_document(doc_id)
        return await self.index_document(doc_id, text, metadata)

    async def get_document_count(self) -> int:
        """获取已索引文档数量。"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(DISTINCT doc_id) FROM vectors")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    async def list_documents(self) -> list[dict[str, Any]]:
        """列出已索引文档摘要。"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT doc_id, metadata_json, COUNT(*) as cnt FROM vectors GROUP BY doc_id"
        ).fetchall()
        conn.close()

        result = []
        for doc_id, meta_json, cnt in rows:
            try:
                meta = _json.loads(meta_json) if meta_json else {}
            except _json.JSONDecodeError:
                meta = {}
            result.append({
                "doc_id": doc_id,
                "filename": meta.get("filename", ""),
                "category": meta.get("category", ""),
                "file_type": meta.get("file_type", ""),
                "chunk_count": cnt,
            })
        return result

    # ------------------------------------------------------------------
    # 便捷方法（供 Agent 调用）
    # ------------------------------------------------------------------

    async def search_for_agent(
        self, query: str, top_k: int = 3, category: str | None = None
    ) -> str:
        """检索结果格式化为 Agent prompt 上下文。"""
        filter_dict = {"category": category} if category else None
        items = await self.search(query, top_k=top_k, filter=filter_dict, similarity_threshold=0.5)

        if not items:
            return "暂无相关参考资料"

        lines = ["以下是相关知识库参考资料：", ""]
        for i, item in enumerate(items, 1):
            source = item.get("metadata", {}).get("filename", "未知来源")
            lines.append(f"【参考 {i}】（来源: {source}, 相关度: {item['score']:.2f}）")
            lines.append(item["content"])
            lines.append("")

        return "\n".join(lines)


# ===================================================================
# 统一入口：优先 Chroma，不可用则回退 SimpleVectorStore
# ===================================================================


def _create_vector_store() -> SimpleVectorStore:
    """创建向量存储实例。

    优先 Chroma（HNSW 索引，性能最优），不可用时回退 SQLite 纯 Python 实现。
    """
    # 禁用 Chroma 遥测（避免 "capture() takes 1 positional argument" 报错）
    import os as _os
    _os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
    _os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

    # 尝试 Chroma
    try:
        import chromadb

        chroma_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chroma")
        os.makedirs(chroma_dir, exist_ok=True)

        client = chromadb.PersistentClient(path=chroma_dir)
        # 测试可用性（Chroma 要求 collection 名以字母数字开头和结尾）
        test_col = client.get_or_create_collection("chroma_test")
        client.delete_collection("chroma_test")
        logger.info(f"✅ 使用 Chroma 向量存储（HNSW 索引）path={chroma_dir}")
        return _ChromaVectorStore(client)
    except ImportError:
        logger.warning(
            "⚠️ chromadb 未安装，回退到 SQLite 向量存储。"
            "RAG 检索功能仍可用，但大规模数据下性能不如 Chroma。"
            "安装 Chroma: pip install chromadb"
        )
    except (OSError, Exception) as e:
        logger.warning(
            f"⚠️ Chroma 启动失败（{e}），回退到 SQLite 向量存储。"
            "RAG 检索功能仍可用，但建议检查 Chroma 配置以获取最佳性能。"
        )

    return SimpleVectorStore()


class _ChromaVectorStore:
    """Chroma 适配层 — 接口与 SimpleVectorStore 一致。"""

    def __init__(self, client) -> None:
        self._client = client
        self._emb_client = embedding_client
        self._active_collection: str | None = None

    def _get_collection(self):
        """获取当前活跃的 collection（自动检测维度）。"""
        if self._active_collection:
            try:
                return self._client.get_collection(self._active_collection)
            except Exception:
                pass
        # 尝试常见维度后缀（1024 = BGE-M3, 1536 = OpenAI, 256 = mock）
        for dim in [1024, 1536, 256]:
            name = f"{KNOWLEDGE_COLLECTION}_{dim}"
            try:
                col = self._client.get_collection(name)
                if col.count() > 0:
                    self._active_collection = name
                    return col
            except Exception:
                continue
        # 回退到旧的无后缀 collection（兼容升级前数据）
        try:
            return self._client.get_collection(KNOWLEDGE_COLLECTION)
        except Exception:
            return None

    async def index_document(self, doc_id: str, text: str, metadata: dict | None = None) -> int:
        if not text.strip():
            return 0
        chunks = _split_text(text)
        if not chunks:
            return 0

        # 先取一批向量，确定维度
        first_batch = chunks[:1]
        first_embs = await self._emb_client.embed_batch(first_batch)
        emb_dim = len(first_embs[0]) if first_embs else 256

        # 用维度作为 collection 名后缀，避免 256-dim（mock）和 1024-dim（BGE-M3）冲突
        collection_name = f"{KNOWLEDGE_COLLECTION}_{emb_dim}"

        # 如果旧 collection 维度不对，删掉重建
        try:
            old_collection = self._client.get_collection(KNOWLEDGE_COLLECTION)
            old_emb = old_collection.get(limit=1, include=["embeddings"])
            if old_emb and old_emb.get("embeddings") and old_emb["embeddings"][0]:
                old_dim = len(old_emb["embeddings"][0])
                if old_dim != emb_dim:
                    logger.warning(
                        f"向量维度变更（{old_dim} → {emb_dim}），重建 collection"
                    )
                    self._client.delete_collection(KNOWLEDGE_COLLECTION)
        except Exception:
            pass

        self._active_collection = collection_name
        collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # 如果旧 collection（无后缀）有数据，删除
        try:
            old = self._client.get_collection(KNOWLEDGE_COLLECTION)
            if old.count() > 0:
                self._client.delete_collection(KNOWLEDGE_COLLECTION)
        except Exception:
            pass

        # 删除旧索引
        try:
            existing = collection.get(where={"doc_id": doc_id})
            if existing and existing.get("ids"):
                collection.delete(ids=existing["ids"])
        except Exception:
            pass

        total = 0
        batch_size = 20
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            embeddings = await self._emb_client.embed_batch(batch)
            ids = [f"{doc_id}_{i + j}" for j in range(len(batch))]
            metadatas = [
                {**(metadata or {}), "doc_id": doc_id, "chunk_index": i + j, "chunk_count": len(chunks)}
                for j in range(len(batch))
            ]
            collection.add(documents=batch, embeddings=embeddings, metadatas=metadatas, ids=ids)
            total += len(batch)

        return total

    async def search(
        self, query: str, top_k: int = 5,
        filter: dict | None = None, similarity_threshold: float = 0.0,
    ) -> list[dict]:
        if not query.strip():
            return []
        collection = self._get_collection()
        if collection is None:
            return []

        q_emb = await self._emb_client.embed(query)
        try:
            results = collection.query(
                query_embeddings=[q_emb], n_results=top_k, where=filter,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        items = []
        for i, doc in enumerate(documents):
            dist = distances[i] if i < len(distances) else 0
            sim = 1.0 - dist
            if sim < similarity_threshold:
                continue
            items.append({
                "content": doc,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "score": round(sim, 4),
            })
        return items

    async def delete_document(self, doc_id: str) -> bool:
        collection = self._get_collection()
        if collection is None:
            return False
        try:
            existing = collection.get(where={"doc_id": doc_id})
            if existing and existing.get("ids"):
                collection.delete(ids=existing["ids"])
                return True
        except Exception:
            pass
        return False

    async def reindex_document(self, doc_id: str, text: str, metadata: dict | None = None) -> int:
        await self.delete_document(doc_id)
        return await self.index_document(doc_id, text, metadata)

    async def get_document_count(self) -> int:
        collection = self._get_collection()
        if collection is None:
            return 0
        try:
            result = collection.get(include=["metadatas"])
            if result and result.get("metadatas"):
                return len(set(m.get("doc_id", "") for m in result["metadatas"] if m))
        except Exception:
            pass
        return 0

    async def list_documents(self) -> list[dict]:
        collection = self._get_collection()
        if collection is None:
            return []
        try:
            result = collection.get(include=["metadatas"])
            if not result or not result.get("metadatas"):
                return []
            doc_map: dict[str, dict] = {}
            for meta in result["metadatas"]:
                if not meta:
                    continue
                did = meta.get("doc_id", "")
                if did not in doc_map:
                    doc_map[did] = {"doc_id": did, "filename": meta.get("filename", ""),
                                    "category": meta.get("category", ""),
                                    "file_type": meta.get("file_type", ""), "chunk_count": 0}
                doc_map[did]["chunk_count"] += 1
            return list(doc_map.values())
        except Exception:
            return []

    async def search_for_agent(self, query: str, top_k: int = 3, category: str | None = None) -> str:
        filter_dict = {"category": category} if category else None
        items = await self.search(query, top_k=top_k, filter=filter_dict, similarity_threshold=0.5)
        if not items:
            return "暂无相关参考资料"
        lines = ["以下是相关知识库参考资料：", ""]
        for i, item in enumerate(items, 1):
            source = item.get("metadata", {}).get("filename", "未知来源")
            lines.append(f"【参考 {i}】（来源: {source}, 相关度: {item['score']:.2f}）")
            lines.append(item["content"])
            lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

vector_store = _create_vector_store()
