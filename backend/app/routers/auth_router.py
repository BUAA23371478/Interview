"""
认证 / 用户画像路由。

用户身份来自平台注入的 X-Maoo-* 请求头；业务侧维护等级与画像。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select

from app.database import get_db
from app.deps import MaooUser, get_current_user, require_login
from app.llm import llm_client
from app.memory import long_term
from app.models import User
from app.schemas import ProfileData, ProfileUpdate, UserInfo

router = APIRouter(prefix="/auth", tags=["认证与用户"])


@router.get("/me", response_model=UserInfo)
async def me(user: Optional[MaooUser] = Depends(get_current_user)) -> UserInfo:
    """当前平台用户信息（读请求头）。"""
    if user is None:
        return UserInfo(
            maoo_user_id=0, username="anonymous", role="guest",
            level="normal", is_admin=False,
        )
    return UserInfo(
        maoo_user_id=user.user_id, username=user.username, role=user.role,
        level=user.level, is_admin=user.is_admin,
    )


@router.get("/level", response_model=dict)
async def get_level(user: MaooUser = Depends(require_login)) -> dict:
    """获取业务等级（normal/vip/admin）。"""
    async for db in get_db():
        u = await long_term.get_or_create_user(db, user.user_id, user.username, user.role)
        return {"maoo_user_id": user.user_id, "level": u.level, "role": u.role}


@router.post("/test-llm")
async def test_llm(api_key: str = Body(..., embed=True)) -> dict:
    """测试用户提供的 LLM API Key 连通性（前端模型设置用）。"""
    if not api_key:
        raise HTTPException(status_code=400, detail="请填写 API Key")
    return await llm_client.test_connection(api_key=api_key)


@router.get("/profile", response_model=ProfileData)
async def get_profile(user: MaooUser = Depends(require_login)) -> ProfileData:
    data = await long_term.get_profile(user.user_id) or {}
    return ProfileData(**data)


@router.put("/profile", response_model=ProfileData)
async def update_profile(body: ProfileUpdate,
                         user: MaooUser = Depends(require_login)) -> ProfileData:
    fields = {}
    if body.tech_strengths is not None:
        fields["tech_strengths"] = body.tech_strengths
    if body.radar_scores is not None:
        fields["radar_scores"] = body.radar_scores
    data = await long_term.update_profile(user.user_id, **fields) or {}
    return ProfileData(**data)


@router.get("/wrong-book")
async def get_wrong_book(user: MaooUser = Depends(require_login)) -> dict:
    """完整错题本（含题目/回答/参考答案/笔记，供详情查看）。"""
    items = await long_term.list_wrong_answers(user.user_id)
    return {"ok": True, "total": len(items), "items": items}
