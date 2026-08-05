# MAOO 平台部署指南

应用 slug：**`interview-agent`** ｜ 访问地址：`/app/interview-agent/` ｜ 平台：https://maoojjkk.xyz

---

## 一、部署形态

**前后端分离**：前端 `dist.zip` + 后端部署包（zip）。

```
浏览器
  └─ /app/interview-agent/        → 前端静态文件（Nginx serve dist）
  └─ /app/interview-agent/api/*   → 反向代理到后端容器（剥离前缀）
```

---

## 〇、服务器管理员前置准备清单（部署前必读）

> 目的：提前在服务器上拉取基础镜像、确认资源，**避免部署时拉取超时导致失败**。

### 1. 需要预拉取的容器镜像

| 镜像 | 版本 | 用途 | 拉取命令 |
|------|------|------|----------|
| `python` | `3.11-slim` | 后端 FastAPI 运行环境 | `docker pull python:3.11-slim` |
| `mysql` | `8.0` | 平台托管数据库（自动创建模式） | `docker pull mysql:8.0` |
| `postgres` | `15` | 平台托管数据库（若选 PostgreSQL） | `docker pull postgres:15` |
| `node` | `18-alpine`（可选） | 前端构建/本地调试 | `docker pull node:18-alpine` |

> 平台自动创建数据库时会使用 `mysql:8.0` 或 `postgres:15` 镜像，**提前拉取可避免首次创建超时**。

### 2. 服务器资源建议

| 项 | 最低 | 推荐 |
|----|------|------|
| CPU | 1 核 | 2 核 |
| 内存 | 2 GB | 4 GB（后端 + MySQL + jieba 分词） |
| 磁盘 | 5 GB 空闲 | 10 GB（种子知识库 + 上传文档 + 数据库） |
| 网络 | — | 可访问 `pypi.org` / `github.com` / `api.deepseek.com` / `api.siliconflow.cn` |

### 3. 网络出口确认

后端容器需要访问（用于依赖安装与运行）：
- `pypi.org` / `pypi.aliyun.com` — pip 安装依赖（可配镜像加速）
- `api.siliconflow.cn` — 嵌入 API（免费额度，知识库检索）
- `api.deepseek.com` — 用户自带 Key 的 LLM 调用（由用户 key 驱动，服务端不直连也可，但用户功能需可达）
- `github.com` — 可选（内置知识库种子源）

### 4. 提前验证

```bash
# 确认 Docker 与镜像
docker version && docker images | grep -E "python|mysql|postgres"

# 确认网络（服务器上）
curl -sI https://pypi.org --max-time 5 && echo "pypi OK"
curl -sI https://api.siliconflow.cn --max-time 5 && echo "siliconflow OK"
```

---

## 二、打包

在项目根目录执行：

```bash
bash deploy/build.sh
```

产物：
| 文件 | 用途 |
|------|------|
| `frontend/dist.zip` | 前端构建产物（Vite base=`/app/interview-agent/`） |
| `backend/backend-deploy.zip` | 后端部署包（app/ + scripts/ + data/kb_seed/ + Dockerfile） |

> 前端打包规范：进入 `dist` 目录打包**内容**，不含 dist 文件夹本身。
> 后端 <50MB（种子知识库约 1.5MB）。

### 技术栈与依赖清单

**后端（Python 3.11）**：

| 依赖 | 用途 | 说明 |
|------|------|------|
| FastAPI / uvicorn | Web 框架 | 服务入口，监听 `$PORT` |
| SQLAlchemy 2.0 + aiosqlite | ORM + SQLite | 默认本地库 |
| asyncmy / asyncpg | MySQL / PostgreSQL 异步驱动 | 平台托管数据库用 |
| openai | LLM 客户端 | DeepSeek Responses API / chat.completions |
| httpx | 嵌入 API 调用 | SiliconFlow bge-m3 |
| rank-bm25 + jieba | 关键词检索 | RAG 混合检索 BM25 路 |
| PyMuPDF | PDF 解析 | 知识库文档上传 |
| langchain-text-splitters | 中文分块 | RAG 分块 |
| loguru | 日志 | 运行日志 |
| sse-starlette | SSE 流式 | 面试/练习流式输出 |
| python-multipart | 文件上传 | 知识库 UGC 上传 |

**前端（Node 18+）**：React 18 · TypeScript · Vite 5 · react-router-dom · Tailwind CDN

> 依赖在 Docker 构建时安装（`pip install -r requirements.txt`）。服务器管理员可提前配置
> pip 镜像加速（`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple`）
> 避免安装超时。

---

## 三、创建应用与上传

1. 登录 MAOO → 开发中心 → 创建应用
2. 类型：**前后端分离**；slug：`interview-agent`
3. 上传 **前端构建产物** `dist.zip`
4. 上传 **后端部署包** `backend-deploy.zip`
5. 配置数据库连接（可选，见下）与环境变量
6. 提交审核 → 管理员审核 → 发布

---

## 四、环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `EMBEDDING_API_KEY` | SiliconFlow bge-m3 嵌入 Key（知识库检索，平台提供免费额度） | ✅ |
| `EMBEDDING_BASE_URL` | 默认 `https://api.siliconflow.cn/v1` | 可选 |
| `EMBEDDING_MODEL` | 默认 `BAAI/bge-m3` | 可选 |
| `DEBUG` | **必须为 `false`**（生产）。为 true 时无平台头回退 dev 用户，存在安全风险 | ✅ false |
| `ADMIN_ROLES` | 管理员角色，默认 `admin,developer` | 可选 |
| `DATABASE_URL` / `DB_*` | 平台托管数据库（自动创建模式自动注入，无需手填） | 平台注入 |
| `MYSQL_*` | 外部数据库模式（可选） | 可选 |
| `LLM_API_KEY` | 可选。默认**留空**，LLM 由用户自带 Key（BYOK） | 否 |

> **LLM 收费策略**：平台不提供 LLM 额度。用户在前端「个人中心 → 模型设置」填入自己的
> API Key（DeepSeek / SiliconFlow 等 OpenAI 兼容服务），随 `X-LLM-Key` 请求头发送，服务器不落库。
> 未配置 Key 时，AI 面试/练习会明确报错引导配置（不会静默 mock）。知识库搜索用嵌入 Key 免费可用。

平台自动注入 `PORT` / `BASE_URL`，后端监听 `$PORT`，无需手动配置。

---

## 五、数据库

MAOO 平台 v1.0.8+ **支持平台托管数据库**（推荐，免自建）：

> **向量索引与业务数据同库**（重要）：知识库向量（`vectors` 表）、文档元数据（`documents` 表）
> 均存入平台托管数据库，与应用容器同生命周期。容器重启/重新部署后知识库不丢失。
> 本地开发无数据库时整体回退 SQLite。

### 模式一：平台自动创建数据库（推荐）

创建应用时选择"平台自动创建"（MySQL 8.0 / PostgreSQL 15），平台会：
- 创建独立数据库容器 `db-{slug}`，与应用容器内网互联（不占用宿主机端口）
- 自动注入连接环境变量（含随机密码）
- 删除应用时自动清理

**后端自动适配**（无需改代码）：
```bash
# 平台注入（自动创建模式）
DATABASE_URL=mysql://user_{slug}:<pwd>@db-{slug}:3306/app_{slug}
# 或组件变量
DB_HOST=db-{slug}  DB_PORT=3306  DB_NAME=app_{slug}  DB_USER=user_{slug}  DB_PASSWORD=<pwd>
```
启动时 `init_db()` 用 `Base.metadata.create_all` 幂等建表（已存在则跳过），无需手动跑 SQL。

### 模式二：外部数据库（兼容 v1.0.2）

填写 `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_DATABASE` / `MYSQL_USER` / `MYSQL_PASSWORD`，后端检测到后自动切换。

### 本地/无数据库

未注入任何数据库变量时，后端回退 SQLite（`backend/data/interview.db`），适合本地开发。

> 数据库连接串优先级：`DATABASE_URL` > `DB_*` > `MYSQL_*` > SQLite。

---

## 六、知识库审核机制

- 内置种子知识库（48 篇精选文档）启动时自动建索引。
- 用户上传文档（md/txt/pdf ≤50MB）→ **AI 预审**（技术相关性/有害内容/重复检测）→
  `pending` 待审队列 → **管理员复核**（`X-Maoo-User-Role` ∈ admin/developer）通过后建索引入库。
- 防污染：内容 hash 快照比对 + 每日上传配额 + 审核日志全程留痕。

---

## 七、验证清单（提交审核前）

| # | 检查项 | 状态 |
|---|--------|------|
| 1 | Vite base = `/app/interview-agent/` | ✅ |
| 2 | React Router basename = `/app/interview-agent/` | ✅ |
| 3 | API baseURL = `/app/interview-agent/api` | ✅ |
| 4 | 后端路由无 `/api` 前缀 | ✅ |
| 5 | 监听 `$PORT` | ✅ |
| 6 | `/health` 返回 200 | ✅ |
| 7 | 用户身份读 `X-Maoo-User-*` 请求头 | ✅ |
| 8 | 前端从 localStorage 读平台 JWT 作 `Authorization` | ✅ |
| 9 | 401 → 跳 `/login?redirect=...` | ✅ |
| 10 | `DEBUG=false`（生产必需） | ⚠️ 必须确认 |
| 11 | LLM BYOK：前端带 `X-LLM-Key` 头，无 key 明确报错 | ✅ |
| 12 | 知识库嵌入用 `EMBEDDING_API_KEY`（免费） | ✅ |

---

## 八、LLM BYOK（用户自带 Key）

- 用户路径：**个人中心 → 模型设置 → 填 Key → 测试 → 保存**
- Key 仅存于浏览器 `localStorage`，随 `X-LLM-Key` 请求头发送，服务器不落库
- 未配置 Key 时 AI 功能报错引导配置（返回 `code: LLM_NO_KEY_OR_ERROR`）
- 支持 OpenAI 兼容服务（DeepSeek / SiliconFlow 等），由 `LLM_RESPONSES_MODE` 切换
  Responses API（`deepseek-v4-flash`）或 chat.completions

---

## 九、更新流程

取消发布 → 回到草稿 → 重新上传两个 zip → 提交审核 → 重新发布。
