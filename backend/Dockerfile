# MAOO 平台后端部署镜像（前后端分离 → 后端容器）
# 平台注入 PORT / BASE_URL / EMBEDDING_API_KEY 等环境变量
# LLM 采用用户自带 Key（BYOK）：服务端不配 LLM_API_KEY，用户经 X-LLM-Key 头自带
FROM python:3.11-slim

WORKDIR /app

# 安装 Python 依赖
# 提速要点：
#   1. pip 走阿里云镜像（国内服务器拉取快一个量级）
#   2. 无 apt-get 步骤：所有依赖（PyMuPDF/asyncmy/asyncpg 等）都有预编译 wheel，
#      jieba 为纯 Python 包，均无需 build-essential；省去卡死的 deb.debian.org
COPY requirements.txt .
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip install --no-cache-dir -r requirements.txt

# 复制后端代码与种子知识库
COPY app ./app
COPY scripts ./scripts
COPY data ./data

ENV PYTHONPATH=/app
ENV PORT=9000
# 生产必须关闭 debug（否则无平台头时回退 dev 用户，存在安全风险）
ENV DEBUG=false

EXPOSE $PORT

# 启动前先跑种子索引脚本（若 data/kb_seed 存在），再启动服务
CMD ["sh", "-c", "cd /app && python scripts/seed_kb.py || true && uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
