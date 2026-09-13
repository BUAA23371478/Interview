"""定位向量索引中的异常值（inf / NaN / 超范围）。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
_tmp = tempfile.mkdtemp(prefix="vec_probe_")
os.environ["SQLITE_PATH"] = os.path.join(_tmp, "probe.db")
os.environ["LLM_API_KEY"] = ""
os.environ["EMBEDDING_API_KEY"] = ""
os.environ["TEST_MODE"] = "1"

import asyncio  # noqa: E402

import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.embedding import blob_dim, unpack_vector  # noqa: E402
from app.models import Vector  # noqa: E402
from app.rag.vector_store import VectorStore, _stack_vectors  # noqa: E402
from app.services.kb_service import ensure_seed_indexed  # noqa: E402


async def main() -> None:
    await init_db()
    await ensure_seed_indexed()
    async with SessionLocal() as s:
        rows = (await s.execute(select(Vector.id, Vector.doc_id, Vector.chunk_index,
                                       Vector.embedding))).all()
    print(f"total_rows={len(rows)}")
    if not rows:
        print("no_rows")
        return
    dims = {}
    for r in rows:
        dims[blob_dim(r[3])] = dims.get(blob_dim(r[3]), 0) + 1
    print(f"dims={dims}")
    dim = max(dims, key=dims.get)
    keep = [r for r in rows if blob_dim(r[3]) == dim]
    mat = _stack_vectors([r[3] for r in keep], dim)
    print(f"dim={dim} shape={mat.shape} dtype={mat.dtype}")
    print(f"absmax={float(np.max(np.abs(mat))):.6g}")
    print(f"nan={int(np.isnan(mat).sum())} inf={int(np.isinf(mat).sum())}")
    # 逐条定位异常向量
    bad = 0
    for r in keep:
        v = np.asarray(unpack_vector(r[3]), dtype=np.float64)
        m = float(np.max(np.abs(v)))
        if m > 1e3 or not np.isfinite(m):
            bad += 1
            if bad <= 5:
                print(f"  BAD db_id={r[0]} doc={r[1]} chunk={r[2]} absmax={m:.6g}")
    print(f"bad_vectors={bad}")
    # 真实搜索路径
    vs = VectorStore()
    await vs.reload()
    hits = await vs.search("Redis 分布式锁", top_k=3)
    print(f"hits={len(hits)} last_query_ms={vs._last_query_ms}")
    for h in hits:
        print(f"  {h['id']} score={h['score']}")


asyncio.run(main())
