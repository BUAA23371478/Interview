"""
文档加载与分块。

- 支持 .md / .txt / .pdf（PyMuPDF）
- 中文感知的 RecursiveCharacterTextSplitter
"""
from __future__ import annotations

import io
from typing import List, Optional

from loguru import logger

from app.config import settings


def extract_text_from_bytes(content: bytes, filename: str) -> str:
    """从文件字节提取纯文本。"""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return _extract_pdf(content)
    if ext in ("md", "markdown", "txt"):
        return _decode_text(content)
    raise ValueError(f"不支持的文件格式: {ext}")


def _decode_text(content: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _extract_pdf(content: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise ValueError("未安装 PDF 解析库（PyMuPDF 或 pypdf）")
    doc = fitz.open(stream=content, filetype="pdf")
    pages = doc.page_count
    if pages > settings.rag_max_pdf_pages:
        logger.warning("PDF 页数 {} 超过上限 {}，截断", pages, settings.rag_max_pdf_pages)
        pages = settings.rag_max_pdf_pages
    parts = []
    for i in range(pages):
        parts.append(doc.load_page(i).get_text())
    doc.close()
    return "\n".join(parts)


def split_text(text: str, chunk_size: Optional[int] = None,
               chunk_overlap: Optional[int] = None) -> List[str]:
    """中文感知分块。"""
    chunk_size = chunk_size or settings.rag_chunk_size
    chunk_overlap = chunk_overlap or settings.rag_chunk_overlap
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", ".", "!", "?", ";", " ", ""],
        )
        return splitter.split_text(text)
    except ImportError:
        return _naive_split(text, chunk_size, chunk_overlap)


def _naive_split(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        # 尽量在句号处断开
        if end < n:
            cut = max(text.rfind("。", start, end), text.rfind("\n", start, end), text.rfind(".", start, end))
            if cut > start + chunk_size // 2:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= n:
            break
        start = max(start + 1, end - chunk_overlap)
    return [c for c in chunks if c]
