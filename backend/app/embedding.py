"""
Embedding 客户端（OpenAI 兼容 /embeddings）。

生产级关键设计（每一条都对应一个真实踩过的坑）：

1. **绝不「投毒」**：API 可用但调用失败时，返回 None 并进入冷却期，
   通道降级为纯关键词检索——**不会**把 mock 向量写进索引。
   把 256 维随机哈希向量混进 1024 维真实语义索引，会让检索「能跑、有结果、
   但排序完全错误」，比拒绝服务更危险（无人察觉的静默质量崩塌）。
   仅在**完全未配置 Key**（本地 demo / 单测）时才使用 mock 向量。

2. **磁盘向量缓存**：key = sha256(model + text)。语料重建、A/B 复测、参数网格搜索
   会反复 embedding 同一批文本，命中缓存后重复调用降为 0——这是能把评测迭代
   成本与时间压下来的前提。

3. **切批 + 并发 + 自适应降批**：服务商对单请求文本数有硬上限（bge-m3 为 64），
   超限整批 400。因此内部按 embedding_batch_size 切批并发发送；
   遇到 400 自动对半拆分重试（而不是整批失败），对 429/5xx 走退避重试。

4. **失败不永久降级**：冷却期结束后自动恢复真实调用，不会一个瞬时错误
   让整个进程余生都用假向量。

5. **维度显式校验**：维度变化直接报错要求重建索引，绝不静默截断。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import sqlite3
import struct
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import httpx
from loguru import logger

from app.config import settings

MOCK_DIM = 256
MAGIC_F32 = b"F32/"
MAGIC_F64 = b"F64/"


class EmbeddingUnavailable(RuntimeError):
    """Embedding 服务不可用。索引写入场景必须让调用方知道，不能静默降级。"""


def _mock_embed(text: str) -> List[float]:
    """确定性 mock：从文本哈希派生一个 256 维单位向量。

    仅在**完全未配置 API Key**时使用（本地 demo / 单测）。
    绝不允许作为「真实调用失败」的兜底。
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [float(b) for b in digest]
    while len(vec) < MOCK_DIM:
        digest = hashlib.sha256(digest + text.encode("utf-8")).digest()
        vec.extend(float(b) for b in digest)
    vec = vec[:MOCK_DIM]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


# ── 磁盘向量缓存 ─────────────────────────────────────────────────────
class VectorDiskCache:
    """SQLite 持久化向量缓存（可跨进程复用，支撑评测迭代不重复计费）。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.enabled = False
        self.hits = 0
        self.misses = 0
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._connect()
            conn.execute(
                "CREATE TABLE IF NOT EXISTS vec ("
                "  k TEXT PRIMARY KEY,"
                "  dim INTEGER NOT NULL,"
                "  v BLOB NOT NULL,"
                "  ts REAL NOT NULL)"
            )
            conn.commit()
            conn.close()
            self.enabled = True
        except Exception as e:  # noqa: BLE001
            logger.warning("向量缓存初始化失败（将退化为仅内存缓存）: {}", e)
            self.enabled = False

    @staticmethod
    def key(model: str, text: str) -> str:
        h = hashlib.sha256(f"{model}\x00{text}".encode("utf-8")).hexdigest()
        return h

    def get_many(self, keys: Sequence[str]) -> Dict[str, List[float]]:
        if not self.enabled or not keys:
            return {}
        out: Dict[str, List[float]] = {}
        try:
            conn = self._connect()
            try:
                # 分批查询，避免 SQLite 变量数上限（默认 999）
                for i in range(0, len(keys), 500):
                    part = keys[i:i + 500]
                    marks = ",".join("?" * len(part))
                    for k, blob in conn.execute(
                            f"SELECT k, v FROM vec WHERE k IN ({marks})", list(part)):
                        out[k] = unpack_vector(blob)
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("向量缓存读取失败: {}", e)
        self.hits += len(out)
        self.misses += len(keys) - len(out)
        return out

    def put_many(self, items: Sequence[Tuple[str, int, List[float]]]) -> None:
        if not self.enabled or not items:
            return
        try:
            conn = self._connect()
            try:
                now = time.time()
                conn.executemany(
                    "INSERT OR REPLACE INTO vec (k, dim, v, ts) VALUES (?, ?, ?, ?)",
                    [(k, dim, pack_vector(vec), now) for k, dim, vec in items],
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("向量缓存写入失败: {}", e)

    def stats(self) -> Dict[str, object]:
        size = 0
        if self.enabled:
            try:
                conn = self._connect()
                size = conn.execute("SELECT COUNT(*) FROM vec").fetchone()[0]
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        return {"enabled": self.enabled, "rows": size,
                "hits": self.hits, "misses": self.misses,
                "file": str(self.path)}


def _cache_path() -> Path:
    if settings.embedding_cache_db:
        p = Path(settings.embedding_cache_db)
        from app.config import BACKEND_DIR
        return p if p.is_absolute() else (BACKEND_DIR.parent / p)
    return settings.data_dir / "embed_cache.db"


# ── 客户端 ───────────────────────────────────────────────────────────
class EmbeddingClient:
    """统一嵌入客户端。

    两种降级语义必须区分清楚：
      - **未配置 Key** → mock 模式（本地 demo 可用，日志明确告警）；
      - **配置了 Key 但调用失败** → 进入冷却期、返回 None（上层降级为纯 BM25），
        冷却结束自动恢复真实调用。
    """

    def __init__(self) -> None:
        self._api_key = (settings.embedding_api_key or "").strip() or settings.llm_api_key
        self._base_url = settings.embedding_base_url.rstrip("/")
        self._model = settings.embedding_model
        self._dimension: Optional[int] = None
        self._fail_until: float = 0.0
        self._fail_reason: str = ""
        self._cache: "OrderedDict[str, Tuple[float, List[float]]]" = OrderedDict()
        self._cache_max = max(0, settings.embedding_cache_size)
        self._cache_ttl = settings.embedding_cache_ttl
        self._disk = VectorDiskCache(_cache_path())
        self._sem = asyncio.Semaphore(max(1, settings.embedding_concurrency))
        self._stats = {"hit_mem": 0, "hit_disk": 0, "api_calls": 0, "api_texts": 0,
                       "fail": 0, "mock": 0, "split_retry": 0}
        self._warned_mock = False

    # ── 状态 ────────────────────────────────────────────────────────
    @property
    def mock_mode(self) -> bool:
        """未配置任何 Key：本地 demo 模式（会使用 mock 向量）。"""
        return not self._api_key

    @property
    def cooling_down(self) -> bool:
        return time.time() < self._fail_until

    @property
    def enabled(self) -> bool:
        """真实语义能力当前是否可用。"""
        return not self.mock_mode and not self.cooling_down

    @property
    def dimension(self) -> Optional[int]:
        return self._dimension

    @property
    def stats(self) -> Dict[str, object]:
        total = self._stats["hit_mem"] + self._stats["hit_disk"]
        lookups = total + self._stats["api_texts"] + self._stats["mock"]
        out: Dict[str, object] = dict(self._stats)
        out.update({
            "model": self._model,
            "dimension": self._dimension,
            "mock_mode": self.mock_mode,
            "cooling_down": self.cooling_down,
            "cooldown_left_s": round(max(0.0, self._fail_until - time.time()), 1),
            "fail_reason": self._fail_reason,
            "cache_lookups": lookups,
            "cache_hit_rate": round(total / lookups, 4) if lookups else 0.0,
            "disk": self._disk.stats(),
        })
        return out

    def _enter_cooldown(self, exc: Exception) -> None:
        self._fail_until = time.time() + settings.embedding_cooldown
        self._fail_reason = f"{type(exc).__name__}: {exc}"
        self._stats["fail"] += 1
        logger.warning("Embedding API 失败，进入 {}s 冷却（期间向量通道关闭，"
                       "检索自动降级为纯关键词）: {}",
                       settings.embedding_cooldown, self._fail_reason)

    def _record_dim(self, dim: int) -> None:
        if self._dimension is None:
            self._dimension = dim
            logger.info("Embedding 维度探测: {} 维（模型 {}）", dim, self._model)
        elif self._dimension != dim:
            logger.error("Embedding 维度变化: {} -> {}（向量索引需重建）",
                         self._dimension, dim)

    # ── 内存 LRU ────────────────────────────────────────────────────
    def _mem_get(self, text: str) -> Optional[List[float]]:
        if self._cache_max <= 0:
            return None
        item = self._cache.get(text)
        if item is None:
            return None
        ts, vec = item
        if time.time() - ts > self._cache_ttl:
            self._cache.pop(text, None)
            return None
        self._cache.move_to_end(text)
        return vec

    def _mem_put(self, text: str, vec: List[float]) -> None:
        if self._cache_max <= 0:
            return
        self._cache[text] = (time.time(), vec)
        self._cache.move_to_end(text)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    # ── 单条接口 ────────────────────────────────────────────────────
    async def embed(self, text: str) -> Optional[List[float]]:
        """单条嵌入。返回 None 表示当前不可用（调用方应降级为纯关键词检索）。"""
        got = await self.embed_many([text])
        return got[0] if got else None

    async def embed_required(self, text: str) -> List[float]:
        """单条嵌入，不可用则抛错（索引写入场景用它，避免落库半截数据）。"""
        vec = await self.embed(text)
        if not vec:
            raise EmbeddingUnavailable(
                "Embedding 服务不可用，拒绝写入向量索引（避免污染索引）。"
                f" 原因: {self._fail_reason or '未配置 API Key'}"
            )
        return vec

    # ── 批量接口 ────────────────────────────────────────────────────
    async def embed_many(self, texts: Sequence[str]) -> List[Optional[List[float]]]:
        """批量嵌入，尽力而为。返回与输入等长的列表，不可用位置为 None。

        流程：内存LRU → 磁盘缓存 → 切批并发调用 → 回写两层缓存。
        """
        if not texts:
            return []
        out: List[Optional[List[float]]] = [None] * len(texts)

        # 1) 内存缓存
        pending: List[int] = []
        for i, t in enumerate(texts):
            hit = self._mem_get(t)
            if hit is not None:
                self._stats["hit_mem"] += 1
                out[i] = hit
            else:
                pending.append(i)

        # 2) 磁盘缓存（去重后查）
        if pending and self._disk.enabled:
            uniq = {texts[i]: None for i in pending}
            keys = {VectorDiskCache.key(self._model, t): t for t in uniq}
            found = await asyncio.to_thread(self._disk.get_many, list(keys.keys()))
            for k, vec in found.items():
                t = keys.get(k)
                if t is not None:
                    uniq[t] = vec
            still: List[int] = []
            for i in pending:
                vec = uniq.get(texts[i])
                if vec is not None:
                    self._stats["hit_disk"] += 1
                    self._mem_put(texts[i], vec)
                    out[i] = vec
                else:
                    still.append(i)
            pending = still

        # 3) 未配置 Key：mock 模式（仅本地 demo/单测）
        if self.mock_mode:
            if not self._warned_mock:
                logger.warning("未配置 EMBEDDING_API_KEY，使用 mock 向量（维度 {}，"
                               "无语义能力，仅适用于本地演示与单元测试）", MOCK_DIM)
                self._warned_mock = True
            for i in pending:
                self._stats["mock"] += 1
                v = _mock_embed(texts[i])
                self._mem_put(texts[i], v)
                out[i] = v
            return out

        # 4) 冷却期内：直接返回 None，不再打外部 API
        if self.cooling_down:
            return out

        # 5) 真正需要调用的文本（去重，避免同一批里重复文本重复计费）
        todo_map: "OrderedDict[str, List[int]]" = OrderedDict()
        for i in pending:
            todo_map.setdefault(texts[i], []).append(i)
        todo = list(todo_map.keys())
        if not todo:
            return out

        got = await self._embed_remote(todo)
        for t, vec in got.items():
            if vec is None:
                continue
            self._mem_put(t, vec)
            for i in todo_map[t]:
                out[i] = vec
        # 磁盘回写（只写成功的）
        writes = [(VectorDiskCache.key(self._model, t), len(v), v)
                  for t, v in got.items() if v]
        if writes:
            await asyncio.to_thread(self._disk.put_many, writes)
        return out

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """兼容旧调用名。"""
        return await self.embed_many(texts)

    # ── 远程调用（切批 + 并发 + 退避 + 自适应降批）────────────────────
    async def _embed_remote(self, texts: List[str]) -> Dict[str, Optional[List[float]]]:
        batch_size = max(1, settings.embedding_batch_size)
        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
        results: Dict[str, Optional[List[float]]] = {}

        async with httpx.AsyncClient(timeout=settings.llm_timeout,
                                     limits=httpx.Limits(max_connections=16)) as client:
            async def run(batch: List[str]) -> None:
                async with self._sem:
                    got = await self._post_embeddings(client, batch)
                for t in batch:
                    results[t] = None
                if got is not None:
                    for t, v in zip(batch, got):
                        results[t] = v
                    self._stats["api_texts"] += len(batch)

            await asyncio.gather(*(run(b) for b in batches), return_exceptions=True)

        if all(v is None for v in results.values()) and texts:
            self._enter_cooldown(RuntimeError("全部批次调用失败"))
        return results

    async def _post_embeddings(self, client: httpx.AsyncClient,
                               batch: List[str]) -> Optional[List[List[float]]]:
        """发一批；对 429/5xx 退避重试，对 400 自动对半拆分（而非整批失败）。"""
        url = f"{self._base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self._api_key}",
                   "Content-Type": "application/json"}
        max_retries = max(1, settings.embedding_max_retries)

        for attempt in range(max_retries):
            try:
                self._stats["api_calls"] += 1
                resp = await client.post(url, headers=headers,
                                         json={"model": self._model, "input": batch})
                if resp.status_code == 400 and len(batch) > 1:
                    # 服务商对该批的规模/内容不满意：对半拆分，递归处理
                    self._stats["split_retry"] += 1
                    mid = len(batch) // 2
                    left = await self._post_embeddings(client, batch[:mid])
                    right = await self._post_embeddings(client, batch[mid:])
                    if left is None or right is None:
                        return None
                    return left + right
                if resp.status_code in (408, 409, 425, 429) or resp.status_code >= 500:
                    if attempt == max_retries - 1:
                        logger.warning("Embedding 批次失败（重试耗尽）: HTTP {}", resp.status_code)
                        return None
                    delay = min(8.0, 0.5 * (2 ** attempt)) * (0.5 + random.random())
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                data = resp.json().get("data") or []
                if len(data) != len(batch):
                    logger.warning("Embedding 返回条数不匹配: 期望 {} 实得 {}",
                                   len(batch), len(data))
                    return None
                ordered = sorted(data, key=lambda x: x.get("index", 0))
                vectors = [it["embedding"] for it in ordered]
                self._record_dim(len(vectors[0]))
                return vectors
            except httpx.HTTPStatusError as e:
                code = e.response.status_code if e.response is not None else 0
                if code >= 400 and code < 500 and code != 429:
                    logger.error("Embedding 请求被拒绝 HTTP {}: {}",
                                 code, (e.response.text or "")[:200])
                    return None
                if attempt == max_retries - 1:
                    return None
                await asyncio.sleep(min(8.0, 0.5 * (2 ** attempt)))
            except Exception as e:  # noqa: BLE001
                if attempt == max_retries - 1:
                    logger.warning("Embedding 调用异常（重试耗尽）: {}", e)
                    return None
                await asyncio.sleep(min(8.0, 0.5 * (2 ** attempt)))
        return None

    # ── 探活 ────────────────────────────────────────────────────────
    async def probe(self) -> Dict[str, object]:
        """真实探活一次，用于 CI / 启动自检 / 报告取证。"""
        if self.mock_mode:
            return {"ok": False, "model": self._model, "dimension": MOCK_DIM,
                    "error": "未配置 API Key，运行在 mock 模式"}
        t0 = time.perf_counter()
        vec = await self.embed("探活：混合检索与向量召回")
        dt = (time.perf_counter() - t0) * 1000
        if not vec:
            return {"ok": False, "model": self._model, "dimension": self._dimension,
                    "error": self._fail_reason or "调用失败", "latency_ms": round(dt, 1)}
        return {"ok": True, "model": self._model, "dimension": len(vec),
                "latency_ms": round(dt, 1)}

    def test_connection(self) -> dict:
        """同步版状态查询（不发起网络调用），保留以兼容既有调用方。"""
        if self.mock_mode:
            return {"ok": False, "model": self._model, "dimension": MOCK_DIM,
                    "error": "未配置 API Key，运行在 mock 模式"}
        if self.cooling_down:
            return {"ok": False, "model": self._model,
                    "dimension": self._dimension or MOCK_DIM,
                    "error": f"API 处于冷却期（{settings.embedding_cooldown}s 后自动重试）"}
        return {"ok": True, "model": self._model, "dimension": self._dimension}


# ── 向量序列化：带格式头，兼容历史 float64 数据 ────────────────────────
def pack_vector(vec: List[float], dtype: str = "float32") -> bytes:
    """向量 → BLOB。

    float32 相比 float64 体积减半（1024 维 4KB vs 8KB），
    反序列化与内存拷贝开销同步减半；精度损失对余弦排序无实质影响。
    头部 4 字节魔数区分格式，历史无头数据按 float64 解析（向后兼容）。
    """
    n = len(vec)
    if dtype == "float64":
        return MAGIC_F64 + struct.pack(f">{n}d", *vec)
    return MAGIC_F32 + struct.pack(f">{n}f", *vec)


def unpack_vector(blob: bytes) -> List[float]:
    """BLOB → 向量（自动识别 float32 / float64 / 历史无头格式）。"""
    if blob[:4] == MAGIC_F32:
        n = (len(blob) - 4) // 4
        return list(struct.unpack(f">{n}f", blob[4:4 + n * 4]))
    if blob[:4] == MAGIC_F64:
        n = (len(blob) - 4) // 8
        return list(struct.unpack(f">{n}d", blob[4:4 + n * 8]))
    n = len(blob) // 8  # 历史数据：裸 float64
    return list(struct.unpack(f">{n}d", blob))


def blob_dim(blob: bytes) -> int:
    """从 BLOB 推断维度（不完整反序列化，用于快速校验）。"""
    if blob[:4] == MAGIC_F32:
        return (len(blob) - 4) // 4
    if blob[:4] == MAGIC_F64:
        return (len(blob) - 4) // 8
    return len(blob) // 8


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """余弦相似度。

    维度不一致时**抛错**而不是静默截断——初版用 min(len) 比较，
    会让 256 维 mock 向量与 1024 维真实向量之间的打分完全失去意义且无人察觉。
    """
    if len(a) != len(b):
        raise ValueError(f"向量维度不一致: {len(a)} vs {len(b)}（索引需重建）")
    n = len(a)
    dot = sum(a[i] * b[i] for i in range(n))
    na = sum(v * v for v in a) ** 0.5 or 1.0
    nb = sum(v * v for v in b) ** 0.5 or 1.0
    return dot / (na * nb)


embedding_client = EmbeddingClient()
