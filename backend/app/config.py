"""
全局配置：pydantic-settings 读取 .env 环境变量。

MAOO 平台适配：
- PORT       平台自动注入容器监听端口（9000-9999）
- BASE_URL   平台访问前缀，如 /app/interview-agent/
- DATABASE_URL / DB_*   平台托管数据库（v1.0.8+ 自动创建模式）
- MYSQL_*    外部数据库模式（兼容 v1.0.2）
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/config.py -> backend/ 目录（.env 放在 backend/.env）
APP_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = APP_DIR.parent
ENV_FILE = BACKEND_DIR / ".env"


def _to_async_url(url: str) -> str:
    """把平台注入的普通连接串（mysql:// 或 postgres://）转成 SQLAlchemy 异步驱动 URL。

    平台自动创建模式注入的 DATABASE_URL 形如：
        mysql://user_xxx:pwd@db-xxx:3306/app_xxx
    转换为：
        mysql+asyncmy://user_xxx:pwd@db-xxx:3306/app_xxx?charset=utf8mb4
    """
    url = url.strip()
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+asyncmy://", 1)
        if "?" not in url:
            url += "?charset=utf8mb4"
        return url
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1).replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
    return url


class Settings(BaseSettings):
    """应用全局配置（自动从 .env / 环境变量加载）"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用 ----
    app_name: str = "AI 面试智能体"
    host: str = "127.0.0.1"                       # 生产只监听本机（平台反向代理）
    port: int = Field(default=8002, alias="PORT")
    base_url: str = "/app/interview-agent/"       # 平台访问前缀（静态资源用）
    debug: bool = False
    log_level: str = "INFO"
    # 测试模式：仅 pytest 使用，未配 key 时走 MockLLM（生产/本地永不开启）
    test_mode: bool = False

    # 本地开发兜底用户（无 X-Maoo-* 请求头时使用，生产必须通过平台注入）
    dev_user_id: int = 1
    dev_username: str = "dev_user"
    dev_role: str = "developer"

    # ---- LLM（OpenAI 兼容）----
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_api_key: str = ""
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_json_temperature: float = 0.2
    # DeepSeek Responses API 模式（deepseek-v4-flash）：true 走 responses.create
    # base_url 无 /v1 后缀（https://api.deepseek.com），model 用 deepseek-v4-flash
    llm_responses_mode: bool = False
    llm_responses_model: str = "deepseek-v4-flash"
    llm_responses_base_url: str = "https://api.deepseek.com"

    # ---- Embedding（OpenAI 兼容 /embeddings）----
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_api_key: str = ""

    # ---- 数据库（优先平台注入，其次 MySQL 外部，最后 SQLite）----
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "interview_agent"
    mysql_password: str = ""
    mysql_database: str = "interview_agent"
    # 平台托管数据库（v1.0.8+ 自动创建模式）注入的完整连接串
    database_url: str = ""
    # SQLite 数据库文件路径
    sqlite_path: str = str(BACKEND_DIR / "data" / "interview.db")

    @property
    def effective_database_url(self) -> str:
        """平台数据库连接串优先级：

        1. DATABASE_URL（平台自动创建模式注入的完整连接串）
        2. DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD（平台自动创建模式的组件变量）
        3. MYSQL_*（外部数据库模式）
        4. 无 → SQLite（本地开发/降级）
        """
        if self.database_url:
            # 平台注入的是普通 mysql:// 或 postgres://，转换为 SQLAlchemy 异步驱动
            return _to_async_url(self.database_url)
        if os.getenv("DB_HOST"):
            return (
                f"mysql+asyncmy://{os.getenv('DB_USER', '')}:{os.getenv('DB_PASSWORD', '')}"
                f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME', '')}"
                "?charset=utf8mb4"
            )
        if os.getenv("MYSQL_HOST"):
            return (
                f"mysql+asyncmy://{self.mysql_user}:{self.mysql_password}"
                f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
                "?charset=utf8mb4"
            )
        return f"sqlite+aiosqlite:///{self.sqlite_path}"

    # ---- 记忆 ----
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_short_term_ttl: int = 86400  # 短期会话 24h

    # ---- RAG ----
    rag_top_k: int = 5
    rag_vector_weight: float = 0.6
    rag_bm25_weight: float = 0.4
    rag_rrf_k: int = 60
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 100
    rag_max_pdf_pages: int = 200
    rag_max_upload_mb: int = 50
    rag_max_candidates_for_rerank: int = 20
    rag_use_rerank: bool = False

    # ---- 知识库审核 ----
    # AI 预审通过阈值（0-100）：>= 该值才推荐进入待人工复核
    kb_ai_approve_threshold: int = 60
    # 反刷：每人每日上传上限
    kb_daily_upload_limit: int = 5
    kb_daily_char_limit: int = 200_000
    # 管理员角色（平台角色命中其一即可），支持逗号分隔：admin_roles: tuple = ("admin", "developer")
    admin_roles: Annotated[List[str], NoDecode] = ["admin", "developer"]

    @field_validator("admin_roles", mode="before")
    @classmethod
    def _split_admin_roles(cls, v: object) -> object:
        """把 .env 里的逗号分隔字符串解析成列表。"""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, (list, tuple)):
            return list(v)
        return v

    # ---- 面试 / 练习 ----
    default_interview_rounds: int = 10
    max_interview_rounds: int = 20
    max_followups_per_round: int = 2
    consecutive_to_upgrade: int = 2   # 连对 N 题升级难度
    consecutive_to_downgrade: int = 2 # 连错 N 题降级难度
    default_difficulty: str = "medium"
    max_quiz_rounds: int = 20

    # ---- 目录 ----
    @property
    def data_dir(self) -> Path:
        p = BACKEND_DIR / "data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def upload_dir(self) -> Path:
        p = self.data_dir / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def kb_seed_dir(self) -> Path:
        p = self.data_dir / "kb_seed"
        return p

    @property
    def bm25_cache_path(self) -> Path:
        return self.data_dir / "bm25_corpus.pkl"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
