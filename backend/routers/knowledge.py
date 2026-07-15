"""知识库管理 API。

端点:
    POST   /api/knowledge/upload       - 上传文档 → 解析 → 分块 → 向量化 → 存储
    GET    /api/knowledge/list         - 列出已上传文档
    DELETE /api/knowledge/{id}         - 删除文档及其向量
    POST   /api/knowledge/{id}/reindex - 重建索引
    GET    /api/knowledge/search       - 搜索知识库
    GET    /api/knowledge/categories   - 获取分类列表
"""

import os
import shutil
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import get_db
from backend.repositories.knowledge_repo import KnowledgeRepo
from backend.rag.document_loader import document_loader
from backend.rag.vector_store import vector_store

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# 上传文件存储目录
UPLOAD_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "uploads"
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 允许的文件类型
ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}
MAX_UPLOAD_SIZE_MB = 50


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------

def _validate_file(filename: str, size: int) -> str | None:
    """校验文件类型和大小，返回错误信息或 None。"""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"不支持的文件格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}"
    if size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        return f"文件过大 ({size / 1024 / 1024:.1f}MB)，限制为 {MAX_UPLOAD_SIZE_MB}MB"
    return None


# ------------------------------------------------------------------
# 端点
# ------------------------------------------------------------------


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(default="未分类"),
    title: str = Form(default=""),
    user_id: int = Header(alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """上传文档：解析 → 分块 → 向量化 → 存储。

    请求: multipart/form-data
        - file: 文档文件（PDF/MD/TXT）
        - category: 分类标签（可选）
        - title: 文档标题（可选，默认使用文件名）
    """
    if not file.filename:
        return {"ok": False, "error": "未选择文件"}

    # 校验
    error = _validate_file(file.filename, file.size or 0)
    if error:
        return {"ok": False, "error": error}

    repo = KnowledgeRepo(db)
    ext = os.path.splitext(file.filename)[1].lower()

    # 检查重复
    existing = await repo.search_by_filename(user_id, file.filename)
    if existing:
        return {"ok": False, "error": f"文件 {file.filename} 已存在，请先删除旧版本"}

    # 创建元数据记录
    doc = await repo.create(
        user_id=user_id,
        filename=file.filename,
        file_type=ext.lstrip("."),
        category=category,
        title=title or file.filename,
    )

    # 保存上传文件到临时目录并解析
    doc_id_str = f"doc_{doc.id}"
    tmp_path = os.path.join(tempfile.gettempdir(), f"kb_upload_{doc.id}{ext}")

    try:
        # 写入临时文件
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        # 解析文档
        text, metadata = await document_loader.load(tmp_path)

        if not text.strip():
            await repo.delete(doc.id)
            return {"ok": False, "error": "文档内容为空，无法解析"}

        # 索引到向量数据库
        chunk_count = await vector_store.index_document(
            doc_id=doc_id_str,
            text=text,
            metadata={
                "category": category,
                "filename": file.filename,
                "file_type": ext.lstrip("."),
                "title": title or file.filename,
            },
        )

        # 更新元数据
        await repo.update_stats(
            doc.id,
            chunk_count=chunk_count,
            char_count=len(text),
            file_size_mb=round(len(content) / (1024 * 1024), 2),
        )

        # 将文件复制到持久存储
        dest_path = os.path.join(UPLOAD_DIR, f"{doc.id}{ext}")
        shutil.copy2(tmp_path, dest_path)

        logger.info(f"文档上传成功 id={doc.id} filename={file.filename} chunks={chunk_count}")
        return {
            "ok": True,
            "docId": doc.id,
            "filename": file.filename,
            "chunkCount": chunk_count,
            "charCount": len(text),
        }

    except Exception as e:
        logger.error(f"文档上传失败 id={doc.id}: {e}")
        # 清理
        await repo.delete(doc.id)
        await vector_store.delete_document(doc_id_str)
        return {"ok": False, "error": str(e)}

    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.get("/list")
async def list_documents(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    category: Optional[str] = Query(default=None),
    user_id: int = Header(alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """列出已上传的文档。"""
    repo = KnowledgeRepo(db)
    docs, total = await repo.list_documents(user_id, page=page, limit=limit, category=category)

    return {
        "ok": True,
        "total": total,
        "page": page,
        "limit": limit,
        "items": [
            {
                "id": d.id,
                "filename": d.filename,
                "title": d.title,
                "category": d.category,
                "fileType": d.file_type,
                "chunkCount": d.chunk_count,
                "charCount": d.char_count,
                "fileSizeMb": d.file_size_mb,
                "createdAt": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
    }


@router.delete("/{doc_id:int}")
async def delete_document(
    doc_id: int,
    user_id: int = Header(alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除文档及其向量索引。"""
    repo = KnowledgeRepo(db)
    doc = await repo.get_by_id(doc_id)
    if doc is None or doc.user_id != user_id:
        return {"ok": False, "error": "文档不存在"}

    # 删除向量索引
    await vector_store.delete_document(f"doc_{doc_id}")

    # 删除元数据记录
    await repo.delete(doc_id)

    # 删除上传的文件
    for ext in ALLOWED_EXTENSIONS:
        file_path = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")
        if os.path.exists(file_path):
            os.remove(file_path)

    logger.info(f"文档删除成功 id={doc_id}")
    return {"ok": True}


@router.post("/{doc_id:int}/reindex")
async def reindex_document(
    doc_id: int,
    user_id: int = Header(alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """重建文档索引（删除旧索引 + 重新分块向量化）。"""
    repo = KnowledgeRepo(db)
    doc = await repo.get_by_id(doc_id)
    if doc is None or doc.user_id != user_id:
        return {"ok": False, "error": "文档不存在"}

    # 查找上传文件
    file_path = None
    for ext in ALLOWED_EXTENSIONS:
        p = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break

    if file_path is None:
        return {"ok": False, "error": "原始文件不存在，请重新上传"}

    # 重新解析
    text, _metadata = await document_loader.load(file_path)

    if not text.strip():
        return {"ok": False, "error": "文档内容为空"}

    # 重建索引
    doc_id_str = f"doc_{doc_id}"
    chunk_count = await vector_store.reindex_document(
        doc_id=doc_id_str,
        text=text,
        metadata={
            "category": doc.category,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "title": doc.title,
        },
    )

    # 更新元数据
    await repo.update_stats(doc.id, chunk_count=chunk_count, char_count=len(text))

    logger.info(f"索引重建成功 id={doc_id} chunks={chunk_count}")
    return {"ok": True, "chunkCount": chunk_count}


@router.get("/search")
async def search_knowledge(
    q: str = Query(min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
    category: Optional[str] = Query(default=None),
) -> dict:
    """搜索知识库（语义检索）。

    Args:
        q: 搜索关键词
        top_k: 返回结果数
        category: 分类过滤（可选）
    """
    filter_dict = None
    if category:
        filter_dict = {"category": category}

    items = await vector_store.search(q, top_k=top_k, filter=filter_dict)

    return {
        "ok": True,
        "query": q,
        "total": len(items),
        "items": [
            {
                "content": item["content"],
                "metadata": item["metadata"],
                "score": item["score"],
            }
            for item in items
        ],
    }


@router.get("/categories")
async def get_categories(
    user_id: int = Header(alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """获取用户已有的分类列表。"""
    repo = KnowledgeRepo(db)
    categories = await repo.get_categories(user_id)
    return {"ok": True, "categories": categories}
