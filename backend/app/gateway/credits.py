"""积分计费：预扣 → 结算（多退少补），带幂等键与流水记账。

为什么是「预扣 + 结算」而不是「事后扣」
--------------------------------------
「事后扣」在并发下会被套利：用户余额 10 积分，同时发起 5 个各消耗 10 积分的请求，
5 个都先跑完 LLM 再扣费，余额被扣成负数，成本已经真实发生且无法追回。
所以必须**先冻结、后结算**：

1. `pre_deduct`：按任务预估值冻结积分（写入 `kind=pre` 流水）。余额不足直接拒绝，
   不浪费任何 LLM 调用；
2. `settle`：LLM 真实 usage 出来后按 `多退少补` 调整（写入 `kind=settle` 流水）；
3. `release`：请求整体失败（无有效 LLM 产出）时全额退回。

幂等
----
`(request_id, kind)` 唯一约束就是幂等键。客户端超时重试、网关重放，
第二次写入直接冲突并被识别为「已处理」，不会重复扣费。

汇率
----
1 元 = 1000 积分（`CREDITS_PER_YUAN`）。
计费成本来自 `observability.cost_yuan()`（真实 usage × 模型单价），
所以「积分消耗」与「token 账单」是一条可对齐的线，不是拍脑袋的固定值。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import SessionLocal
from app.gateway.registry import get_model
from app.models import CreditAccount, CreditLedger, User

CREDITS_PER_YUAN = 1000

# 各任务的 token 预估（预扣用）。偏保守取上限，结算是多退少补，不会多收。
_ESTIMATE_TOKENS: Dict[str, Dict[str, int]] = {
    "jd_parse":      {"in": 1_800, "out": 700},
    "resume_parse":  {"in": 2_400, "out": 900},
    "question_plan": {"in": 3_200, "out": 1_600},
    "ask_question":  {"in": 2_600, "out": 700},
    "followup":      {"in": 2_000, "out": 500},
    "score":         {"in": 1_600, "out": 500},
    "report":        {"in": 5_000, "out": 2_400},
    "study_plan":    {"in": 2_800, "out": 1_600},
    "chat":          {"in": 1_500, "out": 800},
    "ai_precheck":   {"in": 2_000, "out": 300},
}
_DEFAULT_ESTIMATE = {"in": 2_000, "out": 800}


def estimate_tokens(task: str) -> Dict[str, int]:
    return _ESTIMATE_TOKENS.get(task, _DEFAULT_ESTIMATE)


def credits_for(model_id: str, prompt_tokens: int, completion_tokens: int) -> int:
    """token 用量 → 积分（向上取整，宁可多冻结不拖欠）。"""
    spec = get_model(model_id)
    in_price = spec.in_price if spec else 1.0
    out_price = spec.out_price if spec else 2.0
    yuan = (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000
    return max(1, int(-(-yuan * CREDITS_PER_YUAN // 1)))  # ceil


def estimate_credits(task: str, model_id: str) -> int:
    est = estimate_tokens(task)
    return credits_for(model_id, est["in"], est["out"])


def cost_to_credits(cost_yuan: float) -> int:
    return max(1, int(-(-cost_yuan * CREDITS_PER_YUAN // 1)))


# ── 账户 ──────────────────────────────────────────────────────────────
async def ensure_account(maoo_user_id: int) -> Dict[str, Any]:
    """取账户，不存在则按默认赠额开户（首次使用零摩擦）。"""
    async with SessionLocal() as s:
        acct = (await s.execute(
            select(CreditAccount).where(CreditAccount.maoo_user_id == maoo_user_id)
        )).scalars().first()
        if acct is None:
            grant = max(0, settings.default_credit_grant)
            acct = CreditAccount(maoo_user_id=maoo_user_id, balance=grant,
                                 total_granted=grant)
            s.add(acct)
            await s.flush()
            s.add(CreditLedger(maoo_user_id=maoo_user_id,
                               request_id=f"signup:{maoo_user_id}", kind="grant",
                               amount=grant, balance_after=grant,
                               note="新用户初始赠送"))
            user = (await s.execute(
                select(User).where(User.maoo_user_id == maoo_user_id)
            )).scalars().first()
            if user is not None:
                user.credits = grant
            try:
                await s.commit()
            except IntegrityError:
                # 并发开户：另一个请求先建好了，重新读
                await s.rollback()
                acct = (await s.execute(
                    select(CreditAccount).where(CreditAccount.maoo_user_id == maoo_user_id)
                )).scalars().first()
        if acct is None:
            return {"maoo_user_id": maoo_user_id, "balance": 0, "ok": False}
        return {"maoo_user_id": maoo_user_id, "balance": int(acct.balance),
                "frozen": int(acct.frozen), "total_consumed": int(acct.total_consumed),
                "total_granted": int(acct.total_granted),
                "total_recharged": int(acct.total_recharged)}


async def get_account(maoo_user_id: int) -> Dict[str, Any]:
    return await ensure_account(maoo_user_id)


async def list_ledger(maoo_user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(CreditLedger).where(CreditLedger.maoo_user_id == maoo_user_id)
            .order_by(CreditLedger.id.desc()).limit(limit)
        )).scalars().all()
    return [{
        "id": r.id, "request_id": r.request_id, "kind": r.kind, "amount": r.amount,
        "balance_after": r.balance_after, "model": r.model, "task": r.task,
        "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
        "cost_yuan": round(r.cost_yuan, 6), "note": r.note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


# ── 预扣 / 结算 / 释放 ────────────────────────────────────────────────
async def pre_deduct(maoo_user_id: int, request_id: str, task: str,
                     model_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
    """冻结积分。返回 ok=False 时调用方必须直接拒绝请求（未产生任何 LLM 成本）。"""
    await ensure_account(maoo_user_id)
    if not settings.credit_enforce:
        return {"ok": True, "credits": 0, "skipped": True}

    need = amount if amount is not None else estimate_credits(task, model_id)
    async with SessionLocal() as s:
        # 幂等：同一个 request_id 的预扣只生效一次
        exists = (await s.execute(
            select(CreditLedger).where(CreditLedger.request_id == request_id,
                                       CreditLedger.kind == "pre")
        )).scalars().first()
        if exists is not None:
            return {"ok": True, "credits": abs(exists.amount), "duplicate": True}

        acct = (await s.execute(
            select(CreditAccount).where(CreditAccount.maoo_user_id == maoo_user_id)
            .with_for_update()
        )).scalars().first()
        if acct is None:
            return {"ok": False, "reason": "account_missing", "message": "积分账户不存在"}
        if int(acct.balance) < need:
            return {"ok": False, "reason": "insufficient",
                    "balance": int(acct.balance), "credits": need,
                    "message": f"积分不足：本次预计需要 {need}，当前余额 {int(acct.balance)}"}

        acct.balance = int(acct.balance) - need
        acct.frozen = int(acct.frozen) + need
        s.add(CreditLedger(maoo_user_id=maoo_user_id, request_id=request_id, kind="pre",
                           amount=-need, balance_after=int(acct.balance),
                           model=model_id, task=task, note="预扣"))
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
            return {"ok": True, "credits": need, "duplicate": True}
        return {"ok": True, "credits": need, "balance": int(acct.balance)}


async def settle(maoo_user_id: int, request_id: str, *, frozen: int,
                 model_id: str, task: str, prompt_tokens: int = 0,
                 completion_tokens: int = 0, cost_yuan: float = 0.0,
                 balance_after: Optional[int] = None) -> Dict[str, Any]:
    """按真实用量结算：退还 冻结 - 实际消耗 的差额。"""
    if not settings.credit_enforce:
        return {"ok": True, "credits": 0, "skipped": True}

    actual = cost_to_credits(cost_yuan) if cost_yuan > 0 else 0
    refund = max(0, frozen - actual)
    delta = refund - max(0, actual - frozen)   # 净额：多退少补

    async with SessionLocal() as s:
        exists = (await s.execute(
            select(CreditLedger).where(CreditLedger.request_id == request_id,
                                       CreditLedger.kind == "settle")
        )).scalars().first()
        if exists is not None:
            return {"ok": True, "duplicate": True, "credits": abs(exists.amount)}

        acct = (await s.execute(
            select(CreditAccount).where(CreditAccount.maoo_user_id == maoo_user_id)
            .with_for_update()
        )).scalars().first()
        if acct is None:
            return {"ok": False, "reason": "account_missing"}

        acct.frozen = max(0, int(acct.frozen) - frozen)
        acct.balance = int(acct.balance) + delta
        acct.total_consumed = int(acct.total_consumed) + actual
        s.add(CreditLedger(maoo_user_id=maoo_user_id, request_id=request_id, kind="settle",
                           amount=delta, balance_after=int(acct.balance),
                           model=model_id, task=task,
                           prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                           cost_yuan=round(cost_yuan, 6),
                           note=f"结算：实际消耗 {actual}，退还 {refund}"))
        user = (await s.execute(
            select(User).where(User.maoo_user_id == maoo_user_id)
        )).scalars().first()
        if user is not None:
            user.credits = int(acct.balance)
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
            return {"ok": True, "duplicate": True}
        return {"ok": True, "credits": actual, "refund": refund,
                "balance": int(acct.balance)}


async def release(maoo_user_id: int, request_id: str, *, frozen: int,
                  task: str = "", reason: str = "请求失败，积分退回") -> Dict[str, Any]:
    """请求失败且无有效产出时全额退回冻结积分。"""
    return await settle(maoo_user_id, request_id, frozen=frozen, model_id="",
                        task=task, prompt_tokens=0, completion_tokens=0,
                        cost_yuan=0.0) if frozen else {"ok": True, "credits": 0}


async def recharge(maoo_user_id: int, credits: int, *, order_id: str = "",
                   note: str = "充值（占位，未接入真实支付）") -> Dict[str, Any]:
    """充值（占位实现）。

    真实支付需要：下单 → 支付渠道回调 → 验签 → 入账。
    这里只实现入账一端，并把**幂等键显式暴露为 `order_id`**：
    接入支付渠道后，把渠道订单号原样传进来即可获得「回调重放不会重复入账」的保证。
    未传 order_id 时按占位语义为每次调用生成独立订单（每次调用都是一笔新充值）。
    """
    if credits <= 0:
        return {"ok": False, "message": "充值积分必须大于 0"}
    await ensure_account(maoo_user_id)
    oid = (order_id or "").strip() or f"auto-{uuid.uuid4().hex}"
    req_id = f"recharge:{maoo_user_id}:{oid}"
    async with SessionLocal() as s:
        exists = (await s.execute(
            select(CreditLedger).where(CreditLedger.request_id == req_id,
                                       CreditLedger.kind == "recharge")
        )).scalars().first()
        if exists is not None:
            return {"ok": True, "duplicate": True, "credits": exists.amount,
                    "order_id": oid}
        acct = (await s.execute(
            select(CreditAccount).where(CreditAccount.maoo_user_id == maoo_user_id)
            .with_for_update()
        )).scalars().first()
        acct.balance = int(acct.balance) + credits
        acct.total_recharged = int(acct.total_recharged) + credits
        s.add(CreditLedger(maoo_user_id=maoo_user_id, request_id=req_id, kind="recharge",
                           amount=credits, balance_after=int(acct.balance), note=note))
        user = (await s.execute(
            select(User).where(User.maoo_user_id == maoo_user_id)
        )).scalars().first()
        if user is not None:
            user.credits = int(acct.balance)
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
            return {"ok": True, "duplicate": True, "order_id": oid}
        logger.info("用户 {} 充值 {} 积分（占位通道，订单 {}），余额 {}",
                    maoo_user_id, credits, oid, acct.balance)
        return {"ok": True, "credits": credits, "balance": int(acct.balance),
                "order_id": oid, "yuan": round(credits / CREDITS_PER_YUAN, 4)}
