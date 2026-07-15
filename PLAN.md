# AI 智能刷题与模拟面试系统

基于 AI 的技术面试备考工具，提供**刷题模式**与**模拟面试模式**两种核心练习方式。

---

## 项目简介

```
┌─────────────────────────────────────────────────────────┐
│                   首页（模式选择）                         │
│                                                         │
│  ┌─────────────────┐    ┌─────────────────────────────┐ │
│  │   📝 刷题模式     │    │   🎯 模拟面试模式           │ │
│  │                  │    │                             │ │
│  │  输入主题→逐题练习 │    │  输入JD+简历→模拟面试       │ │
│  │  每道题即时反馈    │    │  一问一答→轮数控制          │ │
│  └─────────────────┘    └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 刷题模式

- 用户自由输入技术主题（如"Java后端开发""MySQL优化"）
- AI 围绕主题持续出题，答完即反馈（评分 + 解析 + 知识点）
- 难度自适应：连续答对 3 题升档，连续答错 2 题降档
- 知识库 RAG 检索增强，题目与主题强相关
- 断线恢复：Checkpoint 持久化状态，刷新不丢失

### 模拟面试模式

- 粘贴目标岗位 JD 和个人简历
- 自定义面试轮数（3-20 轮）
- AI 模拟面试官一问一答，支持追问机制（每轮最多 2 次追问）
- 结合 RAG 按 JD 技术栈检索相关考点，问题更精准
- 结束后生成多维度复盘报告（技术深度/表达清晰度/逻辑性/岗位匹配度）
- 断线恢复：Checkpoint 自动持久化，重启可继续

---

## 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| 前端 | React 19 + TypeScript + Vite + TailwindCSS | SPA 应用，Hash 路由 |
| 后端 | Python FastAPI + LangGraph + SQLite | 异步 API，SSE 流式输出 |
| AI Agent | LangGraph StateGraph | 状态图编排，Checkpoint 持久化 |
| RAG | Chroma + DeepSeek Embedding | 向量检索增强生成 |
| LLM | OpenAI 兼容接口 | DeepSeek / 智谱 GLM / 通义千问 |
| 数据库 | SQLite (WAL) + Alembic 迁移 | 开发环境，预留 MySQL 切换 |
| 测试 | pytest + pytest-asyncio | 异步测试，内存 SQLite |

---

## 项目结构

```
interview/
├── README.md
├── PLAN.md                       # 本文件：项目总览 + 开发计划
├── 需求说明.md
├── 前端技术设计文档.md
├── 后端技术设计文档.md
├── 迭代.md
├── frontend/                     # React 前端
│   └── src/
│       ├── pages/                # 页面组件
│       ├── components/           # 共享 UI 组件
│       ├── hooks/                # 自定义 Hook（含 SSE）
│       ├── api/                  # API 调用模块
│       ├── reducers/             # 状态 Reducer
│       ├── contexts/             # 全局状态
│       ├── types/                # TypeScript 类型
│       └── utils/                # 工具函数
└── backend/                      # Python 后端
    ├── main.py                   # FastAPI 入口
    ├── config.py                 # 配置管理（pydantic-settings）
    ├── agents/                   # LangGraph Agent
    │   ├── practice_agent.py     # 刷题 Agent（StateGraph）
    │   ├── interview_agent.py    # 面试 Agent（StateGraph）
    │   └── prompts.py            # LLM Prompt 模板
    ├── services/                 # 业务编排层
    │   ├── practice_service.py   # 刷题服务（委托 Agent）
    │   ├── interview_service.py  # 面试服务（委托 Agent）
    │   └── history_service.py    # 历史记录服务
    ├── routers/                  # API 路由
    │   ├── user.py               # 用户注册/登录/简历
    │   ├── practice.py           # 刷题 SSE + POST 端点
    │   ├── interview.py          # 面试 SSE + POST 端点
    │   ├── history.py            # 历史记录 CRUD
    │   └── knowledge.py          # 知识库管理 API
    ├── rag/                      # RAG 模块
    │   ├── document_loader.py    # 文档解析（PDF/MD/TXT）
    │   ├── embedding.py          # 向量化客户端
    │   └── vector_store.py       # Chroma 向量存储 + 检索
    ├── llm/                      # LLM 客户端
    │   ├── client.py             # UnifiedLLMClient（OpenAI 兼容）
    │   └── schemas.py            # JSON Schema 定义
    ├── models/                   # SQLAlchemy ORM 模型
    ├── repositories/             # 数据访问层
    ├── schemas/                  # Pydantic 请求/响应模型
    ├── sse/                      # SSE 事件管理
    ├── database/                 # 数据库连接 + 迁移
    ├── middleware/               # CORS + 错误处理
    ├── tests/                    # pytest 测试
    │   ├── conftest.py           # 测试 Fixtures
    │   ├── test_user.py          # 用户模块测试
    │   ├── test_practice.py      # 刷题模块测试
    │   └── test_agents/          # Agent 节点测试
    └── alembic/                  # 数据库迁移
        ├── env.py                # 迁移环境（异步）
        └── versions/             # 迁移脚本
```

---

## 快速开始

### 前置条件

- **Node.js** 18+
- **Python** 3.11+（推荐；3.7+ 基本可用但部分依赖受限）
- **LLM API Key**（DeepSeek 或其他 OpenAI 兼容接口）
- **Windows 用户额外步骤**：`chromadb` 需要 C++ 编译器。下载安装 [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)，安装时勾选 **"Desktop development with C++"** 工作负载。安装完成后继续下面的步骤。

### 1. 克隆项目

```bash
git clone <repo-url>
cd interview
```

### 2. 后端启动

```bash
cd backend

# 创建虚拟环境（推荐）
python -m venv .venv
# .venv\Scripts\activate    # Windows
# source .venv/bin/activate # Linux / macOS

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env        # 如无 .env.example，手动创建
# 编辑 .env，至少配置 LLM_API_KEY（留空则使用 Mock 模式）

# 回到项目根目录（uvicorn 需要从根目录启动才能找到 backend 包）
cd ..

# 启动服务
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

> **注意**：启动命令必须在项目根目录 `interview/` 下执行，而不是 `backend/` 下。因为代码中所有 import 都以 `backend.` 为前缀，Python 需要从根目录才能解析 `backend` 包。

数据库表会在首次请求时自动创建（`lifespan` 事件中调用 `init_db()`），无需手动初始化。

API 文档：启动后访问 [http://localhost:8000/docs](http://localhost:8000/docs)（Swagger UI）

### 3. 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev                 # http://localhost:5173
```

### 4. 环境变量配置

项目使用 OpenAI 兼容接口，默认接入 **DeepSeek**。在 `backend/.env` 中配置：

```env
# LLM 配置（必填，留空则 Mock 模式）
LLM_API_KEY=你的API_Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# Embedding 配置（可选，用于 RAG 向量检索）
# DeepSeek 不提供 Embedding API，推荐用 SiliconFlow（免费额度，注册即用）
EMBEDDING_API_KEY=你的Embedding_API_Key
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3

# 数据库（可选，默认 SQLite）
DATABASE_URL=sqlite+aiosqlite:///./data/interview.db

# 服务配置（可选）
HOST=0.0.0.0
PORT=8000
DEBUG=true

# CORS（可选）
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
```

**切换其他 LLM 提供商**（无需改代码，只改 .env）：

```env
# 智谱 GLM
LLM_API_KEY=你的key
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
LLM_MODEL=glm-4-flash

# 通义千问
LLM_API_KEY=你的key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-turbo
```

**Mock 回退模式**：未配置 `LLM_API_KEY` 时，系统自动使用 Mock 回退，返回预设题目和评分。功能可正常跑通，适合本地开发调试。若每次生成的题目都相同，说明处于 Mock 模式，请检查 API Key。

---

## 架构设计

### 当前架构（Phase 2 完成后）

```
Router → Service → LangGraph Agent（状态图编排）
                     ├── Validate Node
                     ├── Generate Node ←── RAG 检索 ←── Chroma ←── 知识库
                     ├── Evaluate Node ←── RAG 检索
                     ├── Adjust Node
                     └── Next / Decide Node
状态通过 Checkpoint（SQLite）持久化，支持断线恢复和回溯
```

### 核心设计

| 组件 | 职责 |
|------|------|
| **LangGraph StateGraph** | 状态图编排，每个节点职责单一，节点间通过条件边连接 |
| **TypedDict State** | 类型安全的状态定义，节点间传递和累积 |
| **SqliteSaver Checkpoint** | 每次节点执行后自动保存状态快照，断线恢复 |
| **interrupt_before** | 人机交互暂停点（如等待用户回答），配合 `aupdate_state` 恢复 |
| **Chroma VectorStore** | 文档分块 → Embedding → 存储 → 语义检索 |
| **SSE Stream** | `asyncio.Queue` 驱动的服务端推送，30s keepalive |

### 刷题 Agent 图结构

```
START → validate → generate → [interrupt: wait_answer]
    → evaluate → adjust → next → generate (loop) / END
```

### 面试 Agent 图结构

```
START → setup → ask_question → [interrupt: wait_answer]
    → provide_feedback → decide_next
        ├── follow_up → ask_question (loop)
        ├── next_round → ask_question (loop)
        └── report → generate_report → END
```

---

## API 概览

### 用户模块 `/api/user`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/user/register` | 注册 |
| POST | `/api/user/login` | 登录 |
| GET | `/api/user/` | 获取用户信息 |
| GET | `/api/user/resume` | 获取简历 |
| PUT | `/api/user/resume` | 保存简历 |
| POST | `/api/user/resume/parse` | AI 解析简历文件 |

### 刷题模块 `/api/practice`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/practice/start` | 创建刷题会话 |
| GET | `/api/practice/{id}/stream` | SSE 流（题目推送） |
| POST | `/api/practice/{id}/answer` | 提交答案 |
| POST | `/api/practice/{id}/next` | 请求下一题 |
| POST | `/api/practice/{id}/skip` | 跳过当前题 |
| GET | `/api/practice/{id}/status` | 查询会话状态 |
| GET | `/api/practice/stats` | 刷题统计数据 |

### 面试模块 `/api/interview`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/interview/create` | 创建面试会话 |
| GET | `/api/interview/{id}/stream` | SSE 流（问题推送） |
| POST | `/api/interview/{id}/answer` | 提交回答 |
| GET | `/api/interview/{id}/report` | 获取复盘报告 |
| GET | `/api/interview/{id}/status` | 查询会话状态 |

### 知识库模块 `/api/knowledge`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/knowledge/upload` | 上传文档（PDF/MD/TXT） |
| GET | `/api/knowledge/list` | 列出已上传文档 |
| DELETE | `/api/knowledge/{id}` | 删除文档及向量 |
| POST | `/api/knowledge/{id}/reindex` | 重建文档索引 |
| GET | `/api/knowledge/search?q=` | 搜索知识库 |
| GET | `/api/knowledge/categories` | 获取分类列表 |

### 历史模块 `/api/history`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/history/practice` | 刷题历史列表 |
| GET | `/api/history/practice/{id}` | 刷题会话详情 |
| DELETE | `/api/history/practice/{id}` | 删除刷题会话 |
| GET | `/api/history/interview` | 面试历史列表 |
| GET | `/api/history/interview/{id}` | 面试会话详情 |
| DELETE | `/api/history/interview/{id}` | 删除面试会话 |

---

## 日常开发命令

### 后端

```bash
# 启动开发服务器（在项目根目录 interview/ 下执行）
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 数据库迁移（在 backend/ 目录下执行）
cd backend
alembic revision --autogenerate -m "描述修改内容"
alembic upgrade head
alembic downgrade -1          # 回滚一步

# 运行测试（在项目根目录 interview/ 下执行）
pytest -v                    # 全部测试
pytest backend/tests/test_practice.py -v   # 指定模块
pytest -v --tb=short         # 短回溯

# 代码检查
cd backend
ruff check .
ruff format .
```

### 前端

```bash
cd frontend

# 启动开发服务器
npm run dev

# 类型检查
npx tsc --noEmit

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

### 知识库管理

```bash
# 搜索知识库
curl "http://localhost:8000/api/knowledge/search?q=Python装饰器&top_k=5"

# 上传文档
curl -X POST http://localhost:8000/api/knowledge/upload \
  -H "X-User-Id: 1" \
  -F "file=@notes.pdf" \
  -F "category=Python"
```

---

## 开发进度

| 模块 | 状态 | 说明 |
|------|------|------|
| 用户系统 | ✅ 完成 | 注册/登录，SHA-256 密码哈希 |
| 刷题模式 | ✅ 完成 | LangGraph Agent + RAG + Checkpoint 持久化 |
| 模拟面试 | ✅ 完成 | LangGraph Agent + RAG + 断线恢复 |
| 历史记录 | ✅ 完成 | 列表/详情/删除/统计 |
| 知识库 | ✅ 完成 | 上传/解析/向量化/搜索/管理 |
| RAG 集成 | ✅ 完成 | 出题/评估/面试出题均接入向量检索 |
| Agent 编排 | ✅ 完成 | LangGraph StateGraph + SqliteSaver |
| Alembic 迁移 | ✅ 完成 | 异步 env 配置，支持 autogenerate |
| pytest 测试 | ✅ 完成 | 用户/刷题/Agent 节点测试覆盖 |
| 断线恢复 | ✅ 完成 | Checkpoint + 内存缓存双重保障 |
| CI/CD | 📋 待做 | GitHub Actions 自动测试 |

---

## 设计文档

- [需求说明文档](需求说明.md)
- [前端技术设计文档](前端技术设计文档.md)
- [后端技术设计文档](后端技术设计文档.md)
- [迭代记录](迭代.md)
