from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.config import settings
from backend.database.migrations import init_db
from backend.llm.client import UnifiedLLMClient
from backend.middleware.error_handler import AppException, app_exception_handler, global_exception_handler
from backend.routers import history, interview, practice, user


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("正在初始化数据库表...")
    await init_db()
    logger.info("数据库初始化完成，服务已就绪")
    yield
    logger.info("服务正在关闭...")


app = FastAPI(title="AI 智能刷题与模拟面试系统", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user.router)
app.include_router(practice.router)
app.include_router(interview.router)
app.include_router(history.router)

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/api/llm/test")
async def test_llm_connection() -> dict:
    """测试 LLM API 连通性。"""
    client = UnifiedLLMClient()
    return await client.test_connection()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=settings.debug)
