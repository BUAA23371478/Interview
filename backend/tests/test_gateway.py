"""统一模型网关 + 积分计费回归测试。

覆盖三件事：
1. 模型注册表与任务路由（含用户覆盖、非法模型回落）
2. 降级链（主模型失败自动切备用，全挂才抛错）
3. 积分预扣/结算/退回/充值 的幂等与多退少补语义
"""
from __future__ import annotations

import pytest

from app.agents.base_agent import BaseAgent
from app.config import settings
from app.gateway import credits
from app.gateway.registry import get_model, list_models
from app.gateway.router import route
from app.llm import LLMError, llm_client

UID = 777


# ── 注册表与路由 ──────────────────────────────────────────────────────

def test_registry_lookup_and_prefix_match():
    assert get_model("deepseek-chat") is not None
    assert get_model("deepseek-chat-0324").id == "deepseek-chat"   # 前缀匹配
    assert get_model("no-such-model") is None
    assert get_model("") is None
    assert len(list_models()) >= 3


def test_task_routing_picks_tier_by_semantics():
    """报告这类推理密集任务走强档，结构化抽取走便宜档 —— 这是成本优化的依据。"""
    assert route("jd_parse").primary.id == "deepseek-chat"
    assert route("report").primary.id == "deepseek-reasoner"
    assert route("ai_precheck").primary.id == "qwen-turbo"
    # 未登记任务走默认策略，不会崩
    assert route("unknown-task").primary is not None


def test_route_user_prefer_overrides_policy():
    plan = route("report", prefer="qwen-plus")
    assert plan.primary.id == "qwen-plus"
    assert plan.overridden is True
    # 备用链仍然完整（用户覆盖只改首选，不影响兜底）
    assert "deepseek-chat" in [m.id for m in plan.chain]


def test_route_invalid_prefer_ignored():
    """用户填了注册表里没有的模型名 → 忽略并回落策略，而不是整场不可用。"""
    plan = route("report", prefer="my-custom-model")
    assert plan.primary.id == "deepseek-reasoner"
    assert plan.overridden is False


# ── 降级链 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_falls_back_to_next_model(monkeypatch):
    """主模型抛错 → 自动切下一档；记录实际生效模型，保证账单与 trace 对得上。"""
    tried: list[str] = []

    async def fake_chat(system_prompt, user_prompt, **kw):
        from app.llm import llm_model_ctx
        tried.append(llm_model_ctx.get())
        if len(tried) == 1:
            raise LLMError("429 rate limited")
        return "ok-from-fallback"

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    agent = BaseAgent()
    agent.task = "jd_parse"          # 链路：deepseek-chat -> qwen-turbo

    out = await agent.invoke_llm("sys", "user")
    assert out == "ok-from-fallback"
    assert tried == ["deepseek-chat", "qwen-turbo"]


@pytest.mark.asyncio
async def test_agent_raises_when_all_models_fail(monkeypatch):
    async def always_fail(system_prompt, user_prompt, **kw):
        raise LLMError("all down")

    monkeypatch.setattr(llm_client, "chat", always_fail)
    agent = BaseAgent()
    agent.task = "jd_parse"
    with pytest.raises(LLMError):
        await agent.invoke_llm("sys", "user")


@pytest.mark.asyncio
async def test_agent_releases_model_context(monkeypatch):
    """调用结束后 contextvar 必须复位，否则污染同请求后续任务的模型选择。"""
    from app.llm import llm_model_ctx

    async def fake_chat(system_prompt, user_prompt, **kw):
        return "x"

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    agent = BaseAgent()
    agent.task = "report"
    assert llm_model_ctx.get() == ""
    await agent.invoke_llm("sys", "user")
    assert llm_model_ctx.get() == ""


# ── 积分计费 ──────────────────────────────────────────────────────────

def test_credits_estimation_is_ceil_and_positive():
    n = credits.estimate_credits("report", "deepseek-reasoner")
    assert n >= 1
    # 便宜模型的预扣必须显著低于强模型
    assert credits.estimate_credits("ai_precheck", "qwen-turbo") < n
    assert credits.cost_to_credits(0.0) == 1     # 极小成本也至少 1 积分（向上取整）


@pytest.mark.asyncio
async def test_account_auto_provision_with_grant():
    acct = await credits.ensure_account(9101)
    assert acct["balance"] == settings.default_credit_grant
    # 幂等：重复调用不会重复赠送
    again = await credits.ensure_account(9101)
    assert again["balance"] == settings.default_credit_grant


@pytest.mark.asyncio
async def test_pre_deduct_then_settle_refunds_difference():
    """冻结 500 → 实际成本约 0.002 元（2 积分）→ 其余全额退回。"""
    uid = 9102
    await credits.ensure_account(uid)
    start = (await credits.get_account(uid))["balance"]

    pre = await credits.pre_deduct(uid, "req-a", "score", "deepseek-chat", amount=500)
    assert pre["ok"] is True
    assert (await credits.get_account(uid))["balance"] == start - 500

    done = await credits.settle(uid, "req-a", frozen=500, model_id="deepseek-chat",
                                task="score", prompt_tokens=1000, completion_tokens=500,
                                cost_yuan=0.002)
    assert done["credits"] == 2      # 0.002 元 = 2 积分
    assert done["refund"] == 498
    assert (await credits.get_account(uid))["balance"] == start - 2


@pytest.mark.asyncio
async def test_pre_deduct_idempotent_on_retry():
    """同一 request_id 重放不会重复扣费（客户端超时重试场景）。"""
    uid = 9103
    await credits.ensure_account(uid)
    start = (await credits.get_account(uid))["balance"]

    a = await credits.pre_deduct(uid, "req-dup", "score", "deepseek-chat", amount=300)
    b = await credits.pre_deduct(uid, "req-dup", "score", "deepseek-chat", amount=300)
    assert a["ok"] and b.get("duplicate") is True
    assert (await credits.get_account(uid))["balance"] == start - 300


@pytest.mark.asyncio
async def test_pre_deduct_rejects_insufficient_balance():
    """余额不足必须**在调用 LLM 之前**拒绝，避免烧掉无法追回的成本。"""
    uid = 9104
    await credits.ensure_account(uid)
    res = await credits.pre_deduct(uid, "req-poor", "report", "deepseek-reasoner",
                                   amount=10 ** 9)
    assert res["ok"] is False
    assert res["reason"] == "insufficient"
    assert "积分不足" in res["message"]


@pytest.mark.asyncio
async def test_release_refunds_everything_on_failure():
    uid = 9105
    await credits.ensure_account(uid)
    start = (await credits.get_account(uid))["balance"]
    await credits.pre_deduct(uid, "req-fail", "report", "deepseek-reasoner", amount=800)
    await credits.release(uid, "req-fail", frozen=800, task="report")
    assert (await credits.get_account(uid))["balance"] == start


@pytest.mark.asyncio
async def test_recharge_placeholder_is_idempotent_by_order_id():
    uid = 9106
    await credits.ensure_account(uid)
    start = (await credits.get_account(uid))["balance"]

    r1 = await credits.recharge(uid, 5000, order_id="order-001")
    r2 = await credits.recharge(uid, 5000, order_id="order-001")   # 支付回调重放
    assert r1["ok"] and r2.get("duplicate") is True
    assert (await credits.get_account(uid))["balance"] == start + 5000


@pytest.mark.asyncio
async def test_ledger_records_full_lifecycle():
    uid = 9107
    await credits.ensure_account(uid)
    await credits.pre_deduct(uid, "req-ledger", "score", "deepseek-chat", amount=100)
    await credits.settle(uid, "req-ledger", frozen=100, model_id="deepseek-chat",
                         task="score", cost_yuan=0.003)
    rows = await credits.list_ledger(uid, limit=20)
    kinds = [r["kind"] for r in rows]
    assert "grant" in kinds and "pre" in kinds and "settle" in kinds
    pre = next(r for r in rows if r["kind"] == "pre")
    assert pre["amount"] == -100
