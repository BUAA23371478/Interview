"""pytest fixtures：使用隔离的临时数据库，避免污染开发数据。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# 保证 `pytest` 在 backend/ 目录下运行时能 import app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 在 import app 之前设置隔离数据库路径
_tmp_dir = tempfile.mkdtemp(prefix="interview_test_")
os.environ["SQLITE_PATH"] = os.path.join(_tmp_dir, "test.db")
os.environ["LLM_API_KEY"] = ""  # 不配 key
os.environ["EMBEDDING_API_KEY"] = ""
os.environ["RERANK_API_KEY"] = ""
# 多 provider 凭据也必须清空：本地 .env 里存着真实 key，
# 若不屏蔽，单测会真的去打外部付费 API（既花钱又让结论不可复现）。
os.environ["LLM_PROVIDER_KEYS"] = "{}"
os.environ["LLM_PROVIDER_BASE_URLS"] = "{}"
os.environ["TEST_MODE"] = "1"  # 测试模式：未配 key 时 LLM 走确定性 mock
# 成本流水写到临时目录 + 关闭真实调用路径
os.environ["LLM_BUDGET_LEDGER"] = os.path.join(_tmp_dir, "spend.json")
os.environ["LLM_BUDGET_YUAN"] = "0"
# 向量/精排缓存也隔离到临时目录，避免测试复用生产缓存导致结论失真
os.environ["EMBEDDING_CACHE_DB"] = os.path.join(_tmp_dir, "embed_cache.db")
# 业务阈值也必须隔离：本地 .env 为了评测放宽过配额，
# 不能让「放宽的本地配置」把配额类单测静默变成无效断言。
os.environ["KB_DAILY_UPLOAD_LIMIT"] = "5"
os.environ["KB_DAILY_CHAR_LIMIT"] = "200000"
os.environ["KB_AI_APPROVE_THRESHOLD"] = "60"


import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """每个会话开始时建表 + 种子索引。"""
    import asyncio
    from app.database import init_db
    from app.services.kb_service import ensure_seed_indexed

    async def _setup():
        await init_db()
        await ensure_seed_indexed()

    asyncio.run(_setup())
    yield


@pytest.fixture(autouse=True)
def _clean_users():
    """每个测试前清空非 seed 数据，避免配额/重复影响。"""
    import asyncio
    from app.database import SessionLocal
    from app.models import (CreditAccount, CreditLedger, Document, Report,
                            Session, WrongAnswer, UserProfile, User)

    async def _clean():
        async with SessionLocal() as session:
            from sqlalchemy import delete
            await session.execute(delete(Document).where(Document.is_seed == 0))
            await session.execute(delete(Report))
            await session.execute(delete(Session))
            await session.execute(delete(WrongAnswer))
            await session.execute(delete(UserProfile))
            await session.execute(delete(CreditLedger))
            await session.execute(delete(CreditAccount))
            await session.execute(delete(User))
            await session.commit()

    asyncio.run(_clean())
    yield

