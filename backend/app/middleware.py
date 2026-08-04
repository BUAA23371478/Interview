"""
请求中间件：CORS 与统一错误处理。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.llm import LLMError


def add_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class AppException(Exception):
    """业务异常：带 HTTP 状态码与错误码。"""

    def __init__(self, status_code: int, message: str, code: str = "APP_ERROR") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        from loguru import logger
        logger.exception("未处理异常: {}", exc)
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "服务器内部错误"},
        )

    @app.exception_handler(LLMError)
    async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(
            status_code=400,
            content={"code": "LLM_NO_KEY_OR_ERROR", "message": exc.message},
        )


def error_payload(status_code: int, message: str, code: str = "APP_ERROR") -> Dict[str, Any]:
    return {"code": code, "message": message}
