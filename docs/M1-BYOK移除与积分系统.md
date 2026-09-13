# M1 · BYOK 移除 + 平台用户适配 + 积分系统

> **完成时间**：2026-09-13 15:50
> **提交**：本轮 `M1 提交将含以下变更`（55 passed）
> **目标**：把上一轮 `opt/v1 + opt2` 里的 BYOK 模式（用户自带 LLM Key 经 `X-LLM-Key` 头注入）从代码、配置、文档、测试全链路清除，引入「平台 key + 用户积分」单一模式；MAOO 平台仅用作用户识别，业务表全部自有。

---

## 一、本轮变更概览

| 模块 | 变更 |
|---|---|
| `app/llm.py` | **删除** `llm_api_key_ctx` contextvar、`set_llm_key_context()` 函数；改 `byok` 字段为 `enabled`/`server_key`；改 `_NO_KEY_ERROR` 文案 |
| `app/deps.py` | **重写**：声明 `require_login` 不再接受 `X-LLM-Key` 请求头；改用 `app.platform.resolve_chain` 解析用户 |
| `app/platform/__init__.py` + `app/platform/maoo.py` | **新增**：MAOO 平台适配层（`MaooPlatform` / `LocalDevPlatform` / `resolve_chain`），业务侧与具体平台解耦 |
| `app/models.py` | 不变：`User` 表就是业务子用户表（关联 `maoo_user_id`） |
| `app/gateway/credits.py` | 不变：预扣/结算/释放/充值/幂等 早已就位 |
| `app/routers/auth_router.py` | **删除** `/auth/test-llm` 端点（业务侧不再接收 BYOK） |
| `app/routers/billing_router.py` | 不变：5 个端点已就位 |
| `frontend/src/api/client.ts` | **删除** `LLM_KEY_STORAGE` / `getLlmKey()` / 任何 `X-LLM-Key` 头；新增 402 积分不足自动跳转 `/billing` |
| `frontend/src/api/auth.ts` | **删除** `authApi.testLlm()`；新增 `authApi.credits()` / `authApi.recharge()` |
| `frontend/src/pages/Profile.tsx` | **重写**：删除「自带 API Key」输入卡，替换为「积分账户」充值卡 |
| `backend/Dockerfile` | **改注释**：BYOK → 服务端托管 |
| `backend/tests/test_reliability.py` | **改名**：`test_byok_pool_*` → `test_provider_key_pool_*` |
| `backend/tests/test_byok_removed.py` | **新增**：10 个回归用例，覆盖平台适配链 + BYOK 全清除 + 积分不足拒绝 + 充值幂等 |
| `docker-compose.yml` | **新增**：项目根一键启动 MySQL+Redis+Backend，含健康检查、依赖顺序、卷挂载 |

---

## 二、关键设计决策

### 2.1 为什么完全删除 BYOK 而不是保留为可选开关

> **用户决策**：BYOK 与「平台 key + 积分充值」模式互斥；保留双轨会让凭据解析出现「先 BYOK 还是先平台 key」的歧义，跨用户审计时也无法回答「这一调用到底用了谁的 key」。二选一是工程上的干净选择。

技术细节：
- `app/llm.py:UnifiedLLMClient._key_for_provider(provider)` 现在只调 `settings.provider_key(provider)`
- 业务侧读不到任何用户携带 key 的入口（请求头、cookie、数据库都没有）
- 多租户隔离仍由 `X-Maoo-User-Id` 头保证——平台已校验 JWT，业务侧信任头部即可

### 2.2 平台适配层的最小可插拔抽象

```python
class PlatformAdapter(ABC):
    name: str
    @abstractmethod
    async def resolve(self, headers: dict) -> Optional[ResolvedUser]: ...
```

- `MaooPlatform` 解析 `X-Maoo-*` 头部（生产）
- `LocalDevPlatform` 在 `debug=True` 时返回 dev_user（本地）
- `resolve_chain(headers)` 顺序尝试，第一个非 None 的结果胜出
- 新增 SSO / Keycloak / 企业微信：写一个 `SsoPlatform` 加入 `_DEFAULT_CHAIN`，依赖层不动

这是为了未来切换身份系统时**业务层一行代码不改**——用户表/积分表/知识库/会话/Agent 全部不知道也不关心你用的是哪个平台。

### 2.3 业务子用户表（sub_user）就是 User 表

`User` 表就是业务侧子用户表：
- `maoo_user_id`（unique）= MAOO 平台用户 id
- `username` / `role` / `level`（normal/vip/admin）
- `credits`（冗余字段：与 `CreditAccount.balance` 同步）

不需要新建 `sub_user` 表。**MAOO 用户首次访问** → `app/memory/long_term.py::get_or_create_user()` 自动建 User + 赠 `DEFAULT_CREDIT_GRANT`（默认 10000 积分 ≈ 10 元）。

### 2.4 积分系统（早已实现，本轮不动）

- `app/gateway/credits.py::ensure_account()`：自动开户 + 赠额 + 写 grant 流水
- `pre_deduct()` / `settle()` / `release()`：预扣 → 结算（多退少补）→ 失败退回
- 幂等键 `(request_id, kind)`：客户端/网关重试不会重复扣费
- `recharge(maoo_user_id, credits, order_id=...)`：充值占位实现，`order_id` 留作接入真实支付后的幂等键

新增的 `402 Payment Required` 语义：积分不足时 LLM 调用直接被 `pre_deduct()` 拒绝（返回 `reason="insufficient"`），FastAPI 异常处理会映射到 402，前端 `client.ts` 拦截 402 自动跳 `/billing`。

---

## 三、测试覆盖（10 个新增，全绿）

| 测试 | 验证点 |
|---|---|
| `test_platform_adapter_chain_resolves_maoo_first` | MAOO 头部存在时优先用 MAOO，LocalDev 不被调用 |
| `test_platform_adapter_chain_falls_back_to_local_dev` | 无 MAOO 头时（debug=True）回退 dev_user |
| `test_platform_adapter_rejects_invalid_user_id_in_production` | 生产模式下非法 user_id 不兜底 |
| `test_byok_header_is_completely_ignored` | `X-LLM-Key` 头不被读——`_key_for_provider` 完全走服务端 settings |
| `test_llm_module_exposes_no_byok_api` | `app.llm` 公共 API 不再有 `set_llm_key_context` / `llm_api_key_ctx` |
| `test_deps_require_login_does_not_take_x_llm_key` | FastAPI 依赖函数签名不含 `x_llm_key` 参数 |
| `test_pre_deduct_rejects_insufficient_balance` | 余额为 0 时预扣返回 `ok=False, reason="insufficient"` |
| `test_recharge_is_idempotent_by_order_id` | 同 `order_id` 二次充值只入账一次 |
| `test_frontend_client_does_not_send_x_llm_key` | 前端 client.ts 不再有 X-LLM-Key 头 |
| `test_frontend_profile_no_longer_exposes_byok_input` | 前端 Profile 页面无 BYOK 输入框 |

总计：**55 passed in 4:23**（45 原有 + 10 新增）。

---

## 四、本轮改动前后对比

| 维度 | 改前 | 改后 |
|---|---|---|
| 用户自带 key 入口 | `X-LLM-Key` 请求头（前端 localStorage） | 无 |
| LLM 凭据来源 | `request_key`（contextvar） > `server_key` | 仅 `server_key`（按 provider） |
| BYOK / 平台 key 优先级歧义 | 存在 | 不存在（无 BYOK） |
| 跨用户审计难度 | 中（两路 key） | 低（单路 key） |
| 平台适配层 | 隐式（直接读头） | 显式（`PlatformAdapter` 协议） |
| 切换 SSO / Keycloak | 需要改 deps.py | 加一个 PlatformAdapter |
| 充值接口 | 占位存在 | 占位存在（与 M1 之前无差异） |
| 测试用例 | 45 | 55（+10 BYOK 移除回归） |

---

## 五、运行验证

```bash
# 后端测试
cd backend
pytest -q tests                    # 55 passed in 4:23

# 一键启动（docker-compose 雏形，docker 引擎可用时）
docker compose up -d               # 启动 mysql + redis + backend
docker compose logs -f backend     # 看后端启动日志
curl http://127.0.0.1:8002/health  # 健康检查
```

> **本机 docker 引擎暂不可用**（上一轮已确认进程无法跨工具调用存活），
> compose 文件已就绪，下次 Docker 引擎恢复可立即起。
> 当前 M1 验证全靠 pytest 完成。

---

## 六、下一轮（M2）预告

进入**企业级架构骨架**：
- asyncio.Queue 异步任务队列
- Redis Lua 滑动窗口限流（全局/用户/IP 三档）
- asyncmy pool + Redis Sentinel 连接池配置
- 多实例 backend（gunicorn -w 4）
- bench/stress_test.py 压测脚本
- 目标：100 并发 / 10000 用户容量

具体细节见 `docs/优化规划-v2.md` § 二 · M2。