"""M1 回归测试：BYOK 完全移除 + 平台适配层抽象 + 积分系统。

- `X-LLM-Key` 请求头应当完全被忽略（业务侧不接收用户自带 key）
- BYOK 不再存在，LLM 调用一律走服务端 settings 托管 key
- 平台适配层抽象正确：MAOO → LocalDev 链顺序解析
- 积分不足时 LLM 调用应当被拒绝（402）
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List


# ── 平台适配层 ────────────────────────────────────────────────────
def test_platform_adapter_chain_resolves_maoo_first():
    """MAOO 头部存在时优先使用 MAOO 适配器，LocalDev 不被触发。"""
    from app.platform import LocalDevPlatform, MaooPlatform, resolve_chain

    called: List[str] = []

    class TrackedMaoo(MaooPlatform):
        async def resolve(self, headers):
            called.append("maoo")
            return await super().resolve(headers)

    class TrackedLocal(LocalDevPlatform):
        async def resolve(self, headers):
            called.append("local")
            return await super().resolve(headers)

    # 临时替换全局链
    from app.platform import maoo as maoo_mod
    saved = maoo_mod._DEFAULT_CHAIN
    maoo_mod._DEFAULT_CHAIN = [TrackedMaoo(), TrackedLocal()]
    try:
        user = asyncio.run(resolve_chain({
            "x-maoo-user-id": "42",
            "x-maoo-username": "alice",
            "x-maoo-user-role": "admin",
        }))
    finally:
        maoo_mod._DEFAULT_CHAIN = saved

    assert user is not None
    assert user.external_id == 42
    assert user.username == "alice"
    assert user.role == "admin"
    assert called == ["maoo"]   # LocalDev 没被调用


def test_platform_adapter_chain_falls_back_to_local_dev():
    """无 MAOO 头时（debug=True）回退 LocalDev。"""
    from app.platform import resolve_chain
    from app.platform import maoo as maoo_mod
    from app.config import settings

    saved_chain = maoo_mod._DEFAULT_CHAIN
    saved_debug = settings.debug
    settings.debug = True
    try:
        user = asyncio.run(resolve_chain({}))   # 无任何头
    finally:
        maoo_mod._DEFAULT_CHAIN = saved_chain
        settings.debug = saved_debug

    assert user is not None
    assert user.external_id == settings.dev_user_id
    assert user.username == settings.dev_username


def test_platform_adapter_rejects_invalid_user_id_in_production():
    """MAOO 头存在但 user_id 不是合法整数 → MAOO 适配器返回 None。
    生产环境下（debug=False）LocalDev 不兜底 → 最终 None。
    """
    from app.config import settings
    from app.platform import resolve_chain
    from app.platform import maoo as maoo_mod

    saved_debug = settings.debug
    settings.debug = False
    try:
        user = asyncio.run(resolve_chain({"x-maoo-user-id": "not-an-int"}))
    finally:
        settings.debug = saved_debug

    assert user is None


# ── BYOK 已彻底移除 ─────────────────────────────────────────────────
def test_byok_header_is_completely_ignored():
    """发 X-LLM-Key 头时，LLM 客户端不应当使用它——纯走服务端托管 key。

    验证手段：直接读 UnifiedLLMClient._key_for_provider(provider)，
    返回的必须是 settings 里的服务端 key，而不是请求头里塞的假 key。
    """
    from app.llm import UnifiedLLMClient

    client = UnifiedLLMClient()
    # 即便上下文里"曾经"设置过 llm_api_key_ctx（已不存在的概念），也不应生效：
    # 这里直接验证 _key_for_provider 完全只走服务端 settings。
    server_key = client._key_for_provider("deepseek")
    # 与 settings.provider_key("deepseek") 一致
    from app.config import settings
    assert server_key == settings.provider_key("deepseek")


def test_llm_module_exposes_no_byok_api():
    """app.llm 公共 API 不应再暴露 set_llm_key_context / llm_api_key_ctx。"""
    import app.llm as llm_mod
    assert not hasattr(llm_mod, "set_llm_key_context")
    assert not hasattr(llm_mod, "llm_api_key_ctx")


def test_deps_require_login_does_not_take_x_llm_key():
    """FastAPI 依赖层不再声明 X-LLM-Key 请求头。"""
    import inspect
    from app.deps import require_login

    sig = inspect.signature(require_login)
    param_names = [p.name for p in sig.parameters.values()]
    assert "x_llm_key" not in param_names, (
        f"require_login 仍然声明了 x_llm_key 参数: {param_names}")


# ── 积分系统集成 ─────────────────────────────────────────────────
def test_pre_deduct_rejects_insufficient_balance(monkeypatch):
    """余额为 0 时，预扣应当返回 ok=False 并提供 reason='insufficient'。"""
    from app.gateway import credits

    async def run():
        # 用一个全新账号
        uid = 999_001
        await credits.ensure_account(uid)
        # 强行把余额改回 0（模拟耗尽）
        from sqlalchemy import select, update
        from app.models import CreditAccount
        from app.database import SessionLocal
        async with SessionLocal() as s:
            await s.execute(update(CreditAccount)
                            .where(CreditAccount.maoo_user_id == uid)
                            .values(balance=0))
            await s.commit()
        res = await credits.pre_deduct(uid, "test-req-1", "ask_question",
                                       model_id="deepseek-flash", amount=10)
        return res

    res = asyncio.run(run())
    assert res["ok"] is False
    assert res["reason"] == "insufficient"
    assert res["balance"] == 0
    assert res["credits"] == 10


def test_recharge_is_idempotent_by_order_id():
    """同一个 order_id 多次充值只会入账一次。"""
    from app.gateway import credits
    from app.database import SessionLocal
    from app.models import CreditAccount
    from sqlalchemy import select

    async def run():
        uid = 999_002
        await credits.ensure_account(uid)
        r1 = await credits.recharge(uid, 5000, order_id="order-test-1")
        r2 = await credits.recharge(uid, 5000, order_id="order-test-1")   # 重复
        async with SessionLocal() as s:
            acct = (await s.execute(
                select(CreditAccount).where(CreditAccount.maoo_user_id == uid)
            )).scalars().first()
            final_balance = int(acct.balance)
        return r1, r2, final_balance

    r1, r2, final_balance = asyncio.run(run())
    assert r1["ok"] is True
    assert r2["ok"] is True and r2["duplicate"] is True
    assert r2["credits"] == 5000
    # 余额只被加一次：r1 加了 5000，之后 r2 是重复不入账
    assert r1["balance"] == final_balance


# ── 前端代码不留 X-LLM-Key 头痕迹 ──────────────────────────────────
def test_frontend_client_does_not_send_x_llm_key():
    """TypeScript 客户端代码不再发送 X-LLM-Key 请求头（无 BYOK 模式）。"""
    from pathlib import Path
    client_path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "client.ts"
    src = client_path.read_text(encoding="utf-8")
    assert "X-LLM-Key" not in src, "前端 client.ts 仍然存在 X-LLM-Key 头"
    assert "getLlmKey" not in src, "前端仍然暴露 getLlmKey 函数"


def test_frontend_profile_no_longer_exposes_byok_input():
    """前端个人中心页面不再展示「自带 API Key」输入框。"""
    from pathlib import Path
    profile_path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "Profile.tsx"
    src = profile_path.read_text(encoding="utf-8")
    assert "LLM_KEY_STORAGE" not in src
    assert "saveLlmKey" not in src
    assert "testLlm" not in src
    # 反向断言：积分账户卡片应存在
    assert "积分账户" in src