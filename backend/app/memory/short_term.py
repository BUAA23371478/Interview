"""
短期会话存储：Redis（可选）→ 内存 dict 回退。

状态快照 + 对话轮次，TTL 24h。从 Redis 加载后做类型修正（_sanitize_state）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from app.config import settings

BOOL_FIELDS = ["interview_finished", "awaiting_answer", "awaiting_evaluation",
               "should_followup", "force_finish", "is_followup"]
INT_FIELDS = ["current_question_idx", "followup_count", "max_followup",
              "total_questions", "consecutive_correct", "consecutive_wrong", "total_rounds"]


def _coerce_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)


def sanitize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """修正 Redis JSON 往返后的字段类型。"""
    for f in BOOL_FIELDS:
        if f in state:
            state[f] = _coerce_bool(state[f])
    for f in INT_FIELDS:
        if f in state:
            try:
                state[f] = int(state[f])
            except (TypeError, ValueError):
                state[f] = 0
    return state


class ShortTermMemory:
    """短期会话记忆。"""

    def __init__(self) -> None:
        self._redis: Optional[Any] = None
        self._mem_store: Dict[str, Dict[str, Any]] = {}
        self._available: Optional[bool] = None

    def _ensure(self) -> Any:
        """惰性连接 Redis，失败则使用内存。"""
        if self._available is True:
            return self._redis
        if self._available is False:
            return None
        try:
            import redis as redis_mod
            r = redis_mod.Redis(
                host=settings.redis_host, port=settings.redis_port,
                password=settings.redis_password, db=settings.redis_db,
                decode_responses=True, socket_connect_timeout=3,
            )
            r.ping()
            self._redis = r
            self._available = True
            logger.info("Redis 短期记忆已连接")
        except Exception as e:  # noqa: BLE001
            self._available = False
            logger.warning("Redis 不可用，短期记忆使用内存模式：{}", e)
        return self._redis

    def save_snapshot(self, session_id: str, state: Dict[str, Any],
                      expected_version: Optional[int] = None) -> bool:
        """保存会话状态快照（带乐观锁 CAS）。

        并发场景：同一会话被两个请求同时读改写时，后写者会覆盖前写者，
        导致「答题记录丢失 / 题目跳变」。这里用版本号做 CAS：

        - `expected_version` 为 None → 无条件写（初始化等场景）；
        - 否则比对存储中的当前版本，不一致即拒绝写入并返回 False，
          调用方据此返回 409，让客户端重试而不是静默丢数据。
        """
        try:
            data = json.dumps(_safe_serialize(state), ensure_ascii=False)
        except (TypeError, ValueError):
            data = json.dumps({})
        ver = int(state.get("_version") or 0)
        r = self._ensure()
        if r:
            return self._cas_redis(r, session_id, data, ver, expected_version)
        return self._cas_memory(session_id, data, ver, expected_version)

    def _cas_redis(self, r: Any, session_id: str, data: str,
                   ver: int, expected_version: Optional[int]) -> bool:
        """Redis WATCH/MULTI 实现原子 CAS。"""
        snap_key = f"iam:short:{session_id}:snapshot"
        ver_key = f"iam:short:{session_id}:ver"
        ttl = settings.redis_short_term_ttl
        try:
            with r.pipeline() as pipe:
                pipe.watch(ver_key)
                cur = pipe.get(ver_key)
                cur = int(cur) if cur is not None else 0
                if expected_version is not None and cur != expected_version:
                    pipe.unwatch()
                    logger.warning("会话 {} 版本冲突：期望 {} 实际 {}，拒绝写入",
                                   session_id, expected_version, cur)
                    return False
                pipe.multi()
                pipe.set(snap_key, data, ex=ttl)
                pipe.set(ver_key, cur + 1, ex=ttl)
                pipe.execute()
            return True
        except Exception as e:  # noqa: BLE001
            from redis.exceptions import WatchError
            if isinstance(e, WatchError):
                logger.warning("会话 {} CAS 检测到并发写，拒绝写入", session_id)
                return False
            logger.warning("保存会话快照失败: {}", e)
            return False

    def _cas_memory(self, session_id: str, data: str, ver: int,
                    expected_version: Optional[int]) -> bool:
        cur = self._mem_store.get(f"{session_id}:ver")
        cur = int(cur) if cur is not None else 0
        if expected_version is not None and cur != expected_version:
            logger.warning("会话 {} 版本冲突：期望 {} 实际 {}，拒绝写入",
                           session_id, expected_version, cur)
            return False
        self._mem_store[f"{session_id}:snapshot"] = {
            "data": data,
            "expire": settings.redis_short_term_ttl,
        }
        self._mem_store[f"{session_id}:ver"] = cur + 1
        return True

    def version(self, session_id: str) -> int:
        """读取会话当前版本号（无则 0）。"""
        r = self._ensure()
        try:
            if r:
                v = r.get(f"iam:short:{session_id}:ver")
                return int(v) if v is not None else 0
        except Exception as e:  # noqa: BLE001
            logger.warning("读取会话版本失败: {}", e)
        v = self._mem_store.get(f"{session_id}:ver")
        return int(v) if v is not None else 0

    def load_snapshot(self, session_id: str) -> Dict[str, Any]:
        r = self._ensure()
        try:
            if r:
                data = r.get(f"iam:short:{session_id}:snapshot")
            else:
                item = self._mem_store.get(f"{session_id}:snapshot")
                data = item["data"] if item else None
            if not data:
                return {}
            state = sanitize_state(json.loads(data))
            # 注入乐观锁版本号，供后续 CAS 写回校验
            state["_version"] = self.version(session_id)
            return state
        except Exception as e:  # noqa: BLE001
            logger.warning("加载会话快照失败: {}", e)
            return {}

    def append_turn(self, session_id: str, role: str, content: str, max_turns: int = 20) -> None:
        item = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        r = self._ensure()
        key = f"iam:short:{session_id}:turns"
        if r:
            r.rpush(key, item)
            r.ltrim(key, -max_turns, -1)
            r.expire(key, settings.redis_short_term_ttl)
        else:
            turns = self._mem_store.setdefault(f"{session_id}:turns", [])
            turns.append(item)
            del turns[:-max_turns]

    def load_turns(self, session_id: str) -> List[Dict[str, str]]:
        r = self._ensure()
        try:
            if r:
                items = r.lrange(f"iam:short:{session_id}:turns", 0, -1)
            else:
                items = self._mem_store.get(f"{session_id}:turns", [])
            out = []
            for it in items:
                try:
                    out.append(json.loads(it))
                except (TypeError, ValueError):
                    continue
            return out
        except Exception as e:  # noqa: BLE001
            logger.warning("加载对话轮次失败: {}", e)
            return []

    def clear(self, session_id: str) -> None:
        r = self._ensure()
        if r:
            for suffix in ("snapshot", "turns", "ver"):
                r.delete(f"iam:short:{session_id}:{suffix}")
        else:
            self._mem_store.pop(f"{session_id}:snapshot", None)
            self._mem_store.pop(f"{session_id}:turns", None)
            self._mem_store.pop(f"{session_id}:ver", None)


def _safe_serialize(obj: Any) -> Any:
    """把不可 JSON 序列化的对象转成字符串。"""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}
    return str(obj)


short_term_memory = ShortTermMemory()
