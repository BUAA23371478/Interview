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

    def save_snapshot(self, session_id: str, state: Dict[str, Any]) -> None:
        """保存会话状态快照。"""
        try:
            data = json.dumps(_safe_serialize(state), ensure_ascii=False)
        except (TypeError, ValueError):
            data = json.dumps({})
        r = self._ensure()
        if r:
            r.set(f"iam:short:{session_id}:snapshot", data, ex=settings.redis_short_term_ttl)
        else:
            self._mem_store[f"{session_id}:snapshot"] = {
                "data": data,
                "expire": settings.redis_short_term_ttl,
            }

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
            return sanitize_state(json.loads(data))
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
            for suffix in ("snapshot", "turns"):
                r.delete(f"iam:short:{session_id}:{suffix}")
        else:
            self._mem_store.pop(f"{session_id}:snapshot", None)
            self._mem_store.pop(f"{session_id}:turns", None)


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
