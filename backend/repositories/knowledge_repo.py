"""知识库文档 Repository。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.knowledge import KnowledgeDocument
from backend.repositories.base import BaseRepository


class KnowledgeRepo(BaseRepository):
    """知识库文档元数据操作。"""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def create(
        self,
        user_id: int,
        filename: str,
        file_type: str,
        category: str = "未分类",
        title: str = "",
        description: str = "",
    ) -> KnowledgeDocument:
        doc = KnowledgeDocument(
            user_id=user_id,
            filename=filename,
            file_type=file_type,
            category=category,
            title=title or filename,
            description=description,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def get_by_id(self, doc_id: int) -> KnowledgeDocument | None:
        result = await self.db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        )
        return result.scalar_one_or_none()

    async def list_documents(
        self, user_id: int, page: int = 1, limit: int = 50, category: str | None = None
    ) -> tuple[list[KnowledgeDocument], int]:
        base_query = select(KnowledgeDocument).where(
            KnowledgeDocument.user_id == user_id,
            KnowledgeDocument.status == "active",
        )
        if category:
            base_query = base_query.where(KnowledgeDocument.category == category)

        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.db.execute(count_query)
        total = int(count_result.scalar() or 0)

        result = await self.db.execute(
            base_query
            .order_by(KnowledgeDocument.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def update_stats(
        self,
        doc_id: int,
        chunk_count: int = 0,
        char_count: int = 0,
        file_size_mb: float = 0.0,
        status: str = "active",
    ) -> None:
        doc = await self.get_by_id(doc_id)
        if doc is None:
            return
        doc.chunk_count = chunk_count
        doc.char_count = char_count
        doc.file_size_mb = file_size_mb
        doc.status = status

    async def delete(self, doc_id: int) -> bool:
        doc = await self.get_by_id(doc_id)
        if doc is None:
            return False
        doc.status = "deleted"
        await self.db.flush()
        return True

    async def get_categories(self, user_id: int) -> list[str]:
        result = await self.db.execute(
            select(KnowledgeDocument.category)
            .where(
                KnowledgeDocument.user_id == user_id,
                KnowledgeDocument.status == "active",
            )
            .distinct()
        )
        return [row[0] for row in result.all()]

    async def search_by_filename(self, user_id: int, filename: str) -> KnowledgeDocument | None:
        result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.user_id == user_id,
                KnowledgeDocument.filename == filename,
                KnowledgeDocument.status == "active",
            )
        )
        return result.scalar_one_or_none()
