"""面试/练习全流程 API 测试（mock LLM）。"""
from __future__ import annotations

import pytest

from app.deps import MaooUser
from app.services import interview_service, practice_service


@pytest.fixture
def user() -> MaooUser:
    return MaooUser(user_id=202, username="api_tester", role="user")


@pytest.mark.asyncio
async def test_interview_flow(user: MaooUser):
    r = await interview_service.start_interview(user, "AI Agent 工程师 JD", "5 年 Python RAG 经验", 3, "medium")
    assert r["ok"] is True
    assert r["question"]
    sid = r["session_id"]

    finished = False
    for _ in range(3):
        a = await interview_service.answer_interview(user, sid, "我的完整回答")
        if a.get("interview_finished"):
            finished = True
            assert "overall_score" in a["final_report"]
            assert a["study_plan"].get("weeks")
            break
    assert finished


@pytest.mark.asyncio
async def test_practice_flow(user: MaooUser):
    r = await practice_service.start_practice(user, "Redis", "medium", "字节", 2)
    assert r["ok"] is True
    sid = r["session_id"]

    finished = False
    for _ in range(2):
        a = await practice_service.answer_practice(user, sid, "我的练习回答")
        if a.get("finished"):
            finished = True
            assert "avg_score" in a["report"]
            break
    assert finished


@pytest.mark.asyncio
async def test_session_isolation(user: MaooUser):
    """会话按用户隔离：他人不可访问。"""
    other = MaooUser(user_id=999, username="intruder", role="user")
    r = await interview_service.start_interview(user, "JD", "resume", 2, "medium")
    state = await interview_service.get_report(other, r["session_id"])
    assert state is None  # 其他用户访问不到
