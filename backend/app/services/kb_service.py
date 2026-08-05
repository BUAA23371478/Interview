"""
知识库服务：内置文档索引 + 用户 UGC 上传 → 审核 → 入库全流程。

防污染机制：
1. 上传即做基础校验（类型/大小/内容为空/是否已存在）
2. AI 预审：LLM 评估是否技术面试相关、是否有害内容，生成推荐分类与通过分
3. 管理员人工复核：仅 admin 可 approve/reject，全程留痕（review_logs）
4. 内容快照 + hash 比对：approve 时重新计算 hash，与上传时比对，防止改
5. 反刷：每人每日上传数量 / 字数上限
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from loguru import logger
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.deps import MaooUser
from app.llm import llm_client
from app.models import Document, ReviewLog
from app.rag.bm25 import BM25Retriever
from app.rag.loader import extract_text_from_bytes, split_text
from app.rag.vector_store import vector_store

ALLOWED_EXTS = {".md", ".markdown", ".txt", ".pdf"}

_DOC_ID_PREFIX = "doc"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _doc_id(doc_id: int) -> str:
    return f"{_DOC_ID_PREFIX}:{doc_id}"


# ── 文档模型序列化 ────────────────────────────────────────────────────

def _doc_to_dict(d: Document) -> Dict[str, Any]:
    return {
        "id": d.id,
        "maoo_user_id": d.maoo_user_id,
        "filename": d.filename,
        "title": d.title or d.filename,
        "category": d.category,
        "file_type": d.file_type,
        "file_size": d.file_size,
        "char_count": d.char_count,
        "status": d.status,
        "is_seed": bool(d.is_seed),
        "review_note": d.review_note,
        "chunk_count": d.chunk_count,
        "created_at": d.created_at,
    }


# ── 列表 / 分类 ───────────────────────────────────────────────────────

async def list_documents(user: MaooUser, page: int = 1, limit: int = 50,
                         status: Optional[str] = None,
                         category: Optional[str] = None) -> Dict[str, Any]:
    """普通用户只能看到 approved；admin 可看全部状态。"""
    async with SessionLocal() as session:
        q = select(Document)
        if user.is_admin:
            if status:
                q = q.where(Document.status == status)
        else:
            q = q.where(Document.status == "approved")
        if category:
            q = q.where(Document.category == category)
        total = (await session.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar() or 0
        rows = (await session.execute(
            q.order_by(Document.id.desc()).offset((page - 1) * limit).limit(limit)
        )).scalars().all()
        return {"total": total, "page": page, "limit": limit,
                "items": [_doc_to_dict(d) for d in rows]}


async def list_categories(user: MaooUser) -> List[str]:
    async with SessionLocal() as session:
        q = select(Document.category).distinct()
        if not user.is_admin:
            q = q.where(Document.status == "approved")
        rows = (await session.execute(q)).scalars().all()
        return sorted({r for r in rows if r})


# ── 检索 ──────────────────────────────────────────────────────────────

async def search_documents(query: str, top_k: int = 5,
                           category: Optional[str] = None,
                           user: Optional[MaooUser] = None) -> List[Dict[str, Any]]:
    """混合检索已上架文档。"""
    from app.rag.engine import query_engine
    filter_meta = {"status": "approved"}
    if category:
        filter_meta["category"] = category
    hits = await query_engine.hybrid_query(query, top_k=top_k, filter_meta=filter_meta)
    out = []
    for h in hits:
        out.append({
            "id": h["id"],
            "content": h["content"],
            "doc_title": h.get("doc_title", ""),
            "category": h.get("category", ""),
            "score": h.get("score", 0.0),
        })
    return out


# ── 索引构建 ─────────────────────────────────────────────────────────

async def _index_doc_chunks(doc_id: int, chunks: List[str], meta: Dict[str, Any]) -> int:
    """向量 + BM25 双索引。"""
    did = _doc_id(doc_id)
    chunk_count = await vector_store.index_document(did, chunks, meta)
    # 同步 BM25 缓存：追加语料后重建
    nodes = [{
        "id": f"{did}#{i}", "doc_id": did, "text": c, "metadata": meta,
    } for i, c in enumerate(chunks)]
    _append_bm25(nodes)
    return chunk_count


def _append_bm25(nodes: List[Dict[str, Any]]) -> None:
    """把新节点合并进 BM25 缓存并重建。"""
    try:
        import pickle
        cache_path = settings.bm25_cache_path
        corpus: List[Dict[str, Any]] = []
        if cache_path.exists():
            with open(cache_path, "rb") as fh:
                corpus = pickle.load(fh).get("corpus", [])
        existing_ids = {n["id"] for n in corpus}
        for n in nodes:
            if n["id"] not in existing_ids:
                corpus.append(n)
        with open(cache_path, "wb") as fh:
            pickle.dump({"corpus": corpus}, fh)
        # 热更新当前进程的 BM25 实例
        from app.rag.bm25 import bm25_retriever
        bm25_retriever._corpus = corpus
        from rank_bm25 import BM25Okapi
        bm25_retriever._bm25 = BM25Okapi([_tokenize(d["text"]) for d in corpus]) if corpus else None
    except Exception as e:  # noqa: BLE001
        logger.warning("BM25 缓存更新失败: {}", e)


def _tokenize(text: str) -> List[str]:
    try:
        import jieba
        return [w.strip() for w in jieba.cut(text) if w.strip()]
    except ImportError:
        import re
        return re.findall(r"[\w一-鿿]+", text.lower())


async def reindex_doc(doc_id: int, content: str, meta: Dict[str, Any]) -> int:
    """重建单个文档索引（先删后建）。"""
    await vector_store.delete_document(_doc_id(doc_id))
    chunks = split_text(content)
    return await _index_doc_chunks(doc_id, chunks, meta)


# ── 内置种子索引 ─────────────────────────────────────────────────────

async def ensure_seed_indexed() -> None:
    """启动时若向量库为空且存在 seed 文档 → 全量索引（幂等）。"""
    if await vector_store.total_count() > 0:
        logger.info("向量库已有 {} 条，跳过种子索引", await vector_store.total_count())
        return
    seed_dir = settings.kb_seed_dir
    if not seed_dir.exists():
        logger.warning("seed 目录不存在: {}", seed_dir)
        return
    files = sorted(seed_dir.glob("*.md"))
    if not files:
        return
    async with SessionLocal() as session:
        indexed = 0
        for f in files:
            name = f.name
            cat = name.split("__")[0] if "__" in name else "通用知识"
            title = name.split("__")[-1].rsplit(".", 1)[0]
            # 幂等：按 title+category 查
            existing = (await session.execute(
                select(Document).where(Document.title == title, Document.category == cat)
            )).scalar_one_or_none()
            if existing and existing.chunk_count > 0:
                continue
            try:
                content = extract_text_from_bytes(f.read_bytes(), f.name)
            except Exception as e:  # noqa: BLE001
                logger.warning("解析 seed {} 失败: {}", name, e)
                continue
            if existing:
                doc = existing
            else:
                doc = Document(
                    maoo_user_id=0, filename=f.name, title=title, category=cat,
                    file_type="md", file_size=f.stat().st_size,
                    char_count=len(content), status="approved",
                    is_seed=1, original_hash=_sha256(content), content_text=content,
                )
                session.add(doc)
            doc.status = "approved"
            doc.content_text = content
            # 先提交 document 行，释放写事务，避免 SQLite 嵌套写锁（vector 索引用独立会话）
            await session.commit()
            await session.refresh(doc)
            meta = {"doc_title": title, "category": cat, "status": "approved", "doc_id": _doc_id(doc.id)}
            cc = await _index_doc_chunks(doc.id, split_text(content), meta)
            # 回填 chunk_count 并提交
            doc.chunk_count = cc
            await session.commit()
            indexed += 1
            logger.info("seed 已索引: {} ({} chunks)", title, cc)
        if indexed:
            logger.success("种子知识库索引完成：{} 篇", indexed)
        else:
            logger.info("种子知识库已全部索引，跳过")


# ── 上传与审核 ───────────────────────────────────────────────────────

async def validate_upload(user: MaooUser, filename: str, size: int) -> Optional[str]:
    """基础校验，返回错误信息或 None。"""
    ext = filename.lower().rsplit(".", 1)[-1]
    if f".{ext}" not in ALLOWED_EXTS:
        return f"不支持的文件格式 .{ext}，支持: md/txt/pdf"
    if size > settings.rag_max_upload_mb * 1024 * 1024:
        return f"文件过大（{size / 1024 / 1024:.1f}MB），上限 {settings.rag_max_upload_mb}MB"
    return None


async def _daily_upload_stats(user_id: int) -> Dict[str, int]:
    """当日该用户上传数量与字数。"""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    async with SessionLocal() as session:
        q = select(Document).where(
            Document.maoo_user_id == user_id,
            Document.created_at >= today,
            Document.is_seed == 0,
        )
        rows = (await session.execute(q)).scalars().all()
        return {"count": len(rows), "chars": sum(d.char_count or 0 for d in rows)}


async def ai_precheck(content: str, filename: str) -> Dict[str, Any]:
    """AI 预审：技术相关性 + 有害内容 + 推荐分类 + 通过建议。"""
    sample = content[:4000]
    system = (
        "你是知识库内容审核员。判断用户上传的文档是否适合收录进「AI 面试 / 技术知识库」。\n"
        "输出严格 JSON：\n"
        "{\n"
        '  "is_tech_related": true/false,   # 是否技术面试/知识相关内容\n'
        '  "has_harmful_content": true/false, # 是否含违法违规/低俗/广告/恶意内容\n'
        '  "is_duplicate_likely": false,     # 是否疑似重复\n'
        '  "approve_score": 0-100,           # 推荐通过分数\n'
        '  "recommended_category": "RAG|Agent|面经|八股文|其他",\n'
        '  "reason": "一句话理由"\n'
        "}\n"
    )
    user = f"文件名: {filename}\n文档内容预览:\n{sample}"
    parsed = await llm_client.chat_with_json(system, user)
    return {
        "is_tech_related": bool(parsed.get("is_tech_related", True)),
        "has_harmful_content": bool(parsed.get("has_harmful_content", False)),
        "is_duplicate_likely": bool(parsed.get("is_duplicate_likely", False)),
        "approve_score": int(parsed.get("approve_score", 50)),
        "recommended_category": str(parsed.get("recommended_category", "其他")),
        "reason": str(parsed.get("reason", "")),
    }


async def upload_document(user: MaooUser, file: UploadFile,
                          category: str = "", title: str = "") -> Dict[str, Any]:
    """用户上传文档 → 校验 → AI 预审 → pending 待人工复核。"""
    filename = file.filename or "未命名"
    content_bytes = await file.read()
    size = len(content_bytes)

    err = await validate_upload(user, filename, size)
    if err:
        return {"ok": False, "filename": filename, "status": "rejected", "message": err}

    # 解析文本
    try:
        content = extract_text_from_bytes(content_bytes, filename)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "filename": filename, "status": "rejected", "message": f"内容解析失败: {e}"}
    if len(content.strip()) < 50:
        return {"ok": False, "filename": filename, "status": "rejected", "message": "内容过短或为空"}

    # 反刷配额
    stats = await _daily_upload_stats(user.user_id)
    if stats["count"] >= settings.kb_daily_upload_limit:
        return {"ok": False, "filename": filename, "status": "rejected",
                "message": f"每日上传上限 {settings.kb_daily_upload_limit} 篇，已超限"}
    if stats["chars"] + len(content) > settings.kb_daily_char_limit:
        return {"ok": False, "filename": filename, "status": "rejected",
                "message": "今日上传总字数超限"}

    # 重复检测（hash 比对已上架文档）
    content_hash = _sha256(content)
    dup = await _find_existing(content_hash, user.user_id)
    if dup:
        return {"ok": False, "filename": filename, "status": "rejected",
                "message": f"内容已存在（文档 #{dup.id}: {dup.title}）"}

    # AI 预审
    precheck = await ai_precheck(content, filename)
    if precheck["has_harmful_content"] or not precheck["is_tech_related"]:
        status = "rejected"
        msg = f"未通过 AI 预审：{precheck['reason']}"
    else:
        status = "pending"
        msg = "已提交审核，等待管理员复核"

    # 保存原始文件到磁盘（留痕）
    saved_path = settings.upload_dir / f"u{user.user_id}_{int(datetime.now(timezone.utc).timestamp())}_{filename}"
    try:
        saved_path.write_bytes(content_bytes)
    except Exception as e:  # noqa: BLE001
        logger.warning("保存上传文件失败: {}", e)

    ext = filename.lower().rsplit(".", 1)[-1]
    async with SessionLocal() as session:
        doc = Document(
            maoo_user_id=user.user_id,
            filename=filename,
            title=title or filename.rsplit(".", 1)[0],
            category=category or precheck.get("recommended_category") or "未分类",
            file_type=ext,
            file_size=size,
            char_count=len(content),
            status=status,
            original_hash=content_hash,
            content_text=content,
        )
        session.add(doc)
        await session.flush()
        session.add(ReviewLog(
            doc_id=doc.id, action="upload", reviewer_role=user.role,
            reviewer_id=user.user_id, note=f"用户上传 {filename}",
        ))
        session.add(ReviewLog(
            doc_id=doc.id, action="ai_precheck", reviewer_role="ai",
            reviewer_id=0, note=precheck.get("reason", ""), ai_precheck=precheck,
        ))
        await session.commit()
        doc_id = doc.id

    return {
        "ok": True, "doc_id": doc_id, "filename": filename,
        "status": status, "message": msg, "ai_precheck": precheck,
    }


async def _find_existing(content_hash: str, user_id: int) -> Optional[Document]:
    async with SessionLocal() as session:
        return (await session.execute(
            select(Document).where(
                Document.original_hash == content_hash,
                Document.status.in_(["approved", "pending"]),
            )
        )).scalars().first()


# ── 管理员审核 ───────────────────────────────────────────────────────

async def list_pending(user: MaooUser, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    if not user.is_admin:
        return {"total": 0, "page": page, "limit": limit, "items": []}
    async with SessionLocal() as session:
        q = select(Document).where(Document.status == "pending")
        total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
        rows = (await session.execute(
            q.order_by(Document.id.asc()).offset((page - 1) * limit).limit(limit)
        )).scalars().all()
        items = []
        for d in rows:
            logs = (await session.execute(
                select(ReviewLog).where(ReviewLog.doc_id == d.id).order_by(ReviewLog.id)
            )).scalars().all()
            precheck = {}
            for lg in logs:
                if lg.ai_precheck:
                    precheck = lg.ai_precheck
            items.append({
                **_doc_to_dict(d),
                "review_logs": [
                    {"action": lg.action, "reviewer_role": lg.reviewer_role,
                     "reviewer_id": lg.reviewer_id, "note": lg.note,
                     "ai_precheck": lg.ai_precheck, "created_at": lg.created_at}
                    for lg in logs
                ],
                "ai_precheck": precheck,
            })
        return {"total": total, "page": page, "limit": limit, "items": items}


async def review_document(user: MaooUser, doc_id: int, action: str, note: str = "") -> Dict[str, Any]:
    """管理员 approve / reject。approve 时校验 hash + 建索引。"""
    if not user.is_admin:
        return {"ok": False, "message": "需要管理员权限"}
    async with SessionLocal() as session:
        doc = (await session.execute(
            select(Document).where(Document.id == doc_id)
        )).scalar_one_or_none()
        if not doc:
            return {"ok": False, "message": "文档不存在"}
        if doc.status != "pending":
            return {"ok": False, "message": f"文档状态为 {doc.status}，不可审核"}

        # 防篡改：重新计算 hash 对比
        current_hash = _sha256(doc.content_text or "")
        if doc.original_hash and current_hash != doc.original_hash:
            doc.status = "rejected"
            doc.review_note = f"{note}（内容 hash 校验失败，可能被篡改）"
            doc.review_by = user.username
            doc.review_at = datetime.now(timezone.utc)
            session.add(ReviewLog(
                doc_id=doc.id, action="reject", reviewer_role=user.role,
                reviewer_id=user.user_id, note="内容 hash 校验失败",
            ))
            await session.commit()
            return {"ok": False, "message": "内容 hash 校验失败，已拒绝"}

        if action == "approve":
            # 建索引
            meta = {
                "doc_title": doc.title or doc.filename,
                "category": doc.category,
                "status": "approved",
                "doc_id": _doc_id(doc.id),
            }
            chunks = split_text(doc.content_text or "")
            cc = await _index_doc_chunks(doc.id, chunks, meta)
            doc.chunk_count = cc
            doc.status = "approved"
            doc.review_note = note
            session.add(ReviewLog(
                doc_id=doc.id, action="approve", reviewer_role=user.role,
                reviewer_id=user.user_id, note=note or "管理员通过",
            ))
            message = f"已通过并建立索引（{cc} 个分块）"
        else:
            doc.status = "rejected"
            doc.review_note = note
            session.add(ReviewLog(
                doc_id=doc.id, action="reject", reviewer_role=user.role,
                reviewer_id=user.user_id, note=note or "管理员拒绝",
            ))
            message = "已拒绝"
        doc.review_by = user.username
        doc.review_at = datetime.now(timezone.utc)
        await session.commit()
        return {"ok": True, "message": message, "doc_id": doc.id, "status": doc.status}


async def remove_document(user: MaooUser, doc_id: int) -> Dict[str, Any]:
    """下架文档（admin 或本人）。"""
    async with SessionLocal() as session:
        doc = (await session.execute(
            select(Document).where(Document.id == doc_id)
        )).scalar_one_or_none()
        if not doc:
            return {"ok": False, "message": "文档不存在"}
        if not user.is_admin and doc.maoo_user_id != user.user_id:
            return {"ok": False, "message": "无权操作"}
        await vector_store.delete_document(_doc_id(doc.id))
        doc.status = "removed"
        doc.review_note = "已下架"
        await session.commit()
        return {"ok": True, "message": "已下架"}
