"""FastAPI 应用入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.config import settings
from app.database import init_db
from app.middleware import add_middleware, register_exception_handlers
from app.routers import (auth_router, billing_router, health, interview_router,
                         kb_router, practice_router)
from app.services.kb_service import ensure_seed_indexed


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    logger.info("初始化数据库...")
    await init_db()
    logger.info("初始化知识库索引...")
    try:
        await ensure_seed_indexed()
    except Exception as e:  # noqa: BLE001
        logger.warning("知识库索引初始化失败（可稍后手动构建）: {}", e)
    logger.info("{} 服务已就绪", settings.app_name)
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
add_middleware(app)
register_exception_handlers(app)

app.include_router(health.router)
app.include_router(auth_router.router)
app.include_router(kb_router.router)
app.include_router(billing_router.router)
app.include_router(interview_router.router)
app.include_router(practice_router.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
