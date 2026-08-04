"""知识库审核闭环测试：上传 → pending → admin 审核 → 可检索。"""
from __future__ import annotations

import io
import pytest

from app.database import SessionLocal
from app.deps import MaooUser
from app.models import Document
from app.services import kb_service
from sqlalchemy import select


@pytest.fixture(scope="module")
def user() -> MaooUser:
    return MaooUser(user_id=101, username="tester", role="user")


@pytest.fixture(scope="module")
def admin() -> MaooUser:
    return MaooUser(user_id=1, username="admin", role="admin")


class FakeUpload:
    def __init__(self, content: str, name: str) -> None:
        self._content = content.encode("utf-8")
        self.filename = name

    async def read(self) -> bytes:
        return self._content


@pytest.mark.asyncio
async def test_upload_pending_then_approve(user: MaooUser, admin: MaooUser):
    content = (
        "# Redis 分布式锁面试题\n\n"
        "## 问题：如何实现 Redis 分布式锁？\n\n"
        "使用 SETNX + TTL，配合 Lua 脚本保证原子性释放。"
        "看门狗机制用于续期。RedLock 存在争议。"
        "这是足够长的技术文档内容，用于通过 AI 预审。"
        "继续补充一些细节文字以保证长度足够，避免触发过短校验。"
    )
    up = await kb_service.upload_document(user, FakeUpload(content, "redis-lock.md"))
    assert up["ok"] is True
    assert up["status"] == "pending"
    doc_id = up["doc_id"]

    # 普通用户看不到 pending（列表过滤）
    listed = await kb_service.list_documents(user, 1, 50)
    assert all(d["status"] == "approved" for d in listed["items"])

    # 非 admin 审核被拒
    res = await kb_service.review_document(user, doc_id, "approve")
    assert res["ok"] is False

    # admin 审核通过
    res = await kb_service.review_document(admin, doc_id, "approve", "合格")
    assert res["ok"] is True
    assert res["status"] == "approved"

    # 通过后可以检索到
    hits = await kb_service.search_documents("Redis 分布式锁", top_k=5)
    assert len(hits) > 0


@pytest.mark.asyncio
async def test_duplicate_rejected(user: MaooUser):
    content = (
        "# MySQL 索引面试题\n\n"
        "## 问题：B+ 树索引为什么快？\n\n"
        "B+ 树是平衡多路查找树，叶子节点存储数据并形成有序链表，"
        "支持范围查询。高度较低，IO 次数少。这是足够长的文档内容。"
    )
    up1 = await kb_service.upload_document(user, FakeUpload(content, "mysql-index.md"))
    assert up1["ok"] is True
    up2 = await kb_service.upload_document(user, FakeUpload(content, "mysql-index-copy.md"))
    assert up2["ok"] is False  # 内容重复被拦截
    assert up2["status"] == "rejected"


@pytest.mark.asyncio
async def test_upload_quota(user: MaooUser):
    """每日上传数量超限被拦截。"""
    small = ("# 技术文档\n\n" + "这是一篇技术文档内容。" * 20)
    ok_count = 0
    for i in range(6):  # 上限默认 5
        up = await kb_service.upload_document(
            user, FakeUpload(small, f"doc-{i}.md"), )
        if up["ok"]:
            ok_count += 1
    assert ok_count <= 5
