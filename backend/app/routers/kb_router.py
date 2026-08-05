"""
知识库路由：浏览 / 分类 / 检索 / 上传（UGC + 审核）/ 审核管理。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query

from app.deps import MaooUser, get_current_user, require_admin, require_login
from app.schemas import (CategoryResponse, DocumentListResponse,
                         ReviewRequest, SearchResponse, UploadResponse)
from app.services import kb_service

router = APIRouter(prefix="/kb", tags=["知识库"])


@router.get("/categories", response_model=CategoryResponse)
async def categories(user: Optional[MaooUser] = Depends(get_current_user)) -> CategoryResponse:
    cats = await kb_service.list_categories(user or _guest())
    return CategoryResponse(categories=cats)


@router.get("/docs", response_model=DocumentListResponse)
async def list_docs(
    page: int = 1,
    limit: int = Query(default=50, le=200),
    status: Optional[str] = None,
    category: Optional[str] = None,
    mine: bool = False,
    user: Optional[MaooUser] = Depends(get_current_user),
) -> DocumentListResponse:
    data = await kb_service.list_documents(user or _guest(), page, limit, status, category, mine)
    return DocumentListResponse(**data)


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    top_k: int = Query(default=5, le=20),
    category: Optional[str] = None,
    user: Optional[MaooUser] = Depends(get_current_user),
) -> SearchResponse:
    hits = await kb_service.search_documents(q, top_k=top_k, category=category, user=user)
    return SearchResponse(query=q, total=len(hits), items=hits)


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(default=""),
    title: str = Form(default=""),
    user: MaooUser = Depends(require_login),
) -> UploadResponse:
    """用户上传技术文档/面经 → AI 预审 → pending 待管理员复核。"""
    result = await kb_service.upload_document(user, file, category, title)
    return UploadResponse(
        ok=result["ok"], doc_id=result.get("doc_id"),
        filename=result["filename"], status=result.get("status", "pending"),
        message=result.get("message", ""), ai_precheck=result.get("ai_precheck"),
    )


@router.get("/pending")
async def list_pending(page: int = 1, limit: int = 50,
                       user: MaooUser = Depends(require_login)) -> dict:
    """待审队列（admin）。"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return await kb_service.list_pending(user, page, limit)


@router.post("/review/{doc_id}")
async def review_document(doc_id: int, body: ReviewRequest,
                          user: MaooUser = Depends(require_admin)) -> dict:
    """管理员审核：approve / reject。"""
    return await kb_service.review_document(user, doc_id, body.action, body.note)


@router.delete("/{doc_id}")
async def remove_document(doc_id: int,
                          user: MaooUser = Depends(require_login)) -> dict:
    """下架文档（admin 或本人）。"""
    return await kb_service.remove_document(user, doc_id)


def _guest() -> MaooUser:
    """未登录访客：只能浏览已上架内容。"""
    return MaooUser(user_id=0, username="guest", role="guest")
