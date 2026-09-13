"""
SQLAlchemy ORM 模型。

业务表以平台用户 ID（maoo_user_id）关联用户，不自建登录系统。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, DateTime, Float, ForeignKey, Integer, LargeBinary,
                        String, Text, UniqueConstraint)
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """应用内用户（对应 MAOO 平台用户）。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maoo_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(32), default="user")  # user / developer / admin
    level: Mapped[str] = mapped_column(String(20), default="normal")  # normal / vip / admin
    credits: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class UserProfile(Base):
    """用户画像（长期记忆核心）。"""
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maoo_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    total_interviews: Mapped[int] = mapped_column(Integer, default=0)
    total_practices: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)
    persistent_weaknesses: Mapped[list] = mapped_column(JSON, default=list)  # 跨会话薄弱点
    tech_strengths: Mapped[list] = mapped_column(JSON, default=list)
    radar_scores: Mapped[dict] = mapped_column(JSON, default=dict)  # 技能雷达 {维度: 分数}
    learning_footprint: Mapped[list] = mapped_column(JSON, default=list)  # 学习足迹 [{ts, action, detail}]
    wrong_book: Mapped[list] = mapped_column(JSON, default=list)  # 错题本


class Document(Base):
    """知识库文档（内置 + 用户 UGC）。"""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maoo_user_id: Mapped[int] = mapped_column(Integer, index=True, default=0)  # 0 = 内置 seed
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(64), default="未分类")
    file_type: Mapped[str] = mapped_column(String(16), default="md")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/approved/rejected/removed
    is_seed: Mapped[int] = mapped_column(Integer, default=0)
    review_note: Mapped[str] = mapped_column(Text, default="")
    review_by: Mapped[str] = mapped_column(String(64), default="")
    review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    original_hash: Mapped[str] = mapped_column(String(64), default="")
    content_text: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), default="")  # 内容快照（MySQL 用 MEDIUMTEXT 支持长文档）
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ReviewLog(Base):
    """审核日志（全程留痕）。"""
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(20), default="upload")  # upload/ai_precheck/approve/reject/remove
    reviewer_role: Mapped[str] = mapped_column(String(32), default="")
    reviewer_id: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    ai_precheck: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Session(Base):
    """面试/练习会话。"""
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    maoo_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="interview")  # interview/practice
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/completed
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Report(Base):
    """面试/练习复盘报告。"""
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maoo_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="interview")
    report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class WrongAnswer(Base):
    """错题记录。"""
    __tablename__ = "wrong_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maoo_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), default="")
    topic: Mapped[str] = mapped_column(String(64), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    reference: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reviewed: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Vector(Base):
    """向量索引（与业务数据同库，生产用 MySQL / 本地用 SQLite）。"""
    __tablename__ = "vectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), default="")
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), default="{}")


# ── 积分账户（统一计费）──────────────────────────────────────────────
class CreditAccount(Base):
    """用户积分账户。积分是唯一的资源计量单位，token 成本按汇率折算成积分。"""
    __tablename__ = "credit_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maoo_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    balance: Mapped[int] = mapped_column(Integer, default=0)          # 当前可用积分
    frozen: Mapped[int] = mapped_column(Integer, default=0)           # 进行中请求的预扣积分
    total_granted: Mapped[int] = mapped_column(Integer, default=0)    # 累计赠送
    total_recharged: Mapped[int] = mapped_column(Integer, default=0)  # 累计充值（占位，未接真实支付）
    total_consumed: Mapped[int] = mapped_column(Integer, default=0)   # 累计实际消耗
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CreditLedger(Base):
    """积分流水（记账唯一事实来源）。

    `(request_id, kind)` 唯一 —— 这就是**幂等键**：
    客户端/网关重试同一个 request_id 时，第二次插入直接冲突，
    不会重复扣费。预扣（pre）与结算（settle）各自一条流水，可完整复盘一笔请求。
    """
    __tablename__ = "credit_ledger"
    __table_args__ = (
        UniqueConstraint("request_id", "kind", name="uq_credit_ledger_request_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maoo_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="settle")  # pre/settle/release/recharge/grant
    amount: Mapped[int] = mapped_column(Integer, default=0)          # 负数=扣减，正数=入账
    balance_after: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(64), default="")
    task: Mapped[str] = mapped_column(String(32), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_yuan: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
