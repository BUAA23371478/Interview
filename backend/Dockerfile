# MAOO 平台后端部署镜像（前后端分离 → 后端容器）
# 平台注入 PORT / BASE_URL / LLM_API_KEY 等环境变量
FROM python:3.11-slim

WORKDIR /app

# 系统依赖（PyMuPDF 需要部分库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码与种子知识库
COPY app ./app
COPY scripts ./scripts
COPY data ./data

ENV PYTHONPATH=/app
ENV PORT=9000

EXPOSE $PORT

# 启动前先跑种子索引脚本（若 data/kb_seed 存在），再启动服务
CMD ["sh", "-c", "cd /app && python scripts/seed_kb.py || true && uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
