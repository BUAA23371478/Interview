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
os.environ["TEST_MODE"] = "1"  # 测试模式：未配 key 时 LLM 走确定性 mock


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

