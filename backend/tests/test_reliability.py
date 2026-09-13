"""可靠性回归测试：SSE 事件回放、会话乐观锁、难度状态机、向量字节序、Provider key 池隔离。

这些用例对应本轮优化修掉的 P0 缺陷，也是「优化前 vs 优化后」可复现的证据：
每一条都能在旧实现上失败、在新实现上通过。
"""
from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest

from app.agents.difficulty_fsm import effective_difficulty, update_difficulty
from app.config import settings
from app.deps import MaooUser
from app.embedding import MAGIC_F32, MAGIC_F64, blob_dim, pack_vector, unpack_vector
from app.memory.short_term import ShortTermMemory
from app.rag.vector_store import _stack_vectors
from app.sse.emitter import SSEManager, SSEmitter, parse_last_event_id, sse_format


def _user(uid: int = 1) -> MaooUser:
    return MaooUser(user_id=uid, username=f"u{uid}", role="user")


# ── SSE：事件不丢 + 断线回放 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_sse_buffers_without_client():
    """旧实现：无连接时 emit 直接 return False，事件静默丢弃。

    新实现：通道与连接解耦，无客户端也会建通道并缓冲，返回 True。
    """
    mgr = SSEManager()
    emi = SSEmitter(mgr)
    key = "interview:no-client"
    ok = await emi.emit(key, "question", {"question": "Q1"})
    assert ok is True
    conn = mgr.get(key)
    assert conn is not None and conn.seq == 1 and len(conn.buffer) == 1


async def _collect(mgr: SSEManager, key: str, conn: Any, last_event_id: int,
                   limit: int) -> list:
    """收集前 limit 条事件（通道未 done 时不会永久挂住）。"""
    out = []
    async for e in mgr.stream_events(key, conn, last_event_id=last_event_id):
        out.append(e)
        if len(out) >= limit:
            break
    return out


@pytest.mark.asyncio
async def test_sse_replay_since_last_event_id():
    """断线重连：带 Last-Event-ID 只回放该序号之后的事件，不重复不遗漏。"""
    mgr = SSEManager()
    emi = SSEmitter(mgr)
    key = "interview:replay"
    for i in range(5):
        await emi.emit(key, "chunk", {"content": str(i)})

    conn = await mgr.connect(key, 1)
    full = await _collect(mgr, key, conn, last_event_id=0, limit=5)
    assert [e["id"] for e in full] == [1, 2, 3, 4, 5]

    # 模拟断线在 seq=2 之后：重连只应拿到 3、4、5
    conn2 = await mgr.connect(key, 1)
    partial = await _collect(mgr, key, conn2, last_event_id=2, limit=3)
    assert [e["id"] for e in partial] == [3, 4, 5]
    assert [e["data"]["content"] for e in partial] == ["2", "3", "4"]


@pytest.mark.asyncio
async def test_sse_stream_terminates_on_done():
    """会话标记 done 后，消费流排空缓冲即正常收尾（不会永久挂住）。"""
    mgr = SSEManager()
    emi = SSEmitter(mgr)
    key = "interview:done"
    await emi.emit(key, "question", {"question": "Q1"})
    await emi.emit(key, "interview_finished", {})
    mgr.mark_done(key)

    conn = await mgr.connect(key, 1)
    events = [e async for e in mgr.stream_events(key, conn, last_event_id=0)]
    assert [e["event"] for e in events] == ["question", "interview_finished"]


def test_sse_format_has_id_line():
    text = sse_format("chunk", {"content": "x"}, event_id=7)
    assert "id: 7\n" in text and "event: chunk\n" in text and text.endswith("\n\n")
    assert parse_last_event_id("12") == 12
    assert parse_last_event_id("abc") == 0          # 非法值容错
    assert parse_last_event_id(None) == 0


# ── 会话快照乐观锁 ────────────────────────────────────────────────────

def test_session_cas_rejects_stale_write():
    """旧实现：后写者无条件覆盖，并发下答题记录直接丢。

    新实现：版本失配拒绝写入，调用方据此返回 409。
    """
    stm = ShortTermMemory()
    stm._available = False  # 强制内存模式，避免依赖 Redis
    sid = "cas-test"
    state = {"session_id": sid, "qa_history": [], "_version": 0}

    assert stm.save_snapshot(sid, state, expected_version=None) is True   # 首写无条件
    assert stm.version(sid) == 1

    loaded = stm.load_snapshot(sid)
    assert loaded["_version"] == 1

    # 客户端 A、B 都基于版本 1 读改写
    assert stm.save_snapshot(sid, {"session_id": sid, "qa_history": [1]},
                             expected_version=1) is True
    # B 用过期版本 1 再写 → 必须被拒
    assert stm.save_snapshot(sid, {"session_id": sid, "qa_history": [2]},
                             expected_version=1) is False
    # 落库的仍是 A 的写入
    assert stm.load_snapshot(sid)["qa_history"] == [1]


# ── 难度状态机真正参与出题 ────────────────────────────────────────────

def test_difficulty_fsm_adaptive_drives_question():
    """旧实现：出题取 plan 里预生成的 difficulty，状态机只装饰 prompt。

    新实现：adaptive 模式下状态机是唯一裁决者；plan 模式保留作 A/B 对照。
    """
    state = {"current_difficulty": "easy", "consecutive_correct": 0,
             "consecutive_wrong": 0, "last_correctness": True,
             "current_question_idx": 0}
    plan_item = {"difficulty": "hard"}
    old_mode = settings.difficulty_mode

    try:
        settings.difficulty_mode = "adaptive"
        assert effective_difficulty(state, plan_item) == "easy"
        for _ in range(settings.consecutive_to_upgrade):
            update_difficulty(state)
            state["last_correctness"] = True
        assert state["current_difficulty"] == "medium"
        assert effective_difficulty(state, plan_item) == "medium"
        assert [t["reason"] for t in state["difficulty_trace"]].count("upgrade") == 1

        settings.difficulty_mode = "plan"
        assert effective_difficulty(state, plan_item) == "hard"
    finally:
        settings.difficulty_mode = old_mode


def test_difficulty_fsm_downgrade_on_wrong_streak():
    state = {"current_difficulty": "hard", "consecutive_correct": 0,
             "consecutive_wrong": 0, "last_correctness": False,
             "current_question_idx": 0}
    for _ in range(settings.consecutive_to_downgrade):
        update_difficulty(state)
    assert state["current_difficulty"] == "medium"


# ── 向量 BLOB 字节序（本轮真实踩到的坑）────────────────────────────────

@pytest.mark.parametrize("dtype", ["float32", "float64"])
def test_pack_stack_roundtrip_matches(dtype: str):
    """pack_vector 用大端打包，numpy 必须显式按大端解析。

    若按本机小端解析，矩阵会变成 inf/NaN —— 检索「能跑但结果是错的」。
    """
    vec = [0.5, -0.25, 1.0, 0.0, 0.125]
    blob = pack_vector(vec, dtype=dtype)
    assert blob_dim(blob) == len(vec)
    assert blob[:4] == (MAGIC_F32 if dtype == "float32" else MAGIC_F64)

    mat = _stack_vectors([blob], len(vec))
    assert mat.dtype == np.float32
    assert np.all(np.isfinite(mat))
    np.testing.assert_allclose(np.asarray(unpack_vector(blob), dtype=np.float64),
                               np.asarray(vec), rtol=1e-6)


def test_mixed_legacy_and_new_blobs():
    """历史裸大端 float64（无头）与新格式混库时都能正确解析。"""
    import struct

    vec = [0.25, 0.5, -0.75, 0.125]
    legacy = struct.pack(">4d", *vec)          # 旧生产格式：大端 float64，无头
    modern = pack_vector(vec, "float32")
    mat = _stack_vectors([legacy, modern], 4)
    assert np.all(np.isfinite(mat))
    np.testing.assert_allclose(mat[0], mat[1], rtol=1e-6)


# ── 混合检索融合 ──────────────────────────────────────────────────────

def _hit(cid: str, doc: str, score: float, source: str) -> dict:
    return {"id": cid, "doc_id": doc, "content": cid, "metadata": {}, "score": score,
            "source": source}


def test_rrf_merges_shared_chunk_ids():
    """同一个 chunk 被两路同时召回 → 得分相加 → 名次上升。这是融合生效的判据。"""
    from app.rag.hybrid import reciprocal_rank_fusion

    vec = [_hit("d1#0", "d1", 0.9, "vector"), _hit("d2#0", "d2", 0.8, "vector")]
    bm25 = [_hit("d2#0", "d2", 12.0, "bm25"), _hit("d3#0", "d3", 9.0, "bm25")]
    out = reciprocal_rank_fusion(vec, bm25)
    assert out[0]["id"] == "d2#0"          # 双路命中者排第一
    got = {o["id"]: o["score"] for o in out}
    assert got["d2#0"] > got["d1#0"] and got["d2#0"] > got["d3#0"]


def test_namespace_mismatch_degrades_fusion_to_union():
    """修复前：向量路用 DB 主键、BM25 路用 `{doc_id}#{index}` → 得分无法相加。

    融合退化为「先列完全部向量结果，再接上 BM25 结果」，
    BM25 独有的正确文档被挤到所有向量结果之后，超出截断线。
    修复后 id 对齐，双路命中的 chunk 立刻上升到第 1。
    """
    from app.rag.hybrid import reciprocal_rank_fusion

    # 修复前：两路 id 处于不同命名空间，永远无法合并
    mismatched_vec = [_hit(f"pk-{i}", f"wrong{i}", 0.9 - i * 0.01, "vector") for i in range(5)]
    bm25 = [_hit("d1#0", "d1", 99.0, "bm25")]
    legacy = reciprocal_rank_fusion(mismatched_vec, bm25)
    assert [o["doc_id"] for o in legacy[:5]] == [f"wrong{i}" for i in range(5)]  # d1 被挤出
    assert legacy[-1]["doc_id"] == "d1"

    # 修复后：id 命名空间对齐，双路命中的 chunk 得分相加 → 跃居第 1
    aligned_vec = [_hit(f"wrong{i}#0", f"wrong{i}", 0.9 - i * 0.01, "vector")
                   for i in range(5)] + [_hit("d1#0", "d1", 0.2, "vector")]
    fixed = reciprocal_rank_fusion(aligned_vec, bm25)
    assert fixed[0]["doc_id"] == "d1"


def test_score_norm_bounds_and_scale_invariance():
    """score_norm 逐通道 min-max 归一化：量纲不同的两路不会互相压制。

    向量通道分数在 0~1，BM25 分数在 0~100。若直接比较原始分数，
    BM25 会无条件碾压；归一化后两路各自最大值为 1，权重才真正起作用。
    """
    from app.rag.hybrid import score_norm_fusion

    vec = [_hit("a#0", "a", 0.9, "vector"), _hit("b#0", "b", 0.1, "vector")]
    bm25 = [_hit("c#0", "c", 100.0, "bm25"), _hit("d#0", "d", 1.0, "bm25")]

    sn = score_norm_fusion(vec, bm25, vector_weight=0.5, bm25_weight=0.5)
    got = {o["id"]: o["score"] for o in sn}
    assert got["a#0"] == 0.5 and got["c#0"] == 0.5    # 各自通道第 1 名 → 权重满分
    assert got["b#0"] == 0.0 and got["d#0"] == 0.0    # 通道末位 → 不贡献
    assert all(0.0 <= s <= 1.0 for s in got.values())  # 分数被约束在权重范围内


def test_score_norm_single_item_channel_has_no_signal():
    """通道只有 1 条结果时无区分度 → 归一化为 0，不参与排序（避免单条结果被高估）。"""
    from app.rag.hybrid import score_norm_fusion

    vec = [_hit("a#0", "a", 0.9, "vector")]
    bm25 = [_hit("b#0", "b", 5.0, "bm25"), _hit("c#0", "c", 1.0, "bm25")]
    got = {o["id"]: o["score"] for o in score_norm_fusion(vec, bm25)}
    assert got["a#0"] == 0.0 and got["b#0"] == 0.4    # 只有 BM25 通道提供区分度


def test_minmax_uniform_channel_yields_zero_signal():
    from app.rag.hybrid import _minmax
    assert _minmax([3.0, 3.0, 3.0]) == [0.0, 0.0, 0.0]   # 全等 → 无区分度
    assert _minmax([0.0, 5.0, 10.0]) == [0.0, 0.5, 1.0]
    assert _minmax([]) == []


def test_fuse_dispatches_by_configured_mode():
    from app.config import settings
    from app.rag.hybrid import FUSION_RRF, FUSION_SCORE_NORM, fuse

    vec = [_hit("a#0", "a", 0.9, "vector"), _hit("b#0", "b", 0.1, "vector")]
    bm25 = [_hit("c#0", "c", 100.0, "bm25"), _hit("d#0", "d", 1.0, "bm25")]
    old = settings.rag_fusion_mode
    try:
        settings.rag_fusion_mode = FUSION_RRF
        rrf_top = fuse(vec, bm25)[0]["score"]
        assert rrf_top < 0.05          # RRF 分数是 1/(k+rank) 量级，与权重无关
        settings.rag_fusion_mode = FUSION_SCORE_NORM
        assert fuse(vec, bm25)[0]["score"] >= 0.5   # 归一化后接近权重上限
    finally:
        settings.rag_fusion_mode = old


# ── Provider key 池（服务端托管 key，不再是 BYOK 用户自带 key）────────────

def test_provider_key_pool_isolation_and_hash():
    """旧实现：单槽缓存 _client/_current_key，多 provider 路由切换会互相覆盖 client。

    新实现：按 (api_key, base_url) 哈希分池，互不干扰，池内不存明文密钥。
    """
    from app.llm import UnifiedLLMClient

    c = UnifiedLLMClient()
    k1 = c._pool_key("sk-provider-a", "https://api.deepseek.com/v1")
    k2 = c._pool_key("sk-provider-b", "https://api.deepseek.com/v1")
    assert k1 != k2
    assert "sk-provider-a" not in k1 and len(k1) == 64   # sha256 十六进制

    # 同一 key 复用同一 client；不同 key 得到不同 client
    a1 = c._acquire("sk-provider-a", "https://api.deepseek.com/v1")
    a2 = c._acquire("sk-provider-a", "https://api.deepseek.com/v1")
    b1 = c._acquire("sk-provider-b", "https://api.deepseek.com/v1")
    assert a1 is a2 and a1 is not b1 and len(c._pool) == 2


def test_provider_key_pool_lru_eviction():
    from app.llm import UnifiedLLMClient

    c = UnifiedLLMClient()
    c._pool_max = 3
    for i in range(5):
        c._acquire(f"sk-provider-{i}", "https://api.deepseek.com/v1")
    assert len(c._pool) == 3        # 超出上限按 LRU 淘汰，密钥不会无限累积
