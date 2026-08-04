# 🎯 AI 面试智能体（Interview Agent）

**生产级 AI 面试陪练应用**：模拟面试 + 专项练习 + 服务器端知识库（UGC 审核），部署于 MAOO 平台。

---

## ✨ 核心能力

| 模块 | 说明 |
|------|------|
| 🎤 **AI 模拟面试** | 上传 JD + 简历 → 8 个专职 Agent 协作：意图路由 / JD 解析 / 简历匹配 / 题目规划（30-50-20 难度分布）/ 面试主持（追问深挖）/ 评估打分（4 维）/ 复习计划（4 周） |
| 🧠 **动态难度 FSM** | 连对升级、连错降级（easy/medium/hard），模拟真实面试官策略 |
| 📚 **服务器端知识库** | 内置 48 篇精选文档（300+ 面试题 / 14 家公司岗位与面经）；混合检索（向量 + BM25 + RRF 融合 + 可选 LLM 精排） |
| 📤 **UGC 上传 + 审核** | 用户可上传技术文档/面经 → **AI 预审** → **管理员复核** → 入库。防污染：hash 快照 + 配额 + 全程留痕 |
| 🧑‍💼 **MAOO 用户系统** | 身份来自 `X-Maoo-*` 请求头，不自建登录；业务侧维护用户画像（薄弱点 / 技能雷达 / 错题本 / 学习足迹） |
| 📝 **专项练习** | 按主题 / 难度 / 公司风格（字节/阿里/腾讯/美团）刷题，逐题评分，错题自动沉淀 |
| 📊 **复盘报告** | 雷达图 + 维度评分 + 亮点/盲区 + 错题清单 + 4 周复习计划，写回长期记忆 |

---

## 🏗️ 技术架构

```
浏览器 (React SPA)
  │ baseURL=/app/interview-agent/api，localStorage 读平台 JWT
  ▼
MAOO 平台 Nginx（验证 JWT → 注入 X-Maoo-* 头 → 剥离前缀）
  ▼
FastAPI 后端（只监听 127.0.0.1:$PORT）
  ├─ Agent 编排层: IntentRouter → JDAnalyzer → ResumeAnalyzer → QuestionPlanner
  │               → Interviewer(追问) → Evaluator → StudyPlanner → ChatAgent
  ├─ RAG 层: 向量(SQLite) + BM25(jieba) + RRF 融合 + LLM rerank
  ├─ 记忆: 短期会话(Redis可选/内存) + 长期(SQLite 用户画像)
  ├─ 知识库: 内置种子 + 用户 UGC(AI预审 → admin 复核 → 建索引)
  └─ /health → {"status":"ok"}
```

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2.0 async · SQLite(WAL) / MySQL 可选 |
| LLM | DeepSeek（OpenAI 兼容）；未配置时**内置 mock** 可离线跑通全流程 |
| Embedding | bge-m3（SiliconFlow）；未配置时内置确定性 mock 向量 |
| RAG | 混合检索（向量+BM25+RRF）+ 可选 LLM rerank + 中文分块 |
| 前端 | React 18 + TypeScript + Vite（`base: /app/interview-agent/`）+ Tailwind |

---

## 🚀 本地开发

### 后端

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows；Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 可选：配置真实 LLM（不配置则用 mock 模式）
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY / EMBEDDING_API_KEY

# 构建内置知识库（把 /tmp/hub_kb 精选文档复制进 data/kb_seed）
python scripts/seed_kb.py /path/to/agent-interview-hub

# 启动（监听 8002）
uvicorn app.main:app --host 127.0.0.1 --port 8002
# 或 python -m app.main
```

### 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173/app/interview-agent/
```

Vite 开发服务器把 `/app/interview-agent/api` 代理到后端 8002。本地无平台头时，后端用
`DEV_USER_ID`（config 默认值）兜底。

### 测试

```bash
cd backend
python -m pytest tests/ -q        # 6 个用例：审核闭环/重复拦截/配额/面试流程/练习/会话隔离
```

---

## 🧪 本地体验（mock 模式）

不配置任何 API Key 即可完整跑通：

1. 打开前端 → **模拟面试** → 填 JD（如"招聘 AI Agent 工程师，熟悉 RAG"）+ 简历 → 开始
2. 逐题回答 → 评分 → 追问 → 报告（雷达图 + 4 周计划）
3. **知识库** → 搜索"Transformer 自注意力" → 上传文档 → 等待审核
4. 用 admin 身份（`X-Maoo-User-Role: admin` 请求头）访问**审核中心** → 通过 → 可检索

> 填入真实 `LLM_API_KEY` / `EMBEDDING_API_KEY` 后自动切换到真实模型，prompt 完全兼容。

---

## 📦 MAOO 部署

见 [deploy/README.md](deploy/README.md)。核心步骤：

```bash
bash deploy/build.sh    # 生成 frontend/dist.zip + backend/backend-deploy.zip
```

1. 平台创建应用（前后端分离，slug=`interview-agent`）
2. 上传 `dist.zip` + `backend-deploy.zip`
3. 配置 `LLM_API_KEY` / `EMBEDDING_API_KEY` 等环境变量
4. 提交审核 → 发布 → 访问 `/app/interview-agent/`

---

## 🔒 知识库审核机制（防污染）

```
用户上传(md/txt/pdf ≤50MB)
  → 基础校验（格式/大小/空内容/重复 hash）
  → 反刷配额（每日 N 篇 / 字数上限）
  → AI 预审（LLM：技术相关性/有害内容/重复检测 → 推荐分类 + 通过分）
  → pending 待审队列
  → 管理员复核（X-Maoo-User-Role ∈ admin/developer）
      ├─ approve → hash 比对 → 分块 → 向量+BM25 双索引 → approved
      └─ reject  → 留痕（review_logs）
```

- 普通用户只能浏览/检索 `approved` 文档
- 内容快照 + SHA-256 比对防篡改
- 审核日志（上传/AI预审/通过/拒绝）全程可追溯

---

## 📁 目录结构

```
interview/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口（lifespan 建表 + 种子索引）
│   │   ├── config.py          # pydantic-settings（PORT/LLM/审核阈值）
│   │   ├── llm.py             # OpenAI 兼容 LLM + mock 回退
│   │   ├── embedding.py       # 嵌入客户端 + mock 回退
│   │   ├── deps.py            # X-Maoo-* 用户依赖
│   │   ├── agents/            # 8 个专职 Agent + 难度 FSM
│   │   ├── rag/               # loader / vector_store / bm25 / hybrid / engine
│   │   ├── memory/            # 短期会话 + 长期画像
│   │   ├── services/          # interview / practice / kb(审核)
│   │   ├── routers/           # auth / kb / interview / practice / health
│   │   └── sse/               # SSE 事件流
│   ├── scripts/seed_kb.py     # 内置知识库构建
│   ├── data/kb_seed/          # 种子文档（gitignore 的 data/ 之外的源码）
│   ├── tests/                 # pytest
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                  # React 18 + Vite + TS
├── deploy/                    # MAOO 打包脚本 + 部署指南
└── README.md
```

---

## 🙏 参考项目与致谢

本项目在设计与实现上参考了以下开源项目，在此致谢：

| 参考项目 | 贡献点 | 仓库 |
|---------|--------|------|
| **AI_InterviewerAgent** | 多 Agent 协作编排、混合检索 RAG（向量 + BM25 + RRF）、Redis/MySQL 双引擎记忆、难度状态机、Skill 技能系统 | [BMN-zyb/AI_InterviewerAgent](https://github.com/BMN-zyb/AI_InterviewerAgent) |
| **interview-practice** | 简历驱动的个性化出题、复盘报告格式、追问与评分流程、错题本与学习笔记闭环 | [guijiamin/interview-practice](https://github.com/guijiamin/interview-practice) |
| **agent-interview-hub** | 知识库内容来源：300+ 带答案面试题、14 家公司岗位要求与面经、深度技术文档 | [zchary1106/agent-interview-hub](https://github.com/zchary1106/agent-interview-hub) · [在线知识库](https://zchary1106.github.io/agent-interview-hub/) |

> 参考项目源码存放于本地 `参考项目/` 目录（不进版本库），用于开发期对照。本项目在其基础上
> 新增了 **MAOO 平台用户系统集成**、**服务器端知识库 + UGC 上传审核机制**（AI 预审 + 管理员复核 +
> 防污染）以及**生产级部署封装**。
