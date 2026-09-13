"""Pydantic API 请求/响应模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── 通用 ──────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    llm: str = "real"  # real / mock
    embedding: str = "real"  # real / mock


# ── 认证 / 用户画像 ───────────────────────────────────────────────────

class UserInfo(BaseModel):
    maoo_user_id: int
    username: str
    role: str
    level: str
    is_admin: bool


class ProfileData(BaseModel):
    maoo_user_id: int
    total_interviews: int = 0
    total_practices: int = 0
    avg_score: float = 0.0
    persistent_weaknesses: List[str] = Field(default_factory=list)
    tech_strengths: List[str] = Field(default_factory=list)
    radar_scores: Dict[str, float] = Field(default_factory=dict)
    wrong_book: List[Dict[str, Any]] = Field(default_factory=list)
    learning_footprint: List[Dict[str, Any]] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    tech_strengths: Optional[List[str]] = None
    radar_scores: Optional[Dict[str, float]] = None


# ── 知识库 ────────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: int
    maoo_user_id: int
    filename: str
    title: str
    category: str
    file_type: str
    file_size: int
    char_count: int
    status: str
    is_seed: bool
    review_note: str
    chunk_count: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    ok: bool = True
    total: int
    page: int
    limit: int
    items: List[DocumentOut]


class CategoryResponse(BaseModel):
    ok: bool = True
    categories: List[str]


class SearchHit(BaseModel):
    id: str
    content: str
    doc_title: str = ""
    category: str = ""
    score: float = 0.0


class SearchResponse(BaseModel):
    ok: bool = True
    query: str
    total: int
    items: List[SearchHit]


class UploadResponse(BaseModel):
    ok: bool = True
    doc_id: Optional[int] = None
    filename: str
    status: str = "pending"  # pending / rejected
    message: str = ""
    ai_precheck: Optional[Dict[str, Any]] = None


class ReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    note: str = ""


class ReviewLogOut(BaseModel):
    action: str
    reviewer_role: str
    reviewer_id: int
    note: str
    ai_precheck: Dict[str, Any]
    created_at: Optional[datetime] = None


class ReviewItemOut(DocumentOut):
    review_logs: List[ReviewLogOut] = Field(default_factory=list)
    ai_precheck: Optional[Dict[str, Any]] = None


# ── 面试 ──────────────────────────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    jd_text: str = Field(..., min_length=1)
    resume_text: str = ""
    total_rounds: int = Field(default=10, ge=1, le=20)
    difficulty: str = "medium"


class InterviewAnswerRequest(BaseModel):
    session_id: str
    answer: str = Field(..., min_length=1)


class InterviewStartResponse(BaseModel):
    session_id: str
    question: str
    question_index: int = 0
    total_rounds: int
    difficulty: str
    jd_title: str = ""
    # 可观测性：本次请求各阶段耗时/token/成本
    trace: Optional[Dict[str, Any]] = None
    # 计费：本次请求实际消耗与余额
    credits: Optional[Dict[str, Any]] = None


class InterviewAnswerResponse(BaseModel):
    session_id: str
    interview_finished: bool = False
    should_followup: bool = False
    question: str = ""
    question_index: int = 0
    total_rounds: int
    difficulty: str
    score: Optional[float] = None
    final_report: Optional[Dict[str, Any]] = None
    study_plan: Optional[Dict[str, Any]] = None
    trace: Optional[Dict[str, Any]] = None
    credits: Optional[Dict[str, Any]] = None


class ReportResponse(BaseModel):
    session_id: str
    mode: str
    final_report: Dict[str, Any]
    study_plan: Optional[Dict[str, Any]] = None


# ── 模型与计费 ────────────────────────────────────────────────────────

class RechargeRequest(BaseModel):
    credits: int = Field(..., gt=0, description="充值积分数量")
    order_id: str = Field(default="", description="支付渠道订单号；留空则由服务端生成（占位语义）")
    note: str = ""


# ── 练习 ──────────────────────────────────────────────────────────────

class PracticeStartRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    difficulty: str = "medium"
    company_style: str = "通用"
    total_rounds: int = Field(default=10, ge=1, le=20)


class PracticeStartResponse(BaseModel):
    session_id: str
    question: str
    question_index: int = 0
    total_rounds: int
    difficulty: str
    topic: str
    rag_hit: bool = True  # 知识库是否命中该主题资料


class PracticeAnswerRequest(BaseModel):
    session_id: str
    answer: str = Field(..., min_length=1)


class PracticeAnswerResponse(BaseModel):
    session_id: str
    finished: bool = False
    score: float = 0.0
    is_correct: bool = False
    feedback: str = ""
    reference: str = ""
    question: str = ""
    question_index: int = 0
    total_rounds: int
    difficulty: str
    wrong_book_prompt: bool = False
    report: Optional[Dict[str, Any]] = None


class HistoryItem(BaseModel):
    session_id: str
    mode: str
    status: str
    created_at: Optional[datetime] = None
    summary: Dict[str, Any] = Field(default_factory=dict)


class HistoryResponse(BaseModel):
    ok: bool = True
    items: List[HistoryItem]
