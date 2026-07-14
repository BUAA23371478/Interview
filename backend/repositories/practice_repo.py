from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.practice import PracticeRecord, PracticeSession
from backend.repositories.base import BaseRepository


class PracticeRepo(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def create_session(self, user_id: int, topic: str, difficulty_level: int, max_questions: int = 20) -> PracticeSession:
        session = PracticeSession(user_id=user_id, topic=topic, difficulty_level=difficulty_level, max_questions=max_questions)
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_session(self, session_id: int) -> PracticeSession | None:
        result = await self.db.execute(select(PracticeSession).where(PracticeSession.id == session_id))
        return result.scalar_one_or_none()

    async def create_record(self, **kwargs) -> PracticeRecord:
        record = PracticeRecord(**kwargs)
        self.db.add(record)
        await self.db.flush()
        return record

    async def create_pending_record(self, session_id: int, question_number: int, question: str, question_type: str, reference_answer: str, knowledge_points: list) -> PracticeRecord:
        """出题时立即创建一条待答记录（user_answer 为空）。"""
        record = PracticeRecord(
            session_id=session_id,
            question_number=question_number,
            question=question,
            question_type=question_type,
            reference_answer=reference_answer,
            user_answer="",
            score=0.0,
            is_correct=False,
            feedback="",
            knowledge_points=knowledge_points,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def update_record_answer(self, record_id: int, user_answer: str, score: float, is_correct: bool, feedback: str, time_spent_seconds: int | None) -> None:
        """更新已提交答案的记录。"""
        result = await self.db.execute(select(PracticeRecord).where(PracticeRecord.id == record_id))
        record = result.scalar_one_or_none()
        if record is None:
            return
        record.user_answer = user_answer
        record.score = score
        record.is_correct = is_correct
        record.feedback = feedback
        record.time_spent_seconds = time_spent_seconds
        await self.db.flush()

    async def get_pending_record(self, session_id: int) -> PracticeRecord | None:
        """获取会话中最近一条未答记录。"""
        result = await self.db.execute(
            select(PracticeRecord)
            .where(PracticeRecord.session_id == session_id, PracticeRecord.user_answer == "")
            .order_by(PracticeRecord.question_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_records_by_session(self, session_id: int) -> list[PracticeRecord]:
        result = await self.db.execute(
            select(PracticeRecord).where(PracticeRecord.session_id == session_id).order_by(PracticeRecord.question_number)
        )
        return list(result.scalars().all())

    async def update_session_stats(self, session_id: int, **kwargs) -> None:
        session = await self.get_session(session_id)
        if session is None:
            return
        for key, value in kwargs.items():
            setattr(session, key, value)

    async def get_user_sessions(self, user_id: int, page: int = 1, limit: int = 20) -> tuple[list[PracticeSession], int]:
        count_result = await self.db.execute(select(func.count()).select_from(PracticeSession).where(PracticeSession.user_id == user_id))
        total = int(count_result.scalar() or 0)

        result = await self.db.execute(
            select(PracticeSession)
            .where(PracticeSession.user_id == user_id)
            .order_by(PracticeSession.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_user_stats(self, user_id: int) -> dict:
        result = await self.db.execute(select(PracticeSession).where(PracticeSession.user_id == user_id))
        sessions = list(result.scalars().all())

        total_questions = sum(session.total_questions for session in sessions)
        total_correct = sum(session.total_correct for session in sessions)
        overall_accuracy = (total_correct / total_questions) if total_questions else 0

        weak_topics: list[dict] = []
        for session in sessions:
            if session.total_questions > 0:
                accuracy = session.total_correct / session.total_questions
                if accuracy < 0.6:
                    weak_topics.append(
                        {
                            "topic": session.topic,
                            "accuracy": round(accuracy * 100, 2),
                            "total_questions": session.total_questions,
                        }
                    )

        return {
            "total_questions": total_questions,
            "total_correct": total_correct,
            "overall_accuracy": round(overall_accuracy * 100, 2),
            "weak_topics": weak_topics,
        }

    async def delete_session(self, session_id: int, user_id: int) -> bool:
        session = await self.get_session(session_id)
        if session is None or session.user_id != user_id:
            return False
        await self.db.delete(session)
        await self.db.flush()
        return True
