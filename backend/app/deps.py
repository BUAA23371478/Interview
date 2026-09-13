"""
MAOO 平台用户依赖。

平台 Nginx 验证 JWT 后注入请求头：
    X-Maoo-User-Id / X-Maoo-Username / X-Maoo-User-Role / X-Maoo-App-Slug

本地开发（无这些头）时回退到 settings 中的 dev 用户。

LLM BYOK：前端可通过 X-LLM-Key 请求头携带用户自己的 LLM API Key，
deps 将其注入请求级 contextvar，LLM 客户端每次调用优先使用。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException

from app.config import settings
from app.llm import set_llm_key_context, set_llm_model_context


@dataclass
class MaooUser:
    user_id: int
    username: str
    role: str
    level: str = "normal"

    @property
    def is_admin(self) -> bool:
        return self.role in settings.admin_roles


async def get_current_user(
    x_maoo_user_id: Optional[str] = Header(default=None),
    x_maoo_username: Optional[str] = Header(default=None),
    x_maoo_user_role: Optional[str] = Header(default=None),
) -> Optional[MaooUser]:
    """读取平台注入的用户身份。

    - 生产（debug=False）：只认 X-Maoo-* 请求头，无头则未登录（401）
    - 本地开发（debug=True）：无平台头时回退到 settings 的 dev 用户
    """
    if x_maoo_user_id:
        try:
            uid = int(x_maoo_user_id)
        except ValueError:
            return None
        return MaooUser(
            user_id=uid,
            username=x_maoo_username or "",
            role=x_maoo_user_role or "user",
        )
    if settings.debug:
        # 本地开发兜底：方便不带平台头直接测试全流程
        return MaooUser(
            user_id=settings.dev_user_id,
            username=settings.dev_username,
            role=settings.dev_role,
        )
    return None


async def require_login(
    user: Optional[MaooUser] = Depends(get_current_user),
    x_llm_key: Optional[str] = Header(default=None),
    x_llm_model: Optional[str] = Header(default=None),
) -> MaooUser:
    """登录依赖：注入请求级 LLM 凭据与模型偏好。

    - `X-LLM-Key`：用户自带 API Key（BYOK）
    - `X-LLM-Model`：用户首选模型；留空则由网关按任务自动路由。
      未在注册表中的模型名会被忽略并回落任务策略（用户填错不会导致整场不可用）。
    """
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    set_llm_key_context(x_llm_key)
    set_llm_model_context(x_llm_model)
    return user


async def require_admin(
    user: Optional[MaooUser] = Depends(get_current_user),
    x_llm_key: Optional[str] = Header(default=None),
    x_llm_model: Optional[str] = Header(default=None),
) -> MaooUser:
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    set_llm_key_context(x_llm_key)
    set_llm_model_context(x_llm_model)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
