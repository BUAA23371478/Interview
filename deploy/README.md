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
| `EMBEDDING_API_KEY` | SiliconFlow bge-m3 嵌入 Key（知识库检索，平台提供免费额度） | ✅ |
| `EMBEDDING_BASE_URL` | 默认 `https://api.siliconflow.cn/v1` | 可选 |
| `EMBEDDING_MODEL` | 默认 `BAAI/bge-m3` | 可选 |
| `DEBUG` | **必须为 `false`**（生产）。为 true 时无平台头回退 dev 用户，存在安全风险 | ✅ false |
| `ADMIN_ROLES` | 管理员角色，默认 `admin,developer` | 可选 |
| `MYSQL_HOST` 等 | 平台注入 MySQL（可选，未配置用 SQLite 持久卷） | 可选 |
| `LLM_API_KEY` | 可选。默认**留空**，LLM 由用户自带 Key（BYOK） | 否 |

> **LLM 收费策略**：平台不提供 LLM 额度。用户在前端「个人中心 → 模型设置」填入自己的
> API Key（DeepSeek / SiliconFlow 等 OpenAI 兼容服务），随 `X-LLM-Key` 请求头发送，服务器不落库。
> 未配置 Key 时，AI 面试/练习会明确报错引导配置（不会静默 mock）。知识库搜索用嵌入 Key 免费可用。

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
