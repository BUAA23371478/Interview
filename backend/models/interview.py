from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.connection import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    jd_content: Mapped[str] = mapped_column(String(5000), nullable=False)
    resume_content: Mapped[str] = mapped_column(String(5000), nullable=False)
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_rounds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="interview_sessions")
    qa_records = relationship(
        "InterviewQA",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewQA.round_number, InterviewQA.id",
    )


class InterviewQA(Base):
    __tablename__ = "interview_qa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_follow_up: Mapped[bool] = mapped_column(Boolean, default=False)
    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    user_answer: Mapped[str | None] = mapped_column(String(3000), nullable=True)
    ai_feedback: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session = relationship("InterviewSession", back_populates="qa_records")
