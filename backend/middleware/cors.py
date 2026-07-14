from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings


def cors_middleware() -> tuple[type[CORSMiddleware], dict]:
    return CORSMiddleware, {
        "allow_origins": settings.cors_origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
