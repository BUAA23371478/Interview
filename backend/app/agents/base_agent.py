"""
Agent 基类：统一 LLM 调用能力。

关键约定：prompt 使用 __UPPER_CASE_PLACEHOLDER__ + .replace 注入（而非 str.format），
以兼容用户提供的 JD/简历中可能包含的 { } 字符。

模型网关接入（v1.1）
--------------------
所有 Agent 的 LLM 调用都收敛到 `invoke_llm` / `invoke_llm_json`，
因此这里是把「任务级模型路由 + 降级链」接进全流程的**唯一改动点**：

- 按 `task`（未显式指定时取 `self.name`）向网关要一条模型调用链；
- 逐个尝试，失败（限流/超时/服务不可用）自动切下一档，全挂才抛错；
- 每次调用把实际模型写进请求级 contextvar，LLM 客户端据此选择接入点与计价，
  计量层记录的即真实使用的模型（账单与 trace 不会对不上）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger

from app.gateway.router import current_prefer, route
from app.llm import LLMError, llm_client, llm_model_ctx


class BaseAgent:
    name: str = "base"
    description: str = ""
    # 网关任务标识：决定用哪个档位的模型（见 app/gateway/router.py TASK_POLICY）
    task: str = ""

    def _task(self) -> str:
        return self.task or self.name

    async def invoke_llm(self, system_prompt: str, user_prompt: str,
                         *, temperature: Optional[float] = None,
                         task: str = "") -> str:
        return await self._call(system_prompt, user_prompt, task=task,
                                temperature=temperature, json_mode=False)

    async def invoke_llm_json(self, system_prompt: str, user_prompt: str,
                              *, temperature: Optional[float] = None,
                              task: str = "") -> Dict[str, Any]:
        return await self._call(system_prompt, user_prompt, task=task,
                                temperature=temperature, json_mode=True)

    async def _call(self, system_prompt: str, user_prompt: str, *,
                    task: str, temperature: Optional[float],
                    json_mode: bool) -> Any:
        """按路由链调用，逐档降级。"""
        plan = route(task or self._task(), prefer=current_prefer())
        if not plan.chain:
            raise LLMError("没有可用的模型（模型注册表为空）")

        last_err: Optional[Exception] = None
        for idx, spec in enumerate(plan.chain):
            token = llm_model_ctx.set(spec.id)
            try:
                if json_mode:
                    return await llm_client.chat_with_json(
                        system_prompt, user_prompt, temperature=temperature)
                return await llm_client.chat(
                    system_prompt, user_prompt, temperature=temperature)
            except LLMError as e:
                last_err = e
                nxt = plan.chain[idx + 1].id if idx + 1 < len(plan.chain) else None
                if nxt:
                    logger.warning("任务 {} 使用模型 {} 失败，降级到 {}：{}",
                                   task, spec.id, nxt, e)
                else:
                    logger.error("任务 {} 全部模型（{}）均失败：{}",
                                 task, [m.id for m in plan.chain], e)
            finally:
                llm_model_ctx.reset(token)
        raise last_err or LLMError("LLM 调用失败")


def _safe_truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len] + "…（已截断）"
