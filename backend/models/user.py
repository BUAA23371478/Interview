import hashlib
import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.connection import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    resume_content: Mapped[str] = mapped_column(String(5000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    practice_sessions = relationship("PracticeSession", back_populates="user", cascade="all, delete-orphan")
    interview_sessions = relationship("InterviewSession", back_populates="user", cascade="all, delete-orphan")

    @staticmethod
    def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
        """开发环境简写：SHA256 哈希，后续迭代可替换为 bcrypt。"""
        salt = salt or os.urandom(16).hex()
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        return h, salt

    def verify_password(self, password: str) -> bool:
        """验证密码（格式: salt:hash）。"""
        parts = self.password_hash.split(":", 1)
        if len(parts) != 2:
            return False
        salt, expected = parts
        h, _ = self.hash_password(password, salt)
        return h == expected
