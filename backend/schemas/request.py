from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)


class PracticeStartRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=50)
    max_questions: int = Field(default=20, ge=3, le=50)


class SubmitAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    time_spent_seconds: int | None = Field(default=None, ge=0)


class InterviewCreateRequest(BaseModel):
    jd: str = Field(min_length=1, max_length=5000)
    resume: str = Field(min_length=1, max_length=5000)
    total_rounds: int = Field(default=10, ge=3, le=20)


class SubmitInterviewAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
