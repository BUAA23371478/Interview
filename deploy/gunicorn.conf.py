"""
Gunicorn 多 worker 启动配置。

启动：
    gunicorn -c deploy/gunicorn.conf.py app.main:app

Worker 模型
~~~~~~~~~~~
- class="uvicorn.workers.UvicornWorker"：保留 uvicorn 的 asyncio 事件循环
  （gunicorn 同步 worker 会阻塞 asyncio 协程，绝不能用）
- workers = (CPU * 2) + 1：业界经验公式
- worker_tmp_dir：解决 gunicorn + preload + 临时目录回收的 bug
- keepalive=30：与 Nginx upstream 一致
- max_requests + max_requests_jitter：worker 周期性重启，防止内存累积

与 asyncio.Queue 的关系
~~~~~~~~~~~~~~~~~~~~
asyncio.Queue 是**进程内**的——多 worker 之间不共享。
本项目的任务队列已经按 worker 数量自然拆分；如需跨进程共享请加 Redis broker（M3 之后再说）。
"""
import multiprocessing
import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8002")
workers = int(os.getenv("GUNICORN_WORKERS", str((multiprocessing.cpu_count() * 2) + 1)))
worker_class = "uvicorn.workers.UvicornWorker"
worker_tmp_dir = "/dev/shm" if os.path.exists("/dev/shm") else "/tmp"
keepalive = 30
timeout = 60
graceful_timeout = 30
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
preload_app = False  # 关闭预加载以避免 asyncio 状态跨进程问题

# Worker 启动钩子
def on_starting(server):  # noqa: ARG001
    pass


def post_fork(server, worker):  # noqa: ARG001
    server.log.info("Worker %s spawned (pid=%s)", worker.age, worker.pid)


def worker_int(worker):  # noqa: ARG001
    worker.log.info("Worker %s received SIGINT", worker.age)


def worker_abort(worker):  # noqa: ARG001
    worker.log.warning("Worker %s aborted", worker.age)