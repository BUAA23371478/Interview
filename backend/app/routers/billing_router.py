"""模型网关 + 积分计费 API。

- `GET  /billing/models`   可用模型目录（含计价、档位、能力标签）
- `GET  /billing/routing`  任务→模型路由表（解释「为什么这个环节用这个模型」）
- `GET  /billing/balance`  我的积分余额
- `GET  /billing/ledger`   我的积分流水
- `POST /billing/recharge` 充值（占位通道，未接真实支付）
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.deps import MaooUser, require_login
from app.gateway import credits
from app.gateway.registry import list_models
from app.gateway.router import TASK_POLICY
from app.schemas import RechargeRequest

router = APIRouter(prefix="/billing", tags=["模型与计费"])


@router.get("/models")
async def models(user: MaooUser = Depends(require_login)) -> Dict[str, Any]:
    """可用模型目录。用户可在「模型设置」中指定偏好，未指定则按任务路由。"""
    return {
        "items": [m.to_public() for m in list_models()],
        "default": list_models()[0].id if list_models() else "",
        "credits_per_yuan": credits.CREDITS_PER_YUAN,
        "recharge_enabled": settings.credit_recharge_enabled,
    }


@router.get("/routing")
async def routing(user: MaooUser = Depends(require_login)) -> Dict[str, Any]:
    """任务级路由策略：说明每个环节为什么用这个档位的模型。"""
    return {
        "policy": [
            {"task": task, "primary": spec.primary, "fallbacks": list(spec.fallbacks),
             "reason": spec.reason}
            for task, spec in TASK_POLICY.items()
        ],
    }


@router.get("/balance")
async def balance(user: MaooUser = Depends(require_login)) -> Dict[str, Any]:
    acct = await credits.get_account(user.user_id)
    return {**acct, "credits_per_yuan": credits.CREDITS_PER_YUAN,
            "yuan": round(acct.get("balance", 0) / credits.CREDITS_PER_YUAN, 4)}


@router.get("/ledger")
async def ledger(user: MaooUser = Depends(require_login),
                 limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, Any]:
    return {"items": await credits.list_ledger(user.user_id, limit)}


@router.post("/recharge")
async def recharge(req: RechargeRequest,
                   user: MaooUser = Depends(require_login)) -> Dict[str, Any]:
    """充值（占位）。

    未接入真实支付渠道，仅完成「入账」一端，并对参数做上限校验，
    接入支付后把支付回调的订单号作为幂等键传入即可无缝替换。
    """
    if not settings.credit_recharge_enabled:
        raise HTTPException(
            status_code=503,
            detail="充值通道尚未开放（当前为占位实现，未接入真实支付）")
    if req.credits > 10_000_000:
        raise HTTPException(status_code=400, detail="单次充值积分过大")
    res = await credits.recharge(user.user_id, req.credits,
                                 order_id=req.order_id,
                                 note=req.note or "充值（占位）")
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("message", "充值失败"))
    return res
