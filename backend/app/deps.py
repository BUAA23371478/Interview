"""
MAOO 平台用户依赖（v2 · 通过 PlatformAdapter 解耦）。

平台 Nginx 验证 JWT 后注入请求头：
    X-Maoo-User-Id / X-Maoo-Username / X-Maoo-User-Role

业务侧不直接读平台头——全部走 `app.platform.resolve_chain` 解析。
本地开发（debug=True）无平台头时回退 dev_user。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException

from app.config import settings
from app.llm import set_llm_model_context
from app.platform import ResolvedUser, resolve_chain


@dataclass
class MaooUser:
    """FastAPI 依赖层使用的业务侧用户对象。

    与 ResolvedUser 的差别：把平台侧的字段直接挂在 MaooUser 上便于路由参数使用。
    """
    user_id: int
    username: str
    role: str
    level: str = "normal"

    @property
    def is_admin(self) -> bool:
        return self.role in settings.admin_roles


def _to_business_user(r: ResolvedUser) -> MaooUser:
    return MaooUser(user_id=r.external_id, username=r.username, role=r.role)


async def get_current_user(
    x_maoo_user_id: Optional[str] = Header(default=None),
    x_maoo_username: Optional[str] = Header(default=None),
    x_maoo_user_role: Optional[str] = Header(default=None),
) -> Optional[MaooUser]:
    """读取平台注入的用户身份。

    - 生产（debug=False）：只认平台头部，无头则未登录（401）
    - 本地开发（debug=True）：无平台头时回退 settings.dev_user*

    业务侧关心的「当前用户是谁」与「哪个平台」解耦——未来换 SSO/Keycloak
    只需新增一个 PlatformAdapter，依赖层不动。
    """
    headers = {
        "x-maoo-user-id": x_maoo_user_id,
        "x-maoo-username": x_maoo_username,
        "x-maoo-user-role": x_maoo_user_role,
    }
    resolved = await resolve_chain(headers)
    if resolved is None:
        return None
    return _to_business_user(resolved)


async def require_login(
    user: Optional[MaooUser] = Depends(get_current_user),
    x_llm_model: Optional[str] = Header(default=None),
) -> MaooUser:
    """登录依赖：注入请求级模型偏好。

    - `X-LLM-Model`：用户首选模型；留空则由网关按任务自动路由。
    - `X-LLM-Key`：业务侧**已移除**——Key 由服务端托管，不再从请求头注入。
    """
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    set_llm_model_context(x_llm_model)
    return user


async def require_admin(
    user: Optional[MaooUser] = Depends(get_current_user),
    x_llm_model: Optional[str] = Header(default=None),
) -> MaooUser:
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    set_llm_model_context(x_llm_model)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user