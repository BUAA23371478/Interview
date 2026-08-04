"""
全局配置：pydantic-settings 读取 .env 环境变量。

MAOO 平台适配：
- PORT       平台自动注入容器监听端口（9000-9999）
- BASE_URL   平台访问前缀，如 /app/interview-agent/
- MYSQL_*    平台可选注入 MySQL 连接（不提供则使用本地 SQLite）
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/ 目录（.env 放在 backend/.env）
APP_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = APP_DIR.parent
ENV_FILE = BACKEND_DIR / ".env"


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

    # ---- Embedding（OpenAI 兼容 /embeddings）----
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_api_key: str = ""

    # ---- 数据库（未配置 MySQL 时使用 SQLite）----
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "interview_agent"
    mysql_password: str = ""
    mysql_database: str = "interview_agent"
    # SQLite 数据库文件路径
    sqlite_path: str = str(BACKEND_DIR / "data" / "interview.db")

    @property
    def database_url(self) -> str:
        """优先使用平台注入的 MySQL，否则回退 SQLite。"""
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
    # 管理员角色（平台角色命中其一即可）
    admin_roles: tuple = ("admin", "developer")

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
