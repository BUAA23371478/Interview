"""平台适配层（仅用户系统）。

见 `app.platform.maoo` 的设计原则说明。
"""
from app.platform.maoo import (
    LocalDevPlatform,
    MaooPlatform,
    PlatformAdapter,
    ResolvedUser,
    resolve_chain,
)

__all__ = [
    "LocalDevPlatform",
    "MaooPlatform",
    "PlatformAdapter",
    "ResolvedUser",
    "resolve_chain",
]