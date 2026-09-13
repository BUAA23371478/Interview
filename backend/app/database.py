"""
数据库层：async SQLAlchemy 2.0。

- 默认 SQLite（WAL + busy_timeout，零依赖）
- 配置 MYSQL_HOST 环境变量时切换 MySQL（asyncmy 驱动）
"""
from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


def _build_engine():
    url = settings.effective_database_url
    if url.startswith("sqlite"):
        Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(url, connect_args={"check_same_thread": False})
        # WAL 模式 + busy_timeout，解决并发写锁问题
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    else:
        # asyncmy 池调优：面向百人并发 / 万人容量
        # pool_size=20 是稳态连接数；max_overflow=40 允许突发；pool_recycle=3600 防 MySQL wait_timeout
        engine = create_async_engine(
            url,
            pool_size=20,
            max_overflow=40,
            pool_recycle=3600,
            pool_pre_ping=True,
            pool_timeout=30,
            echo=False,
        )
    return engine


engine = _build_engine()
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """建表（幂等）。"""
    import app.models  # noqa: F401  确保模型已注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from loguru import logger
    logger.info("数据库初始化完成")
