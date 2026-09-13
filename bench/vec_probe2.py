"""逐行对比 _stack_vectors 与 unpack_vector，定位 NaN 来源。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
_tmp = tempfile.mkdtemp(prefix="vec_probe2_")
os.environ["SQLITE_PATH"] = os.path.join(_tmp, "probe.db")
os.environ["LLM_API_KEY"] = ""
os.environ["EMBEDDING_API_KEY"] = ""
os.environ["TEST_MODE"] = "1"

import asyncio  # noqa: E402

import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.embedding import MAGIC_F32, MAGIC_F64, blob_dim, unpack_vector  # noqa: E402
from app.models import Vector  # noqa: E402
from app.rag.vector_store import _stack_vectors  # noqa: E402
from app.services.kb_service import ensure_seed_indexed  # noqa: E402


async def main() -> None:
    await init_db()
    await ensure_seed_indexed()
    async with SessionLocal() as s:
        rows = (await s.execute(select(Vector.id, Vector.embedding))).all()

    lens, types, magics = {}, {}, {}
    for r in rows:
        b = r[1]
        lens[len(b)] = lens.get(len(b), 0) + 1
        types[type(b).__name__] = types.get(type(b).__name__, 0) + 1
        m = "F32" if b[:4] == MAGIC_F32 else ("F64" if b[:4] == MAGIC_F64 else "raw")
        magics[m] = magics.get(m, 0) + 1
    print(f"rows={len(rows)}")
    print(f"len_dist={sorted(lens.items())[:6]}")
    print(f"py_types={types}")
    print(f"magic_dist={magics}")

    blobs = [r[1] for r in rows]
    dim = blob_dim(blobs[0])
    print(f"dim={dim} first_len={len(blobs[0])}")

    print(f"blob[:4]={blobs[0][:4]!r} MAGIC_F32={MAGIC_F32!r} eq={blobs[0][:4] == MAGIC_F32}")

    mat = _stack_vectors(blobs, dim)
    stack_nan = int(np.isnan(mat).sum())

    unpack_nan = 0
    for b in blobs:
        v = np.asarray(unpack_vector(b), dtype=np.float64)
        if not np.all(np.isfinite(v)):
            unpack_nan += 1

    print(f"stack_nan_cells={stack_nan} unpack_nan_rows={unpack_nan}")

    # 对第一行做精细解剖
    b0 = blobs[0]
    v_struct = np.asarray(unpack_vector(b0), dtype=np.float64)
    v_np = np.frombuffer(b0, dtype=np.float32, count=dim, offset=4).astype(np.float64)
    print(f"row0 struct_absmax={float(np.max(np.abs(v_struct))):.6g} "
          f"nan={int(np.isnan(v_struct).sum())}")
    print(f"row0 npbuf_absmax={float(np.max(np.abs(v_np))):.6g} "
          f"nan={int(np.isnan(v_np).sum())}")

    # 统计：有多少行 np.frombuffer 结果含 NaN
    bad_rows = 0
    for b in blobs:
        v = np.frombuffer(b, dtype=np.float32, count=dim, offset=4)
        if not np.all(np.isfinite(v)):
            bad_rows += 1
    print(f"npbuf_bad_rows={bad_rows}")


asyncio.run(main())
