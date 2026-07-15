"""用户模块测试：注册 / 登录 / 简历。

与 PLAN.md 4.2 节一致。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestUserRegistration:
    """用户注册测试。"""

    async def test_register_success(self, client: AsyncClient):
        """正常注册。"""
        res = await client.post(
            "/api/user/register",
            json={"username": "newuser", "password": "pass123456"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "userId" in data
        assert data.get("username") == "newuser"

    async def test_register_duplicate_username(self, client: AsyncClient, auth_user: dict):
        """重复用户名注册应失败。"""
        res = await client.post(
            "/api/user/register",
            json={"username": "testuser", "password": "pass123456"},
        )
        assert res.status_code == 400

    async def test_register_short_password(self, client: AsyncClient):
        """密码过短应失败。"""
        res = await client.post(
            "/api/user/register",
            json={"username": "user3", "password": "123"},
        )
        # 可能返回 400 或 422
        assert res.status_code in (400, 422)


class TestUserLogin:
    """用户登录测试。"""

    async def test_login_success(self, client: AsyncClient, auth_user: dict):
        """正常登录。"""
        res = await client.post(
            "/api/user/login",
            json={"username": "testuser", "password": "test123456"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("userId") == auth_user["userId"]

    async def test_login_wrong_password(self, client: AsyncClient, auth_user: dict):
        """密码错误应失败。"""
        res = await client.post(
            "/api/user/login",
            json={"username": "testuser", "password": "wrongpassword"},
        )
        assert res.status_code in (400, 401)

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """登录不存在用户应失败。"""
        res = await client.post(
            "/api/user/login",
            json={"username": "nonexistent", "password": "pass123456"},
        )
        assert res.status_code in (400, 401)
