#!/usr/bin/env bash
# MAOO 平台打包脚本：前端 dist.zip + 后端部署包
# 使用 Python zipfile 打包（跨平台，无需系统 zip）
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== 1/3 构建前端 ==="
cd frontend
npm run build

echo "--- 打包 dist.zip（dist 内容，不含 dist 文件夹）---"
python - <<'PY'
import os, sys, zipfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
src = "dist"
out = "dist.zip"
if os.path.exists(out):
    os.remove(out)
count = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk(src):
        for f in files:
            full = os.path.join(root, f)
            arc = os.path.relpath(full, src)
            zf.write(full, arc)
            count += 1
print(f"✅ frontend/dist.zip 已生成（{count} 个文件，{os.path.getsize(out)/1024:.0f} KB）")
PY

echo ""
echo "=== 2/3 打包后端 ==="
cd ../backend
python - <<'PY'
import os, sys, zipfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
out = "backend-deploy.zip"
if os.path.exists(out):
    os.remove(out)
targets = ["app", "scripts", "data/kb_seed", "requirements.txt", "Dockerfile"]
count = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for t in targets:
        if os.path.isdir(t):
            for root, _dirs, files in os.walk(t):
                for f in files:
                    if "__pycache__" in root or f.endswith(".pyc"):
                        continue
                    full = os.path.join(root, f)
                    zf.write(full, full)
                    count += 1
        elif os.path.isfile(t):
            zf.write(t, t)
            count += 1
print(f"✅ backend/backend-deploy.zip 已生成（{count} 个文件，{os.path.getsize(out)/1024:.0f} KB）")
PY

echo ""
echo "=== 3/3 产物清单 ==="
echo "  frontend/dist.zip          → MAOO 前端构建产物"
echo "  backend/backend-deploy.zip → MAOO 后端部署包"
echo ""
echo "下一步：前往 MAOO 平台 https://maoojjkk.xyz 创建应用（前后端分离，slug=interview-agent），"
echo "上传两个 zip，配置环境变量（LLM_API_KEY / EMBEDDING_API_KEY 等），提交审核。"
echo "详见 deploy/README.md"
