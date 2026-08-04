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
| `LLM_API_KEY` | DeepSeek API Key | ✅（否则 mock 模式） |
| `LLM_BASE_URL` | 默认 `https://api.deepseek.com/v1` | 可选 |
| `LLM_MODEL` | 默认 `deepseek-chat` | 可选 |
| `EMBEDDING_API_KEY` | SiliconFlow bge-m3 嵌入 Key | 推荐（否则 mock 向量，检索质量下降） |
| `EMBEDDING_BASE_URL` | 默认 `https://api.siliconflow.cn/v1` | 可选 |
| `EMBEDDING_MODEL` | 默认 `BAAI/bge-m3` | 可选 |
| `MYSQL_HOST` 等 | 平台注入 MySQL（可选，未配置用 SQLite 持久卷） | 可选 |
| `ADMIN_ROLES` | 管理员角色，默认 `admin,developer` | 可选 |

平台自动注入 `PORT` / `BASE_URL`，后端监听 `$PORT`，无需手动配置。

---

## 五、数据库

MAOO 平台不托管数据库实例。两种选择：

1. **SQLite（默认）**：数据落在容器持久卷 `backend/data/interview.db`，单机零运维。
2. **MySQL**：在平台创建应用时填写 MySQL 连接信息，后端检测到 `MYSQL_HOST` 自动切换
   （同 ORM，无需迁移）。

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

---

## 八、更新流程

取消发布 → 回到草稿 → 重新上传两个 zip → 提交审核 → 重新发布。
