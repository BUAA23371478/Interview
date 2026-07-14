from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    user_id: str = Field(alias="userId")
    username: str


class PracticeStartResponse(BaseModel):
    session_id: str = Field(alias="sessionId")


class InterviewCreateResponse(BaseModel):
    session_id: str = Field(alias="sessionId")


class PracticeStatsResponse(BaseModel):
    total_questions: int = Field(alias="totalQuestions")
    total_correct: int = Field(alias="totalCorrect")
    overall_accuracy: float = Field(alias="overallAccuracy")
    weak_topics: list[dict] = Field(alias="weakTopics")

    model_config = {
        "populate_by_name": True,
    }


class InterviewReportResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    report: dict
