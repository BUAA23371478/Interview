from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.interview import InterviewQA, InterviewSession
from backend.repositories.base import BaseRepository


class InterviewRepo(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def create_session(self, user_id: int, jd_content: str, resume_content: str, total_rounds: int) -> InterviewSession:
        session = InterviewSession(
            user_id=user_id,
            jd_content=jd_content,
            resume_content=resume_content,
            total_rounds=total_rounds,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_session(self, session_id: int) -> InterviewSession | None:
        result = await self.db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
        return result.scalar_one_or_none()

    async def create_qa(self, **kwargs) -> InterviewQA:
        qa = InterviewQA(**kwargs)
        self.db.add(qa)
        await self.db.flush()
        return qa

    async def save_report(self, session_id: int, report: dict) -> None:
        session = await self.get_session(session_id)
        if session is None:
            return
        session.report_content = report
        session.overall_score = int(report.get("overall_score", 0))
        session.status = "completed"

    async def get_user_sessions(self, user_id: int, page: int = 1, limit: int = 20) -> tuple[list[InterviewSession], int]:
        count_result = await self.db.execute(select(func.count()).select_from(InterviewSession).where(InterviewSession.user_id == user_id))
        total = int(count_result.scalar() or 0)

        result = await self.db.execute(
            select(InterviewSession)
            .where(InterviewSession.user_id == user_id)
            .order_by(InterviewSession.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def update_session_progress(self, session_id: int, completed_rounds: int, status: str) -> None:
        """更新面试会话的进度和状态。"""
        session = await self.get_session(session_id)
        if session is None:
            return
        session.completed_rounds = completed_rounds
        session.status = status

    async def get_qa_records(self, session_id: int) -> list[InterviewQA]:
        result = await self.db.execute(select(InterviewQA).where(InterviewQA.session_id == session_id).order_by(InterviewQA.round_number, InterviewQA.id))
        return list(result.scalars().all())

    async def delete_session(self, session_id: int, user_id: int) -> bool:
        session = await self.get_session(session_id)
        if session is None or session.user_id != user_id:
            return False
        await self.db.delete(session)
        await self.db.flush()
        return True
