"""
MAOO 平台适配层。

设计原则
--------
- **只适配用户系统**：业务侧表（积分、画像、知识库、会话）全部自有，
  不依赖任何平台运行时——这意味着生产（MAOO 平台）与本地（dev user）走的是
  同一份业务代码，仅用户识别入口不同。
- **可插拔**：通过 `PlatformAdapter` 协议抽象，可替换为其他平台（自建 SSO / Keycloak / 企业微信），
  不动业务一行代码。
- **失败安全**：识别不到用户时，本地（debug=True）回退到 dev user，
  生产（debug=False）返回 None，由依赖层统一 401。

生产路径（MAOO）
~~~~~~~~~~~~~~
平台 Nginx 验证 JWT → 注入 `X-Maoo-User-Id / X-Maoo-Username / X-Maoo-User-Role` → 
本适配层读头部 → 解析为 `MaooUser` → 业务侧按 user_id 走自有表。

本地路径（开发/调试）
~~~~~~~~~~~~~~~~
无平台头时回退 `settings.dev_user_id`（仍是 MaooUser 实例，结构一致）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from fastapi import Header

from app.config import settings


@dataclass(frozen=True)
class ResolvedUser:
    """适配层产出的用户信息（与具体平台解耦）。

    字段含义：
    - external_id: 平台侧的用户 id（MAOO 模式下是 X-Maoo-User-Id）；
      业务侧不再单独建"平台 id"，直接拿这个值当主键关联。
    - username: 平台展示名（用于 UI 渲染，不参与权限判定）。
    - role: 平台角色（admin / developer / user），业务侧只关心是否 admin。
    """
    external_id: int
    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role in settings.admin_roles


class PlatformAdapter(ABC):
    """平台适配器协议：把请求头的若干字段解析成一个统一的 ResolvedUser。"""

    name: str = "abstract"

    @abstractmethod
    async def resolve(self, headers: dict) -> Optional[ResolvedUser]:
        """根据请求头解析用户；识别不到返回 None。"""


class MaooPlatform(PlatformAdapter):
    """MAOO 平台适配器：从 X-Maoo-* 头部解析用户。

    头部约定（由 MAOO 平台 Nginx 注入）：
    - X-Maoo-User-Id: int，平台用户 id（已通过 JWT 校验）
    - X-Maoo-Username: str，展示名（可选）
    - X-Maoo-User-Role: str，平台角色（admin / developer / user）
    """
    name = "maoo"

    async def resolve(self, headers: dict) -> Optional[ResolvedUser]:
        raw_id = headers.get("x-maoo-user-id")
        if not raw_id:
            return None
        try:
            uid = int(raw_id)
        except (TypeError, ValueError):
            return None
        return ResolvedUser(
            external_id=uid,
            username=(headers.get("x-maoo-username") or "").strip(),
            role=(headers.get("x-maoo-user-role") or "user").strip() or "user",
        )


class LocalDevPlatform(PlatformAdapter):
    """本地开发兜底：无平台头时回退 settings.dev_user*。

    仅在 `settings.debug=True` 时被启用——生产环境不应该走这条路径。
    """
    name = "local-dev"

    async def resolve(self, headers: dict) -> Optional[ResolvedUser]:
        if not settings.debug:
            return None
        return ResolvedUser(
            external_id=settings.dev_user_id,
            username=settings.dev_username,
            role=settings.dev_role,
        )


# 全局默认适配器：MAOO 优先，本地兜底
_DEFAULT_CHAIN: list[PlatformAdapter] = [MaooPlatform(), LocalDevPlatform()]


def get_default_chain() -> list[PlatformAdapter]:
    """返回默认适配器链（MAOO → LocalDev）。

    依赖层直接调 `resolve_chain(headers)` 即可；新增平台只需在这里插入。
    """
    return list(_DEFAULT_CHAIN)


async def resolve_chain(headers: dict) -> Optional[ResolvedUser]:
    """按默认链顺序尝试解析用户；返回第一个非 None 的结果。"""
    for adapter in get_default_chain():
        user = await adapter.resolve(headers)
        if user is not None:
            return user
    return None


# ── FastAPI 依赖注入入口（供 app.deps 调用）───────────────────────
async def get_current_user(
    x_maoo_user_id: Optional[str] = Header(default=None),
    x_maoo_username: Optional[str] = Header(default=None),
    x_maoo_user_role: Optional[str] = Header(default=None),
) -> Optional[ResolvedUser]:
    """FastAPI 依赖：解析请求头 → ResolvedUser（None 表示未识别）。"""
    headers = {
        "x-maoo-user-id": x_maoo_user_id,
        "x-maoo-username": x_maoo_username,
        "x-maoo-user-role": x_maoo_user_role,
    }
    return await resolve_chain(headers)