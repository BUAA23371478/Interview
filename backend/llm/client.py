from __future__ import annotations

import asyncio
import json
import time as _time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx
from openai import AsyncOpenAI
from openai import APIError as OpenAIApiError
from loguru import logger

from backend.config import settings
from backend.middleware.error_handler import LLMError


@dataclass
class LLMReply:
    content: str
    structured: dict[str, Any] | None = None


class UnifiedLLMClient:
    def __init__(self) -> None:
        self._enabled = bool(settings.llm_api_key)
        self._model = settings.llm_model
        # httpx.Timeout: connect=10s, read=60s, write=10s, pool=5s
        _timeout = httpx.Timeout(10.0, read=60.0, write=10.0, pool=5.0)
        self._client = (
            AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=_timeout,
                max_retries=0,  # 我们自行管理重试
            )
            if self._enabled
            else None
        )
        self._max_retries = 3

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def test_connection(self) -> dict[str, Any]:
        """测试 LLM 连通性。"""
        if not self._enabled or self._client is None:
            return {"ok": False, "model": "N/A", "latency_ms": 0, "error": "LLM_API_KEY 未配置，当前为 Mock 模式"}
        t0 = _time.monotonic()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            latency = int((_time.monotonic() - t0) * 1000)
            return {"ok": True, "model": self._model, "latency_ms": latency, "response": response.choices[0].message.content or ""}
        except OpenAIApiError as e:
            latency = int((_time.monotonic() - t0) * 1000)
            return {"ok": False, "model": self._model, "latency_ms": latency, "error": str(e)}
        except Exception as e:
            latency = int((_time.monotonic() - t0) * 1000)
            return {"ok": False, "model": self._model, "latency_ms": latency, "error": f"连接失败: {e}"}

    async def chat(
        self,
        messages: list[dict[str, str]] | str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict[str, str] | None = None,
    ) -> str:
        if not self._enabled or self._client is None:
            return await self._mock_chat(messages)

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        logger.debug(f"LLM chat 请求 model={self._model} msg_len={len(str(messages))}")

        for attempt in range(self._max_retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if response_format:
                    kwargs["response_format"] = response_format

                response = await self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                logger.debug(f"LLM chat 响应 len={len(content)}")
                return content

            except OpenAIApiError as e:
                logger.warning(f"LLM API 错误 (attempt {attempt + 1}/{self._max_retries}): {e}")
                if attempt >= self._max_retries - 1:
                    raise LLMError(f"AI 服务调用失败: {e}") from e
                await asyncio.sleep(min(2 ** attempt, 8))

            except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                logger.warning(f"LLM 超时 (attempt {attempt + 1}/{self._max_retries}): {e}")
                if attempt >= self._max_retries - 1:
                    raise LLMError("AI 服务响应超时，请稍后重试") from e
                await asyncio.sleep(min(2 ** attempt, 8))

            except Exception as e:
                logger.warning(f"LLM 未知错误 (attempt {attempt + 1}/{self._max_retries}): {type(e).__name__}: {e}")
                if attempt >= self._max_retries - 1:
                    raise LLMError(f"AI 服务异常: {e}") from e
                await asyncio.sleep(min(2 ** attempt, 8))

        return ""

    async def chat_with_json(self, messages: list[dict[str, str]] | str, *, temperature: float = 0.3) -> dict[str, Any]:
        text = await self.chat(messages, temperature=temperature)
        # 尝试提取 JSON：去除 markdown 代码块包裹
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # 去掉 ```json 或 ``` 开头
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            result = json.loads(cleaned)
            logger.debug(f"LLM JSON 解析成功 keys={list(result.keys())}")
            return result
        except json.JSONDecodeError:
            logger.warning(f"LLM 返回非 JSON 文本，前100字符: {text[:100]}")
            return {}

    async def chat_stream(
        self,
        messages: list[dict[str, str]] | str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        if not self._enabled or self._client is None:
            yield await self._mock_chat(messages)
            return

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        kwargs = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        for attempt in range(self._max_retries):
            try:
                stream = await self._client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                return
            except OpenAIApiError as e:
                logger.warning(f"LLM stream 错误 (attempt {attempt + 1}): {e}")
                if attempt >= self._max_retries - 1:
                    raise LLMError(f"AI 服务调用失败: {e}") from e
                await asyncio.sleep(min(2 ** attempt, 8))
            except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                logger.warning(f"LLM stream 超时 (attempt {attempt + 1}): {e}")
                if attempt >= self._max_retries - 1:
                    raise LLMError("AI 服务响应超时，请稍后重试") from e
                await asyncio.sleep(min(2 ** attempt, 8))
            except Exception as e:
                logger.warning(f"LLM stream 未知错误 (attempt {attempt + 1}): {type(e).__name__}: {e}")
                if attempt >= self._max_retries - 1:
                    raise LLMError(f"AI 服务异常: {e}") from e
                await asyncio.sleep(min(2 ** attempt, 8))

    # ------------------------------------------------------------------
    # Mock 回退（LLM_API_KEY 未配置时使用）
    # ------------------------------------------------------------------

    async def _mock_chat(self, messages: list[dict[str, str]] | str) -> str:
        prompt = messages[-1]["content"] if isinstance(messages, list) and messages else str(messages)
        if "是否属于技术面试相关领域" in prompt:
            return json.dumps({"is_valid": True, "reason": "主题属于技术面试范围"}, ensure_ascii=False)
        if "请生成一道简答题" in prompt:
            return json.dumps(
                {
                    "id": "mock-question",
                    "question": "请简述这个主题的核心概念，并说明一个常见应用场景。",
                    "question_type": "short_answer",
                    "reference_answer": "从定义、原理和场景三个方面回答即可。",
                    "knowledge_points": ["核心概念", "应用场景"],
                },
                ensure_ascii=False,
            )
        if "请评估以下回答" in prompt:
            return json.dumps(
                {
                    "score": 80,
                    "is_correct": True,
                    "correct_answer": "从定义、原理和场景三个方面回答即可。",
                    "analysis": "## 评分：80/100\n\n回答整体可接受，但还可以补充关键细节。",
                    "knowledge_points": ["核心概念", "应用场景"],
                    "common_mistakes": ["只给出结论，没有解释原理"],
                },
                ensure_ascii=False,
            )
        if "判断下一步操作" in prompt:
            return json.dumps({"should_follow_up": False, "reason": "回答已经足够完整"}, ensure_ascii=False)
        if "生成一份全面的复盘报告" in prompt:
            return json.dumps(
                {
                    "overall_score": 82,
                    "tech_depth": 78,
                    "clarity": 85,
                    "logic": 88,
                    "job_match": 76,
                    "overall_comment": "整体表现稳定，具备基本面试竞争力。",
                    "round_reviews": [],
                    "highlights": [],
                    "weaknesses": ["深度仍可提升"],
                    "suggestions": ["补充原理与实践结合的回答"],
                },
                ensure_ascii=False,
            )
        return "{}"
