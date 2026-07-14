# AI 智能刷题与模拟面试系统

基于 AI 的技术面试备考工具，提供**刷题模式**与**模拟面试模式**两种核心练习方式。

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
- 难度自适应：连续答对升级，连续答错降级
- 历史记录追踪，自动识别薄弱主题

### 模拟面试模式
- 粘贴目标岗位 JD 和个人简历
- 自定义面试轮数（3-20 轮）
- AI 模拟面试官一问一答，支持追问机制
- 结束后生成多维度复盘报告（技术深度/表达清晰度/逻辑性/岗位匹配度）

## 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| 前端 | React 19 + TypeScript + Vite + TailwindCSS | SPA 应用，Hash 路由 |
| 后端 | Python FastAPI + LangGraph + SQLite | 异步 API，SSE 流式输出 |
| AI | LLM（OpenAI 兼容接口） | 智谱 GLM-4 / 通义千问 / DeepSeek |

## 项目结构

```
interview/
├── README.md                    # 项目说明（本文件）
├── 需求说明.md                   # 需求分析文档
├── 前端技术设计文档.md            # 前端技术设计
├── 后端技术设计文档.md            # 后端技术设计
├── frontend/                    # 前端项目
│   ├── src/
│   │   ├── pages/               # 10 个页面组件
│   │   ├── components/          # 12 个共享 UI 组件
│   │   ├── hooks/               # 3 个自定义 Hook
│   │   ├── api/                 # 5 个 API 模块
│   │   ├── reducers/            # 2 个状态机 Reducer
│   │   ├── contexts/            # 全局状态
│   │   ├── types/               # TypeScript 类型
│   │   └── utils/               # 工具函数
│   └── 开发说明文档.md            # 前端开发说明
└── backend/                     # 后端项目（已完成核心链路）
    ├── main.py
    ├── routers/
    ├── services/
    ├── agents/
    ├── models/
    └── 开发说明文档.md
```

## 快速开始

### 前置条件
- Node.js 18+
- Python 3.11+
- LLM API Key（如 DeepSeek）

### 前端启动

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

### LLM API Key 配置

项目使用 OpenAI 兼容接口，默认接入 **DeepSeek**。也支持任意兼容接口（智谱 GLM / 通义千问 / OpenAI 等）。

**获取 API Key：**
1. 访问 [DeepSeek 开放平台](https://platform.deepseek.com) 注册账号
2. 在 [API Keys 页面](https://platform.deepseek.com/api_keys) 创建 API Key
3. 将 Key 填入 `backend\.env` 的 `LLM_API_KEY` 字段

**切换其他 LLM 提供商：** 修改 `backend\.env` 中的以下配置即可，无需改代码：

```env
# DeepSeek（默认）
LLM_API_KEY=你的key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# 示例：智谱 GLM
# LLM_API_KEY=你的key
# LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
# LLM_MODEL=glm-4-flash
```

**Mock 回退模式：** 如果未配置 `LLM_API_KEY`（留空），系统会自动使用 Mock 回退，返回预设的题目和评分。Mock 模式下所有功能仍可正常跑通，方便本地开发调试。若看到每次生成的题目都相同，说明正处于 Mock 模式，请检查 API Key 是否已正确配置。

### 后端启动

```bash
pip install -r backend/requirements.txt
copy backend\.env.example backend\.env
# 编辑 backend\.env，填入 LLM_API_KEY（可选，留空则使用 Mock 模式）
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## 开发进度

| 模块 | 状态 | 说明 |
|------|------|------|
| 需求文档 | ✅ 完成 | 需求分析 + 数据模型 + MVP 里程碑 |
| 前端技术设计 | ✅ 完成 | 路由/组件树/状态机/SSE协议/API清单 |
| 后端技术设计 | ✅ 完成 | 架构/Agent/LLM客户端/数据库设计 |
| 前端开发 | ✅ 完成 | 类型检查通过，生产构建通过 |
| 后端开发 | ✅ 完成 | FastAPI + SQLite WAL + SSE + DeepSeek |
| 用户系统 | ✅ 完成 | 注册/登录，SHA256 密码哈希 |
| 刷题模式 | ✅ 初步通过 | 出题/回答/跳过/去重/上限/断线恢复 |
| 模拟面试 | ⏳ 待测试 | 后端完整，前端待联调 |
| 历史记录 | ✅ 完成 | 可展开详情、删除、续答 |
| Agent 优化 | 📋 下一步 | RAG + 向量数据库 + LangGraph 编排 |

## 设计文档

- [需求说明文档](需求说明.md)
- [前端技术设计文档](前端技术设计文档.md)
- [后端技术设计文档](后端技术设计文档.md)
- [前端开发说明](frontend/开发说明文档.md)
- [后端开发说明](backend/开发说明文档.md)
