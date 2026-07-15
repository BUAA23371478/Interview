"""Pytest 配置和共享 Fixtures。

与 PLAN.md 4.2 节一致：
- 内存 SQLite 测试数据库
- FastAPI TestClient（通过 httpx.AsyncClient）
- 依赖覆盖（get_db → 测试 DB）
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database.connection import Base, get_db
from backend.main import app


# ---------------------------------------------------------------------------
# 测试数据库 Fixture
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """创建内存 SQLite 引擎（每个测试独立）。"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """创建独立测试 DB 会话。"""
    test_session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with test_session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# HTTP 客户端 Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI TestClient（httpx AsyncClient）。"""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 辅助 Fixture：注册用户
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def auth_user(client: AsyncClient) -> dict[str, Any]:
    """注册一个测试用户并返回 user 信息。"""
    res = await client.post(
        "/api/user/register",
        json={"username": "testuser", "password": "test123456"},
    )
    assert res.status_code == 200
    data = res.json()
    return {"userId": data["userId"], "username": "testuser"}


@pytest_asyncio.fixture(scope="function")
async def auth_headers(auth_user: dict) -> dict[str, str]:
    """返回带 X-User-Id 的请求头。"""
    return {"X-User-Id": str(auth_user["userId"])}
