"""
异步任务队列（asyncio.Queue + 后台 Worker）。

为什么自己实现而不是用 Celery
~~~~~~~~~~~~~~~~~~~~~~~~~~
- Celery 是重量级组件（额外进程、消息中间件、broker 协议），对本项目规模（万级用户 / 百人并发）过度
- asyncio.Queue + 后台 worker 已能满足所有场景：
    - 高优先级任务（出题 / 追问）走小队列、低延迟
    - 后台任务（评测 / 知识库入库）走大队列、高吞吐
- 不引入 broker 依赖意味着部署简单（无需 RabbitMQ / Redis pub-sub）
- 单进程内任务调度，跨进程 / 跨机器需扩 Redis broker —— 这是 M2 之外的范畴

设计
~~~~
- Task dataclass：函数名 + 参数 + 元数据（用户 id、任务类型、优先级）
- TaskQueue：按优先级分桶 + asyncio.Queue 排队
- Worker：daemon 协程，从队列消费任务，调用对应的处理器
- 处理器注册：模块加载时通过 `register_handler(task_kind, async_fn)` 注册
"""
from __future__ import annotations

import asyncio
import inspect
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from loguru import logger

from app.config import settings


@dataclass
class Task:
    """异步任务描述。"""
    kind: str                       # 任务类型（决定 handler）
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5               # 0=最高，9=最低；默认 5=普通
    enqueued_at: float = field(default_factory=time.time)
    user_id: int = 0
    request_id: str = ""
    timeout_s: float = 30.0

    @property
    def age_s(self) -> float:
        return time.time() - self.enqueued_at


HandlerFn = Callable[..., Awaitable[Any]]


class TaskQueue:
    """异步任务队列（按优先级分桶 + 并发 worker）。"""

    def __init__(self, *, max_size: int = 10000, concurrency: int = 8) -> None:
        self._buckets: Dict[int, asyncio.Queue] = {
            p: asyncio.Queue(maxsize=max_size // 10) for p in range(10)
        }
        self._handlers: Dict[str, HandlerFn] = {}
        self._workers: List[asyncio.Task] = []
        self._stop_event: Optional[asyncio.Event] = None
        self._concurrency = concurrency
        # 统计
        self.total_enqueued = 0
        self.total_processed = 0
        self.total_failed = 0

    def register_handler(self, kind: str, fn: HandlerFn) -> None:
        self._handlers[kind] = fn

    async def enqueue(self, task: Task) -> bool:
        """入队。False 表示队列已满。"""
        bucket = self._buckets.get(task.priority)
        if bucket is None:
            raise ValueError(f"无效优先级 {task.priority}")
        try:
            bucket.put_nowait(task)
        except asyncio.QueueFull:
            logger.warning("任务队列已满 (priority={}): kind={} uid={}",
                           task.priority, task.kind, task.user_id)
            return False
        self.total_enqueued += 1
        return True

    async def _worker(self, name: str) -> None:
        """单 worker：按优先级从各桶轮询拉取任务。"""
        logger.info("任务 worker {} 已启动", name)
        while not (self._stop_event and self._stop_event.is_set()):
            task = await self._poll_task()
            if task is None:
                await asyncio.sleep(0.01)
                continue
            handler = self._handlers.get(task.kind)
            if handler is None:
                logger.warning("无任务 handler: kind={}", task.kind)
                self.total_failed += 1
                continue
            try:
                if task.timeout_s > 0:
                    await asyncio.wait_for(
                        handler(*task.args, **task.kwargs),
                        timeout=task.timeout_s,
                    )
                else:
                    await handler(*task.args, **task.kwargs)
                self.total_processed += 1
            except asyncio.TimeoutError:
                self.total_failed += 1
                logger.warning("任务超时（{:.1f}s）: kind={} uid={}",
                               task.timeout_s, task.kind, task.user_id)
            except Exception as e:  # noqa: BLE001
                self.total_failed += 1
                logger.error("任务失败: kind={} uid={} error={}\n{}",
                             task.kind, task.user_id, e, traceback.format_exc())
        logger.info("任务 worker {} 已停止", name)

    async def _poll_task(self) -> Optional[Task]:
        """按优先级 0→9 轮询拉取，公平避免高优先级独占。"""
        for prio in range(10):
            bucket = self._buckets[prio]
            try:
                return bucket.get_nowait()
            except asyncio.QueueEmpty:
                continue
        return None

    async def start(self) -> None:
        if self._workers:
            return
        self._stop_event = asyncio.Event()
        self._workers = [
            asyncio.create_task(self._worker(f"worker-{i}"), name=f"worker-{i}")
            for i in range(self._concurrency)
        ]

    async def stop(self) -> None:
        if not self._workers:
            return
        if self._stop_event:
            self._stop_event.set()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._stop_event = None
        logger.info("任务队列已停止（processed={} failed={}）",
                    self.total_processed, self.total_failed)

    def stats(self) -> Dict[str, Any]:
        return {
            "enqueued": self.total_enqueued,
            "processed": self.total_processed,
            "failed": self.total_failed,
            "workers": len(self._workers),
            "depth": {p: self._buckets[p].qsize() for p in range(10)},
        }


# ── 全局实例 ──────────────────────────────────────────────────────
_queue: Optional[TaskQueue] = None


def get_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        _queue = TaskQueue(
            max_size=settings.task_queue_max_size,
            concurrency=settings.task_queue_concurrency,
        )
    return _queue


def register(kind: str) -> Callable[[HandlerFn], HandlerFn]:
    """装饰器：注册任务 handler。

    用法：
        @register("kb_index")
        async def index_doc(doc_id: int): ...
    """
    def decorator(fn: HandlerFn) -> HandlerFn:
        get_queue().register_handler(kind, fn)
        return fn
    return decorator


async def enqueue(kind: str, *args, user_id: int = 0, request_id: str = "",
                  priority: int = 5, timeout_s: float = 30.0,
                  **kwargs) -> bool:
    """便捷入队。"""
    return await get_queue().enqueue(Task(
        kind=kind, args=args, kwargs=kwargs,
        user_id=user_id, request_id=request_id,
        priority=priority, timeout_s=timeout_s,
    ))


async def start_workers() -> None:
    await get_queue().start()


async def stop_workers() -> None:
    await get_queue().stop()