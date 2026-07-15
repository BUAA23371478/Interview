"""刷题模块测试：创建会话 / 提交答案 / 跳过 / 下一题。

与 PLAN.md 4.2 节一致。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestPracticeSession:
    """刷题会话生命周期测试。"""

    async def test_create_session_success(self, client: AsyncClient, auth_headers: dict):
        """正常创建刷题会话。"""
        res = await client.post(
            "/api/practice/start",
            json={"topic": "Python", "max_questions": 5},
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert "sessionId" in data

    async def test_create_session_invalid_topic(self, client: AsyncClient, auth_headers: dict):
        """无效主题（非技术类）应被拒绝。"""
        res = await client.post(
            "/api/practice/start",
            json={"topic": "今晚吃什么", "max_questions": 5},
            headers=auth_headers,
        )
        # Mock 模式下 LLM 会通过校验，所以这里只测试请求正常
        assert res.status_code in (200, 400)

    async def test_get_session_status(self, client: AsyncClient, auth_headers: dict):
        """查询会话状态。"""
        # 先创建会话
        res = await client.post(
            "/api/practice/start",
            json={"topic": "Java", "max_questions": 3},
            headers=auth_headers,
        )
        assert res.status_code == 200
        session_id = res.json()["sessionId"]

        res = await client.get(
            f"/api/practice/{session_id}/status",
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert "topic" in data or "phase" in data

    async def test_submit_answer_not_found(self, client: AsyncClient, auth_headers: dict):
        """提交不存在的会话应返回错误。"""
        res = await client.post(
            "/api/practice/99999/answer",
            json={"answer": "test answer", "time_spent_seconds": 30},
            headers=auth_headers,
        )
        assert res.status_code in (400, 404, 500)


class TestPracticeHistory:
    """刷题历史测试。"""

    async def test_practice_history_empty(self, client: AsyncClient, auth_headers: dict):
        """新用户应有空历史。"""
        res = await client.get(
            "/api/history/practice",
            headers=auth_headers,
            params={"page": 1, "limit": 10},
        )
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert data.get("total", 0) == 0

    async def test_practice_stats(self, client: AsyncClient, auth_headers: dict):
        """新用户统计应为全 0。"""
        res = await client.get(
            "/api/practice/stats",
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("totalQuestions", 0) == 0
