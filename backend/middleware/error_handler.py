from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger


class AppException(Exception):
    """业务异常基类。"""

    def __init__(self, status_code: int, message: str, code: str = "ERROR") -> None:
        self.status_code = status_code
        self.message = message
        self.code = code


class TopicValidationError(AppException):
    """主题校验失败。"""

    def __init__(self, message: str) -> None:
        super().__init__(400, message, "INVALID_TOPIC")


class SessionNotFoundError(AppException):
    """会话不存在。"""

    def __init__(self) -> None:
        super().__init__(404, "会话不存在", "SESSION_NOT_FOUND")


class LLMError(AppException):
    """LLM 服务异常。"""

    def __init__(self, message: str = "AI 服务异常，请稍后重试") -> None:
        super().__init__(503, message, "LLM_ERROR")


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        f"业务异常 [{exc.code}] {exc.message} "
        f"status={exc.status_code} path={request.url.path}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"未处理的异常 path={request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "服务器内部错误"},
    )
