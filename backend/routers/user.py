from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.prompts import PARSE_RESUME_PROMPT
from backend.database.connection import get_db
from backend.llm.client import UnifiedLLMClient
from backend.repositories.user_repo import UserRepo
from backend.schemas.request import LoginRequest, RegisterRequest, ResumeSaveRequest
from backend.schemas.response import UserResponse
from backend.middleware.error_handler import LLMError

router = APIRouter(prefix="/api/user", tags=["user"])
llm_client = UnifiedLLMClient()


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


# ------------------------------------------------------------------
# 简历管理
# ------------------------------------------------------------------

@router.get("/resume")
async def get_resume(user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    repo = UserRepo(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"resume": user.resume_content or ""}


@router.put("/resume")
async def save_resume(req: ResumeSaveRequest, user_id: int = Header(alias="X-User-Id"), db: AsyncSession = Depends(get_db)) -> dict:
    repo = UserRepo(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.resume_content = req.resume
    await db.flush()
    return {"status": "ok", "length": len(req.resume)}


@router.post("/resume/parse")
async def parse_resume(user_id: int = Header(alias="X-User-Id"), file: UploadFile = File(...), db: AsyncSession = Depends(get_db)) -> dict:
    # 读取文件内容
    raw_bytes = await file.read()
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            raw_text = raw_bytes.decode("gbk")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="无法解析文件编码，请上传 UTF-8 或 GBK 编码的文本文件")

    if len(raw_text) > 20000:
        raw_text = raw_text[:20000]

    # AI 解析
    try:
        parsed = await llm_client.chat(
            PARSE_RESUME_PROMPT.format(raw_text=raw_text),
            temperature=0.3,
            max_tokens=2048,
        )
    except LLMError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 自动保存
    repo = UserRepo(db)
    user = await repo.get_by_id(user_id)
    if user:
        user.resume_content = parsed.strip()
        await db.flush()

    return {"resume": parsed.strip()}
