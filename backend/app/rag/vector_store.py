"""
向量存储（与业务数据同库，SQLAlchemy ORM；生产 MySQL / 本地 SQLite）。

初版问题（已修复）：
  1. `search()` 每次 `select(Vector)` 把**全表**拉进内存再逐条跑 Python 余弦 → O(N)；
     20,000 chunk 时单次查询 P50 已达 4.9s（见 bench/scale_result_before.md）。
  2. 结果 id 用的是数据库自增主键，而 BM25 那一路用的是 `{doc_id}#{chunk_index}`，
     两路 id 命名空间不相交 → RRF 融合无法把同一 chunk 的两路得分相加（只做了并集）。

现在：
  - 内存向量矩阵（float32）+ numpy 批量余弦，可选 faiss HNSW ANN 索引；
  - chunk 统一 id = `{doc_id}#{chunk_index}`，与 BM25 对齐，RRF 才真正生效；
  - 通过「DB 版本号（count, max_id）」惰性重载，索引变更自动感知；
  - 维度不一致时显式失败并告警，不做静默截断。
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger
from sqlalchemy import delete, func, insert, select

from app.config import settings
from app.database import SessionLocal
from app.embedding import MAGIC_F32, MAGIC_F64, blob_dim, embedding_client, pack_vector
from app.models import Vector

_INVERTED_KEYS = ("status", "category", "doc_title", "doc_id")

# 向量 BLOB 一律使用**大端**（历史数据 `struct.pack(">Nd")` 也是大端，不可改）。
# numpy 默认按本机字节序解析，必须显式指定 ">f4" / ">f8"，
# 否则会把大端字节当成小端读，整张索引矩阵变成 inf/NaN（检索结果静默失效）。
_F32_BE = np.dtype(">f4")
_F64_BE = np.dtype(">f8")


def _stack_vectors(blobs: List[bytes], dim: int) -> np.ndarray:
    """BLOB 列表 → (N, dim) 本机 float32 矩阵。兼容 float32 / float64 / 历史无头格式。"""
    out = np.empty((len(blobs), dim), dtype=np.float32)
    for i, b in enumerate(blobs):
        if b[:4] == MAGIC_F32:
            out[i] = np.frombuffer(b, dtype=_F32_BE, count=dim, offset=4)
        elif b[:4] == MAGIC_F64:
            out[i] = np.frombuffer(b, dtype=_F64_BE, count=dim, offset=4)
        else:  # 历史裸 float64（大端、无头）
            out[i] = np.frombuffer(b, dtype=_F64_BE, count=dim)
    return out


class VectorStore:
    """内存向量索引 + numpy / faiss 检索。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._matrix: Optional[np.ndarray] = None
        self._norms: Optional[np.ndarray] = None
        self._ids: List[str] = []
        self._doc_ids: List[str] = []
        self._contents: List[str] = []
        self._metas: List[Dict[str, Any]] = []
        self._meta_index: Dict[str, np.ndarray] = {}
        self._dim = 0
        self._version: Tuple[int, int] = (-1, -1)
        self._checked_at = 0.0
        self._dirty = True
        self._ann: Any = None
        self._ann_kind = "none"
        self._build_ms = 0.0
        self._last_query_ms = 0.0
        self._skipped_embedding = 0   # 因 Embedding 不可用而关闭向量通道的次数

    # ── 索引装载 ────────────────────────────────────────────────────
    async def _db_version(self) -> Tuple[int, int]:
        async with SessionLocal() as session:
            row = (await session.execute(
                select(func.count(Vector.id), func.max(Vector.id)).select_from(Vector)
            )).first()
        return (int(row[0] or 0), int(row[1] or 0))

    async def _ensure_loaded(self) -> None:
        if self._matrix is not None and not self._dirty:
            if time.time() - self._checked_at < settings.rag_index_reload_interval:
                return
            if await self._db_version() == self._version:
                self._checked_at = time.time()
                return
        async with self._lock:
            if self._matrix is not None and not self._dirty:
                if await self._db_version() == self._version:
                    self._checked_at = time.time()
                    return
            await self._load()

    async def _load(self) -> None:
        t0 = time.perf_counter()
        async with SessionLocal() as session:
            rows = (await session.execute(
                select(Vector.id, Vector.doc_id, Vector.chunk_index,
                       Vector.content, Vector.embedding, Vector.metadata_json)
            )).all()

        if not rows:
            self._matrix, self._norms, self._ann = None, None, None
            self._ids, self._doc_ids, self._contents, self._metas = [], [], [], []
            self._meta_index, self._dim, self._version = {}, 0, (0, 0)
            self._ann_kind, self._dirty = "none", False
            self._checked_at = time.time()
            return

        dim = blob_dim(rows[0][4])
        if dim == 0:
            logger.error("向量索引维度为 0，跳过装载")
            return

        bad = [r[0] for r in rows if blob_dim(r[4]) != dim]
        if bad:
            logger.error("向量索引存在 {} 条维度不一致记录（期望 {} 维，示例 DB id={}），"
                         "已跳过；请重建索引", len(bad), dim, bad[0])
        keep = [r for r in rows if blob_dim(r[4]) == dim]

        self._matrix = _stack_vectors([r[4] for r in keep], dim)
        # 防御：字节序/截断类错误会让整张矩阵变成 inf/NaN，检索结果会静默失准。
        # 宁可显式失败并告警，也不要返回看似正常的错误排序。
        non_finite = int(np.count_nonzero(~np.isfinite(self._matrix)))
        if non_finite:
            logger.error("向量索引装载异常：{} 个非有限值（inf/NaN），"
                         "疑似字节序或 BLOB 截断问题；本次装载结果不可信，已丢弃",
                         non_finite)
            self._matrix, self._norms, self._ann = None, None, None
            self._ann_kind, self._dirty = "error", False
            return
        self._dim = dim
        self._doc_ids = [r[1] for r in keep]
        # chunk 统一 id：与 BM25 的 {doc_id}#{index} 对齐，RRF 融合才成立
        self._ids = [f"{r[1]}#{r[2]}" for r in keep]
        self._contents = [r[3] or "" for r in keep]
        self._metas = []
        for r in keep:
            try:
                self._metas.append(json.loads(r[5] or "{}"))
            except (TypeError, json.JSONDecodeError):
                self._metas.append({})

        self._meta_index = {
            k: np.array([m.get(k, "") for m in self._metas], dtype=object)
            for k in _INVERTED_KEYS
        }
        self._norms = np.linalg.norm(self._matrix, axis=1)
        self._norms[self._norms == 0] = 1.0

        # 预归一化矩阵：余弦 = 点积 / ‖q‖
        # 注意：_version 必须在 ANN 之前赋值 —— 索引落盘文件名依赖它做失效判断
        self._version = (len(rows), max(r[0] for r in rows))
        self._ann, self._ann_kind = None, "exact"
        n = self._matrix.shape[0]
        want_ann = settings.rag_index_type == "hnsw" or (
            settings.rag_index_type == "auto" and n >= settings.rag_ann_threshold)
        if want_ann:
            self._build_or_load_ann(dim, n)

        self._dirty = False
        self._checked_at = time.time()
        self._build_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info("向量索引已装载: {} 条 / {} 维 / {} / {:.1f}MB / 耗时 {}ms",
                    self._matrix.shape[0], dim, self._ann_kind,
                    self._matrix.nbytes / 1024 / 1024, self._build_ms)

    def mark_dirty(self) -> None:
        """索引写入后调用，下次查询触发重载。"""
        self._dirty = True

    async def reload(self) -> None:
        async with self._lock:
            await self._load()

    # ── ANN 索引：构建 / 持久化 ──────────────────────────────────────
    def _ann_path(self, dim: int, n: int, max_id: int) -> Path:
        """索引文件名带上规模与最大 id —— 数据变了文件名就变，天然失效，不会读到脏索引。"""
        return settings.vector_index_dir / f"hnsw_d{dim}_n{n}_v{max_id}.faiss"

    def _build_or_load_ann(self, dim: int, n: int) -> None:
        """构建 HNSW 索引；若磁盘已有匹配快照则直接加载。

        为什么必须持久化：10 万 chunk 的 HNSW（M=32, efConstruction=200）
        实测构建需要 **105 秒**（见 bench/scale_result_100k_hnsw.md）。
        每次进程冷启动重建等于不可用；落盘后冷启动只受加载带宽限制（毫秒级）。
        """
        try:
            import faiss
        except Exception as e:  # noqa: BLE001
            logger.warning("faiss 不可用，回退精确检索：{}", e)
            self._ann, self._ann_kind = None, "exact"
            return
        try:
            path = self._ann_path(dim, n, self._version[1])
            if path.exists():
                self._ann = faiss.read_index(str(path))
                self._ann.hnsw.efSearch = settings.rag_hnsw_ef_search
                self._ann_kind = "hnsw(disk)"
                logger.info("HNSW 索引从磁盘加载: {}（{} 条）", path.name, n)
                return
            index = faiss.IndexHNSWFlat(dim, settings.rag_hnsw_m, faiss.METRIC_INNER_PRODUCT)
            index.hnsw.efConstruction = settings.rag_hnsw_ef_construction
            index.hnsw.efSearch = settings.rag_hnsw_ef_search
            normed = np.ascontiguousarray(self._matrix / self._norms[:, None], dtype=np.float32)
            index.add(normed)
            self._ann, self._ann_kind = index, "hnsw"
            try:
                faiss.write_index(index, str(path))
                logger.info("HNSW 索引已构建并落盘: {}（{} 条）", path.name, n)
            except Exception as e:  # noqa: BLE001
                logger.warning("HNSW 索引落盘失败（不影响本次检索）: {}", e)
        except Exception as e:  # noqa: BLE001
            logger.warning("HNSW 索引构建失败，回退精确检索：{}", e)
            self._ann, self._ann_kind = None, "exact"

    # ── 检索 ────────────────────────────────────────────────────────
    def _mask(self, filter_meta: Dict[str, Any]) -> Optional[np.ndarray]:
        if not filter_meta or self._matrix is None:
            return None
        mask = np.ones(len(self._ids), dtype=bool)
        for k, v in filter_meta.items():
            col = self._meta_index.get(k)
            if col is None:
                col = np.array([m.get(k, "") for m in self._metas], dtype=object)
                self._meta_index[k] = col
            mask &= (col == v)
        return mask

    async def search(self, query: str, top_k: int = 5,
                     filter_meta: Optional[Dict[str, Any]] = None,
                     similarity_threshold: float = 0.0) -> List[Dict[str, Any]]:
        """向量检索：内存矩阵批量余弦（或 HNSW ANN），返回 top_k。"""
        await self._ensure_loaded()
        if self._matrix is None or not self._ids:
            return []

        qvec = await embedding_client.embed(query)
        if len(qvec) != self._dim:
            logger.error("查询向量维度 {} 与索引维度 {} 不一致，跳过向量检索以避免静默错误排序。"
                         "请确认 EMBEDDING_MODEL 未变更，否则需重建索引。", len(qvec), self._dim)
            return []

        q = np.asarray(qvec, dtype=np.float32)
        qn = float(np.linalg.norm(q)) or 1.0
        t0 = time.perf_counter()

        mask = self._mask(filter_meta)
        if mask is not None and not mask.any():
            return []

        if mask is None and self._ann is not None:
            k = min(max(top_k * 4, top_k), len(self._ids))
            dist, idx = self._ann.search(np.ascontiguousarray((q / qn).reshape(1, -1)), k)
            cand_idx, scores = idx[0], dist[0]
        else:
            # 无过滤时直接吃整块矩阵，避免不必要的整表拷贝（10 万 × 1024 float32 ≈ 400MB）
            if mask is None:
                sub, norms_sel, cand = self._matrix, self._norms, None
            else:
                cand = np.nonzero(mask)[0]
                if cand.size == 0:
                    return []
                sub, norms_sel = self._matrix[cand], self._norms[cand]
            sims = (sub @ q) / (norms_sel * qn + 1e-9)
            take = min(max(top_k * 4, top_k), int(sims.size))
            if take < sims.size:
                part = np.argpartition(-sims, take - 1)[:take]
                order = part[np.argsort(-sims[part])]
            else:
                order = np.argsort(-sims)
            cand_idx = order if cand is None else cand[order]
            scores = sims[order]

        out: List[Dict[str, Any]] = []
        for i, s in zip(cand_idx, scores):
            score = float(s)
            if score < similarity_threshold:
                continue
            out.append({
                "id": self._ids[i],
                "doc_id": self._doc_ids[i],
                "content": self._contents[i],
                "metadata": self._metas[i],
                "score": round(score, 4),
                "source": "vector",
            })
            if len(out) >= top_k:
                break

        self._last_query_ms = round((time.perf_counter() - t0) * 1000, 2)
        return out

    # ── 写入 ────────────────────────────────────────────────────────
    async def index_document(self, doc_id: str, chunks: List[str],
                             metadata: Dict[str, Any]) -> int:
        """分块向量化入库，返回 chunk 数。

        两条硬约束：
          1. **全量成功才落库**：任一分块拿不到真实向量就整体失败，
             不允许写入半截索引（部分 chunk 缺失会导致召回率静默下降）；
          2. 批量 INSERT（executemany）而非逐条 add——千级分块时相差一个数量级。
        """
        if not chunks:
            return 0
        vectors = await embedding_client.embed_batch(chunks)
        missing = [i for i, v in enumerate(vectors) if not v]
        if missing:
            raise EmbeddingUnavailable(
                f"分块向量化失败 {len(missing)}/{len(chunks)} 条，拒绝写入不完整索引。"
                "（Embedding 服务不可用时会这样保护索引一致性）"
            )
        meta_json = json.dumps(metadata, ensure_ascii=False)
        rows = [
            {"doc_id": doc_id, "chunk_index": i, "chunk_count": len(chunks),
             "content": chunk, "embedding": pack_vector(vec), "metadata_json": meta_json}
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]
        async with SessionLocal() as session:
            for i in range(0, len(rows), 500):
                await session.execute(insert(Vector), rows[i:i + 500])
            await session.commit()
        self.mark_dirty()
        return len(chunks)

    async def delete_document(self, doc_id: str) -> int:
        async with SessionLocal() as session:
            res = await session.execute(delete(Vector).where(Vector.doc_id == doc_id))
            await session.commit()
            count = res.rowcount or 0
        self.mark_dirty()
        return count

    async def document_chunk_count(self, doc_id: str) -> int:
        async with SessionLocal() as session:
            row = (await session.execute(
                select(Vector.chunk_count).where(Vector.doc_id == doc_id)
            )).scalars().first()
            return int(row or 0)

    async def total_count(self) -> int:
        async with SessionLocal() as session:
            return int((await session.execute(
                select(func.count()).select_from(Vector)
            )).scalar() or 0)

    async def list_doc_ids(self) -> List[str]:
        async with SessionLocal() as session:
            rows = (await session.execute(select(Vector.doc_id).distinct())).scalars().all()
            return list(rows)

    # ── 可观测性 ────────────────────────────────────────────────────
    async def stats(self) -> Dict[str, Any]:
        loaded = 0 if self._matrix is None else int(self._matrix.shape[0])
        return {
            "loaded_chunks": loaded,
            "index_dim": self._dim,
            "index_kind": self._ann_kind,
            "index_version": list(self._version),
            "load_ms": self._build_ms,
            "index_memory_mb": round(self._matrix.nbytes / 1024 / 1024, 2)
            if self._matrix is not None else 0.0,
            "last_query_ms": self._last_query_ms,
            "skipped_embedding_calls": self._skipped_embedding,
            "dirty": self._dirty,
        }


vector_store = VectorStore()
