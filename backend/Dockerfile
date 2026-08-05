# MAOO 平台后端部署镜像（前后端分离 → 后端容器）
# 平台注入 PORT / BASE_URL / EMBEDDING_API_KEY 等环境变量
# LLM 采用用户自带 Key（BYOK）：服务端不配 LLM_API_KEY，用户经 X-LLM-Key 头自带
FROM python:3.11-slim

WORKDIR /app

# 系统依赖（PyMuPDF 需要部分库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（国内服务器用阿里云镜像加速，避免拉取超时）
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
