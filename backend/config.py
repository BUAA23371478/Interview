import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 计算 backend 目录下的 .env 绝对路径，不受 CWD 影响
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_BACKEND_DIR, ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.deepseek.com/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="deepseek-chat", alias="LLM_MODEL")
    llm_long_context_model: str = Field(default="deepseek-chat", alias="LLM_LONG_CONTEXT_MODEL")

    # Embedding 独立配置（Chat 和 Embedding 通常是两个不同服务）
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_base_url: str = Field(default="https://api.siliconflow.cn/v1", alias="EMBEDDING_BASE_URL")
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")

    database_url: str = Field(default="sqlite+aiosqlite:///./data/interview.db", alias="DATABASE_URL")

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    debug: bool = Field(default=True, alias="DEBUG")

    default_difficulty: int = 3
    default_interview_rounds: int = 10
    max_interview_rounds: int = 20
    min_interview_rounds: int = 3
    max_follow_ups_per_round: int = 2
    max_topic_length: int = 50

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"],
        alias="CORS_ORIGINS",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
