from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.repositories.base import BaseRepository


class UserRepo(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def register(self, username: str, password: str) -> User:
        """注册新用户，用户名重复时返回 None。"""
        existing = await self.get_by_username(username)
        if existing is not None:
            return None
        h, salt = User.hash_password(password)
        user = User(username=username, password_hash=f"{salt}:{h}")
        self.db.add(user)
        await self.db.flush()
        return user

    async def login(self, username: str, password: str) -> User | None:
        """登录验证，失败返回 None。"""
        user = await self.get_by_username(username)
        if user is None:
            return None
        if not user.verify_password(password):
            return None
        return user
