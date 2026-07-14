from backend.repositories.interview_repo import InterviewRepo
from backend.repositories.practice_repo import PracticeRepo


class HistoryService:
    def __init__(self, db) -> None:
        self.practice_repo = PracticeRepo(db)
        self.interview_repo = InterviewRepo(db)

    async def practice_history(self, user_id: int, page: int = 1, limit: int = 20) -> dict:
        sessions, total = await self.practice_repo.get_user_sessions(user_id, page=page, limit=limit)
        return {
            "records": [
                {
                    "sessionId": session.id,
                    "topic": session.topic,
                    "status": session.status,
                    "totalQuestions": session.total_questions,
                    "totalCorrect": session.total_correct,
                    "accuracy": round((session.total_correct / session.total_questions) * 100, 2)
                    if session.total_questions
                    else 0,
                    "createdAt": session.created_at,
                }
                for session in sessions
            ],
            "total": total,
            "page": page,
            "limit": limit,
        }

    async def practice_stats(self, user_id: int) -> dict:
        stats = await self.practice_repo.get_user_stats(user_id)
        return {
            "totalQuestions": stats.get("total_questions", 0),
            "totalCorrect": stats.get("total_correct", 0),
            "overallAccuracy": stats.get("overall_accuracy", 0),
            "weakTopics": stats.get("weak_topics", []),
        }

    async def practice_detail(self, session_id: int, user_id: int) -> dict:
        session = await self.practice_repo.get_session(session_id)
        if session is None or session.user_id != user_id:
            return {}

        records = await self.practice_repo.get_records_by_session(session_id)
        return {
            "session": {
                "id": str(session.id),
                "topic": session.topic,
                "status": session.status,
                "difficultyLevel": session.difficulty_level,
                "maxQuestions": session.max_questions or 20,
                "totalQuestions": session.total_questions,
                "totalCorrect": session.total_correct,
                "createdAt": session.created_at,
            },
            "records": [
                {
                    "id": str(record.id),
                    "sessionId": str(record.session_id),
                    "questionNumber": record.question_number,
                    "question": record.question,
                    "questionType": record.question_type,
                    "referenceAnswer": record.reference_answer,
                    "userAnswer": record.user_answer,
                    "score": record.score,
                    "isCorrect": record.is_correct,
                    "feedback": record.feedback,
                    "knowledgePoints": record.knowledge_points,
                    "timeSpentSeconds": record.time_spent_seconds,
                    "createdAt": record.created_at,
                }
                for record in records
            ],
        }

    async def interview_history(self, user_id: int, page: int = 1, limit: int = 20) -> dict:
        sessions, total = await self.interview_repo.get_user_sessions(user_id, page=page, limit=limit)
        return {
            "records": [
                {
                    "sessionId": session.id,
                    "jdContent": session.jd_content,
                    "resumeContent": session.resume_content,
                    "status": session.status,
                    "totalRounds": session.total_rounds,
                    "completedRounds": session.completed_rounds,
                    "overallScore": session.overall_score,
                    "createdAt": session.created_at,
                }
                for session in sessions
            ],
            "total": total,
            "page": page,
            "limit": limit,
        }

    async def interview_detail(self, session_id: int, user_id: int) -> dict:
        session = await self.interview_repo.get_session(session_id)
        if session is None or session.user_id != user_id:
            return {}
        qa_records = await self.interview_repo.get_qa_records(session_id)
        return {
            "session": {
                "id": str(session.id),
                "jdContent": session.jd_content,
                "resumeContent": session.resume_content,
                "totalRounds": session.total_rounds,
                "completedRounds": session.completed_rounds,
                "overallScore": session.overall_score,
                "status": session.status,
                "createdAt": session.created_at,
            },
            "qaRecords": [
                {
                    "id": str(qa.id),
                    "roundNumber": qa.round_number,
                    "isFollowUp": qa.is_follow_up,
                    "question": qa.question,
                    "userAnswer": qa.user_answer,
                    "aiFeedback": qa.ai_feedback,
                    "createdAt": qa.created_at,
                }
                for qa in qa_records
            ],
            "report": session.report_content,
        }
