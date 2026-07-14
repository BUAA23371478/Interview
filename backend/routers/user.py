from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.user_repo import UserRepo
from backend.schemas.request import LoginRequest, RegisterRequest
from backend.schemas.response import UserResponse
from backend.database.connection import get_db

router = APIRouter(prefix="/api/user", tags=["user"])


@router.post("/register", response_model=UserResponse)
async def register_user(req: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    repo = UserRepo(db)
    user = await repo.register(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    return UserResponse(userId=str(user.id), username=user.username)


@router.post("/login", response_model=UserResponse)
async def login_user(req: LoginRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    repo = UserRepo(db)
    user = await repo.login(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return UserResponse(userId=str(user.id), username=user.username)


@router.get("", response_model=UserResponse)
async def get_user(user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> UserResponse:
    repo = UserRepo(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserResponse(userId=str(user.id), username=user.username)
