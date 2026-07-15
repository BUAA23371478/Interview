"""文档解析模块。

支持 PDF（PyMuPDF）、Markdown（markdown-it-py）、纯文本文件的解析。
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger


class DocumentLoader:
    """多格式文档解析器。

    支持格式: PDF (.pdf), Markdown (.md, .markdown), 纯文本 (.txt)
    """

    # PDF 最大页数限制（防止超大文件）
    MAX_PDF_PAGES = 200
    # 最大文件大小（MB）
    MAX_FILE_SIZE_MB = 50

    async def load(self, file_path: str) -> tuple[str, dict]:
        """加载文档，返回 (文本内容, 元数据)。

        Args:
            file_path: 文件路径

        Returns:
            (text_content, metadata_dict)
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 检查文件大小
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self.MAX_FILE_SIZE_MB:
            raise ValueError(f"文件过大 ({size_mb:.1f}MB)，限制为 {self.MAX_FILE_SIZE_MB}MB")

        ext = path.suffix.lower()
        logger.info(f"加载文档: {path.name} ({ext})")

        if ext == ".pdf":
            text = await self._load_pdf(str(path))
        elif ext in (".md", ".markdown"):
            text = await self._load_text(str(path))
        elif ext == ".txt":
            text = await self._load_text(str(path))
        else:
            raise ValueError(f"不支持的文件格式: {ext}，支持: PDF, MD, TXT")

        # 清理文本
        text = self._clean_text(text)

        metadata = {
            "filename": path.name,
            "file_type": ext.lstrip("."),
            "file_size_mb": round(size_mb, 2),
            "char_count": len(text),
        }

        logger.info(f"文档加载完成: {path.name} ({len(text)} 字符)")
        return text, metadata

    # ------------------------------------------------------------------
    # 格式解析
    # ------------------------------------------------------------------

    async def _load_pdf(self, path: str) -> str:
        """使用 PyMuPDF 解析 PDF。"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("请安装 PyMuPDF: pip install PyMuPDF")

        doc = fitz.open(path)
        page_count = min(len(doc), self.MAX_PDF_PAGES)
        pages: list[str] = []

        for i in range(page_count):
            page = doc[i]
            text = page.get_text()
            if text.strip():
                pages.append(text)

        doc.close()

        if not pages:
            logger.warning(f"PDF 未提取到文本: {path}")
            return ""

        return "\n\n".join(pages)

    async def _load_text(self, path: str) -> str:
        """加载纯文本 / Markdown 文件（UTF-8）。"""
        # 尝试 UTF-8，失败则尝试 GBK
        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                with open(path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise ValueError(f"无法解码文件: {path}")

    # ------------------------------------------------------------------
    # 文本清理
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(text: str) -> str:
        """清理多余空白，保留基本格式。"""
        # 合并连续空行（最多保留 2 个换行）
        import re

        text = re.sub(r"\n{3,}", "\n\n", text)
        # 去除行首尾空白但保留换行结构
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)
        # 去除首尾空白
        text = text.strip()
        return text


# 全局单例
document_loader = DocumentLoader()
