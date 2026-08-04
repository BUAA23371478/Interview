"""
MAOO 平台用户依赖。

平台 Nginx 验证 JWT 后注入请求头：
    X-Maoo-User-Id / X-Maoo-Username / X-Maoo-User-Role / X-Maoo-App-Slug

本地开发（无这些头）时回退到 settings 中的 dev 用户。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException

from app.config import settings


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
    """读取平台注入的用户身份。未登录时返回 None（供公开端点）。"""
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
    return None


async def require_login(user: Optional[MaooUser] = Depends(get_current_user)) -> MaooUser:
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


async def require_admin(user: Optional[MaooUser] = Depends(get_current_user)) -> MaooUser:
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
