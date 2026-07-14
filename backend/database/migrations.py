from backend.database.connection import Base, engine
from backend.models import interview, practice, user  # noqa: F401


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
