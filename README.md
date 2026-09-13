# 🎯 AI 面试智能体（Interview Agent）

> **多 LLM Provider 网关 + RAG 混合检索 + 8 Agent 编排 + 企业级并发** 的 AI 面试陪练平台。
> 部署于 MAOO 平台（生产）/ docker compose 一键起（本地演示）。

---

## 📑 文档入口

| 文档 | 用途 | 受众 |
|------|------|------|
| **[docs/优化总结报告.md](docs/优化总结报告.md)** | 主报告：架构 / 5 轮迭代 / 评测数据 / 名词表 | 想完整了解项目的人 |
| **[docs/PPT大纲-技术深.md](docs/PPT大纲-技术深.md)** | 32 页面试 PPT 大纲（技术深版） | 面试时讲给技术 Leader |
| **[docs/PPT大纲-项目展示.md](docs/PPT大纲-项目展示.md)** | 15 页面试 PPT 大纲（项目展示版） | 面试时讲给非技术面试官 |
| **[docs/名词解释.md](docs/名词解释.md)** | 60+ 术语新手版（类比 + 通俗解释） | 从零了解 LLM/RAG/Agent |

> 建议阅读顺序：**优化总结报告 → PPT 大纲（与场景对应） → 名词解释（遇到不懂的概念时翻）**。

---

## ✨ 核心能力

| 模块 | 说明 |
|------|------|
| 🎤 **AI 模拟面试** | 上传 JD + 简历 → 8 个专职 Agent 协作：意图路由 / JD 解析 / 简历匹配 / 题目规划（30-50-20 难度分布）/ 面试主持（追问深挖）/ 评估打分（4 维）/ 复习计划（4 周） |
| 🧠 **动态难度 FSM** | 连对升级、连错降级（easy/medium/hard），模拟真实面试官策略 |
| 📚 **多学科知识库** | 8 学科 48 篇精选文档（计算机/测试/产品/工业设计/经济学/英语/法学/哲学）；混合检索（向量 + BM25 + 双模式融合 + 可选 LLM 精排） |
| 🔌 **多 LLM Provider 网关** | DeepSeek / Qwen / Kimi / SiliconFlow 统一接入，任务级路由 + 跨端点降级链 + 三态熔断 + 成本护栏 |
| 💰 **积分系统** | 平台托管 LLM Key，用户充值得积分，按调用量扣费；充值幂等；余额不足 402 |
| 🏛️ **平台用户适配层** | `PlatformAdapter` 协议抽象，业务侧只与 `ResolvedUser` 接口交互，MAOO / 独立部署可热切换 |
| 🧑‍💼 **MAOO 用户系统** | 身份来自 `X-Maoo-*` 请求头；业务侧维护用户画像（薄弱点 / 技能雷达 / 错题本 / 学习足迹） |
| 📤 **UGC 上传 + 审核** | 用户可上传技术文档/面经 → **AI 预审** → **管理员复核** → 入库。防污染：hash 快照 + 配额 + 全程留痕 |
| 📝 **专项练习** | 按主题 / 难度 / 公司风格（字节/阿里/腾讯/美团）刷题，逐题评分，错题自动沉淀 |
| 📊 **复盘报告** | 雷达图 + 维度评分 + 亮点/盲区 + 错题清单 + 4 周复习计划，写回长期记忆 |
| 🚦 **企业级并发** | Redis Lua 滑动窗口限流（全局/用户/IP 三档）+ asyncio 优先级队列 + Gunicorn 多实例 |

---

## 🏗️ 技术架构

```
浏览器 (React SPA, baseURL=/app/interview-agent/api)
  │
  ▼
MAOO 平台 Nginx（验证 JWT → 注入 X-Maoo-* 头 → 剥离前缀）
  │
  ▼
FastAPI 后端（Gunicorn + UvicornWorker × N 进程）
  ├─ 限流层: Redis Lua 滑动窗口（全局 500 QPS / 每用户 20 QPS / 每 IP 50 QPS）
  ├─ 平台适配层: PlatformAdapter → MaooPlatform / LocalDevPlatform
  ├─ 积分层: 预扣 → 调用 → 结算（幂等键: request_id+kind）
  ├─ Agent 编排层: IntentRouter → JDAnalyzer → ResumeAnalyzer → QuestionPlanner
  │               → Interviewer(追问) → Evaluator → StudyPlanner → ChatAgent
  │               ↓ (统一收口) BaseAgent.invoke_llm
  ├─ 网关层: ModelRegistry + Router(任务级策略) + Breaker(三态熔断) + Fallback(跨端点降级)
  ├─ RAG 层: EmbeddingCache(SQLite) → VectorStore(faiss HNSW 或 numpy) + BM25(jieba)
  │           → Hybrid(score_norm/RRF 双模式) → Rerank(bge-reranker / Aliyun qwen3.7)
  ├─ 记忆层: Redis 短期会话(快照 24h TTL) + MySQL/SQLite 长期画像
  ├─ 知识库: 内置 48 篇多学科种子 + 用户 UGC(AI预审 → admin 复核 → 建索引)
  └─ /health → {"status":"ok", "deps":{redis,mysql,embedding,rerank,llm}}
```

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2.0 async · asyncmy 连接池 (pool=20) · Gunicorn + UvicornWorker |
| LLM 网关 | OpenAI 兼容 SDK（DeepSeek/Qwen/Kimi/SiliconFlow）；任务级路由 + 三态熔断 + 跨端点降级 + 思考模式空回答自愈 |
| Embedding | bge-m3（SiliconFlow API），SQLite 磁盘向量缓存，批量并发 |
| Rerank | bge-reranker-v2-m3（主）→ qwen3.7-text-rerank（Aliyun 降级链） |
| RAG | score_norm / RRF 双融合模式 + 滑动窗口平滑；实测最优 vw=0.5/bw=0.5 |
| 限流 | Redis Lua 滑动窗口（O(1) 内存，原子 check-then-act） |
| 队列 | asyncio 优先级队列（10 桶 × 8 worker），handler 注册式 |
| 前端 | React 18 + TypeScript + Vite（`base: /app/interview-agent/`）+ Tailwind |
| 部署 | docker compose（mysql + redis + backend）/ MAOO 平台（一键发版） |

> **LLM 收费策略**：平台持有 LLM Key（DeepSeek / Qwen 等 OpenAI 兼容服务）。
> 用户通过充值积分使用 LLM 能力；积分按调用 token 数扣费。余额不足时后端返回 402 Payment Required。
> 知识库嵌入用平台免费额度。

---

## 🚀 本地启动

### 方式 A · docker compose（推荐）

```bash
cd E:\Study\MA\Interview
docker compose up -d            # MySQL 8.0 + Redis 7 + Backend 一键起
# 健康检查：curl http://127.0.0.1:8002/health
```

### 方式 B · 手动起后端 + 前端

```bash
# 后端
cd backend
python -m venv .venv && .venv/Scripts/activate    # Windows
pip install -r requirements.txt
cp .env.example .env                              # 填写 LLM/Embedding/Rerank 凭据
python -m pytest tests/ -q                        # 63 个回归用例

# 启动后端（监听 8002）
uvicorn app.main:app --host 127.0.0.1 --port 8002

# 前端（新终端）
cd frontend
npm install
npm run dev        # http://localhost:5173/app/interview-agent/
```

Vite 开发服务器把 `/app/interview-agent/api` 代理到后端 8002。本地无平台头时，后端用
`DEV_USER_ID`（config 默认值）兜底。

### 知识库初始化

```bash
# 1. 生成多学科种子（8 学科 48 篇）
python bench/seed_multidisciplinary.py

# 2. 批量入库并建向量+BM25 索引
python bench/ingest_multidisciplinary.py

# 3. 验证检索质量
python bench/gen_multi_queries.py     # 生成跨学科查询集 → 49 条
python bench/retrieval_eval.py        # 自动调用默认查询集评测
#   期望：跨学科 R@1 > 95%
```

---

## 🧪 评测基线（v2 实测数据）

| 评测维度 | 指标 | 数值 | 评测脚本 |
|---|---|---|---|
| 跨学科检索 | R@1 | **97.2%** | `bench/retrieval_eval.py` |
| 跨学科检索 | R@5 | **98.5%** | 同上 |
| 出题质量 | LLM-as-judge (满分 2.0) | **1.90** | `bench/question_eval.py` |
| 追问质量 | LLM-as-judge (满分 2.0) | **1.97** | 同上 |
| 端到端 | 练习 9/9 + 模拟面试 7/7 | **16/16 全过** | `bench/e2e_eval.py` |
| 压力测试 | 100 并发协程 P95 | （待跑） | `bench/stress_test.py` |
| 测试覆盖 | pytest | **63 passed in 5:29** | `backend/tests/` |

> 评测明细见各评测脚本同名的 `*_result.md` 文件；完整分析见 `docs/优化总结报告.md`。

---

## 📦 MAOO 部署

1. 平台创建应用（前后端分离，slug=`interview-agent`）
2. 构建：`bash deploy/build.sh`（生成 `dist.zip` + `backend-deploy.zip`）
3. 上传两份压缩包
4. 配置环境变量：`LLM_PROVIDER_KEYS`、`EMBEDDING_API_KEY`、`RERANK_FALLBACKS`、`DB_*`、`REDIS_*`
5. 提交审核 → 发布 → 访问 `/app/interview-agent/`

详细平台开发规范见 [`开发部署指导文档.md`](开发部署指导文档.md)。

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
│   │   ├── main.py                 # FastAPI 入口（lifespan 建表 + 限流初始化）
│   │   ├── config.py               # pydantic-settings
│   │   ├── deps.py                 # 用户依赖（PlatformAdapter）
│   │   ├── llm.py                  # OpenAI 兼容 LLM + 跨端点降级 + 思考模式自愈
│   │   ├── embedding.py            # 嵌入客户端 + SQLite 缓存
│   │   ├── platform/               # MAOO 平台适配层（可热切换）
│   │   │   ├── maoo.py             # MaooPlatform（生产）+ LocalDevPlatform（独立运行）
│   │   ├── gateway/                # 多 Provider 网关
│   │   │   ├── registry.py         # 模型注册表（实测可用模型）
│   │   │   ├── router.py           # 任务级路由策略
│   │   │   ├── breaker.py          # 三态熔断
│   │   │   └── credits.py          # 积分预扣+结算
│   │   ├── ratelimit/              # Redis Lua 滑动窗口限流
│   │   ├── queue/                  # asyncio 优先级队列
│   │   ├── observability.py        # Meter / span / 成本流水
│   │   ├── agents/                 # 8 个专职 Agent + 难度 FSM
│   │   ├── rag/                    # loader / vector_store / bm25 / hybrid / rerank / engine
│   │   ├── memory/                 # 短期会话(Redis) + 长期画像
│   │   ├── services/               # interview / practice / kb(审核)
│   │   ├── routers/                # auth / kb / interview / practice / billing / health
│   │   └── sse/                    # SSE 事件流
│   ├── scripts/seed_kb.py          # 内置知识库构建
│   ├── data/                       # 运行时数据（gitignore）
│   ├── tests/                      # pytest（63 用例）
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                       # React 18 + Vite + TS
├── bench/                          # 评测 + 工具脚本
│   ├── retrieval_eval.py           # 跨学科检索评测
│   ├── question_eval.py            # 出题/追问 LLM-as-judge
│   ├── e2e_eval.py                 # 端到端冒烟
│   ├── stress_test.py              # 并发压测
│   ├── seed_multidisciplinary.py   # 多学科种子生成
│   ├── ingest_multidisciplinary.py # 批量入库
│   ├── gen_multi_queries.py        # 查询集生成
│   ├── probe_models.py             # 模型可用性探活
│   ├── probe_providers.py          # Provider 端点探活
│   ├── smoke_rerank_fallback.py    # rerank 降级链冒烟
│   ├── reset_index.py              # 索引库清理
│   └── *_result.{md,json}          # 评测结果
├── deploy/                         # 部署脚本（MAOO 打包 + docker compose）
├── docs/                           # 主报告 / PPT 大纲 / 名词解释
├── docker-compose.yml              # 一键起 mysql+redis+backend
├── 开发部署指导文档.md              # MAOO 平台开发规范
└── README.md                       # 本文件
```

---

## 🙏 参考项目与致谢

本项目在设计与实现上参考了以下开源项目：

| 参考项目 | 贡献点 | 仓库 |
|---------|--------|------|
| **AI_InterviewerAgent** | 多 Agent 协作编排、混合检索 RAG、Redis/MySQL 双引擎记忆、难度状态机、Skill 技能系统 | [BMN-zyb/AI_InterviewerAgent](https://github.com/BMN-zyb/AI_InterviewerAgent) |
| **interview-practice** | 简历驱动的个性化出题、复盘报告格式、追问与评分流程、错题本与学习笔记闭环 | [guijiamin/interview-practice](https://github.com/guijiamin/interview-practice) |
| **agent-interview-hub** | 知识库内容来源：300+ 带答案面试题、14 家公司岗位要求与面经、深度技术文档 | [zchary1106/agent-interview-hub](https://github.com/zchary1106/agent-interview-hub) · [在线知识库](https://zchary1106.github.io/agent-interview-hub/) |

> 参考项目源码存放于本地 `参考项目/` 目录（不进版本库），用于开发期对照。本项目在其基础上
> 新增了 **MAOO 平台用户系统集成**、**服务器端知识库 + UGC 上传审核机制**、
> **多 LLM Provider 网关（任务级路由 + 三态熔断 + 跨端点降级）**、
> **Redis 滑动窗口限流 + asyncio 优先级队列**、**多学科知识库 + 端到端评测基建**。