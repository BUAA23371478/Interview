# AI 面试智能体 · 面试讲解 PPT（技术深版）

> **受众**：技术 Leader / 架构师 / 资深工程师
> **总页数**：32 页
> **讲解时长**：20-25 分钟
> **配套项目**：`E:\Study\MA\Interview`

---

## P1. 封面（1 页）

**主标题**：AI 面试智能体 — 8 Agent 编排的企业级 LLM 应用
**副标题**：从单点 LLM 调用到百人并发 / 万人容量的端到端演进
**讲者信息**：项目作者 / 资深测试工程师（瑞星 ESM3.0）
**关键数字**（右下角小角标）：
- 8 个专职 Agent
- 63 测试 / 5:29 全绿
- ¥0.16 跑通完整 e2e 评测
- 5 轮迭代（M1-M5）

---

## P2. 项目定位（1 页）

**标题**：这项目解决什么？

**3 行要点**：
1. **不是 demo**：能上线给万人用（架构层 + 数据层都按生产设计）
2. **不是玩具**：跨 8 学科知识库 / RAG 召回率 97.2% / 出题追问质量 95-98%
3. **不是单点**：8 Agent 编排 + 多 LLM 路由 + 多副本部署 + 完整监控

**底部**：架构总览图（占下半页）
```
[平台: MAOO] → [PlatformAdapter] → [业务侧 ResolvedUser]
                                          ↓
   [Web: React+Vite] → [API: FastAPI] → [8 Agents] → [LLM Gateway]
                                          ↓              ↓
                                    [RAG: 97 docs]   [DeepSeek/Aliyun/SiliconFlow]
                                          ↓              ↓
                                    [MySQL+Redis]   [熔断+降级链]
```

---

## P3. 关键技术挑战（1 页）

**4 个 P0 问题（按发现顺序）**：

| # | 问题 | 影响 |
|---|---|---|
| 1 | 全局单一 LLM Key，路由切模型时 401 | 降级链形同虚设 |
| 2 | 思考模式静默返回空正文 | 流式问答用户看不到答案 |
| 3 | 检索融合权重写死 | 实际数据反而变差 |
| 4 | 单实例 asyncio.Lock，多副本失效 | 脏写 |

**继续追问**：你怎么知道这些问题存在？答：实测探活（bench/probe_models.py）

---

## P4. 解决思路：先建评测基建（1 页）

**关键论断**：**没有评测的优化都是赌博**

```
                  ┌──────────────────────────┐
   上线前 ───→    │  评测基建（5 类）        │
                  │  · 模型可用性            │
                  │  · 检索质量              │
                  │  · 出题/追问质量         │
                  │  · 端到端冒烟            │
                  │  · 压力测试              │
                  └──────────────────────────┘
                              ↓
                  每个优化都要回放这 5 类评测
                  证明「数据更好 / 不退化」
```

---

## P5. 架构总览：分层设计（1 页）

**5 层架构**：

| 层 | 组件 | 关注点 |
|---|---|---|
| 接入 | React 前端 + API 网关 | 限流 / 鉴权 / CORS |
| 业务 | FastAPI + 8 Agents | 编排 / 状态 / 业务规则 |
| 能力 | LLM Gateway + RAG Engine | 模型路由 / 检索 / 精排 |
| 数据 | MySQL + Redis + SQLite(WAL) | 持久化 / 缓存 / 短期记忆 |
| 基础设施 | Docker + 多实例 + 健康检查 | 部署 / 弹性 / 监控 |

---

## P6. LLM 网关：多 provider 路由（2 页）

**第 1 页 — 设计动机**：
- 真实业务中：DeepSeek 触限 / 阿里云服务降级 / SiliconFlow 限流都是常态
- 单一 provider = 单一故障点
- 必须有"主备跨厂商"的降级链

**第 2 页 — 实现要点**：
- `ModelSpec` 注册表：每个模型一个独立条目
- 任务级 `RouteSpec`：主模型 + 降级链
- 凭据按 provider 隔离（`_key_for_provider`，不是全局 key）
- 三态熔断（closed/open/half-open）

---

## P7. 模型探活（实测数据）（1 页）

**关键发现**（本项目实测）：
- DeepSeek 官方端点**只有 2 个真实模型**（不是文档里写的 3 个）
- 阿里云聚合端点**列出 249 个模型**，实测**大多数未给本账号开通**
- SiliconFlow bge-reranker 在 >10 calls/min 时返回 429

**结论**：**端点目录 ≠ 账号可用**。必须做运行时探活，且注册表只登记实测可用模型。

---

## P8. 思考模式 bug（1 页）

**触发条件**：DeepSeek V4 Flash 默认开启"先思维链再正文"

**实测数据**：

| 配置 | 正文 | 思维链 | 首字延迟 |
|---|---|---|---|
| 关闭思考 + 256 token | 69 字 | 0 字 | 783ms |
| 默认思考 + 64 token | **0 字** | 145 字 | 无 |
| 默认思考 + 768 token | 58 字 | 211 字 | 988ms |

**根因**：max_tokens 预算被思维链吃掉，正文返回空字符串，接口 200 无异常

**修复**：
1. 默认 `LLM_THINKING_MODE=disabled`
2. max_tokens < 阈值强制关闭
3. 解析 `reasoning_content` 字段
4. 正文为空 → 显式重试（再发一次显式禁用）→ 仍为空则报错交降级链

---

## P9. RAG 引擎：召回 + 精排（2 页）

**第 1 页 — 两阶段设计**：
```
Query → [向量召回 (bge-m3)] ─┐
      → [BM25 召回 (jieba)] ─┴→ [score_norm / RRF 融合] → top 20
                                                            ↓
                                                       [bge-reranker-v2-m3]
                                                            ↓
                                                       top K (默认 5)
```

**第 2 页 — 双塔 vs Cross-Encoder**：
- 双塔（向量）：query 和文档**分开**编码，只算向量距离
- Cross-Encoder（精排）：把 (query, 文档) 拼起来过模型，能捕捉否定/条件/数字
- 权衡：精排准但慢，所以只用在召回后的少量候选上

---

## P10. 多 provider 精排降级链（1 页）

**实测触发**：SiliconFlow bge-reranker 触限

**降级路径**：
1. 主：SiliconFlow OpenAI 兼容协议 `POST /v1/rerank`
2. 备：Aliyun MaaS **DashScope 原生协议** `POST /api/v1/services/rerank/...`

**协议差异**：
- OpenAI：payload 在顶层 `query/documents`，URL `/rerank`
- DashScope：payload 在 `input.*`，URL `api/v1/services/rerank/text-rerank/text-rerank`

**客户端实现**：按 base_url 自动识别协议 + 拼路径

---

## P11. 检索质量评测数据（1 页）

| 方案 | R@1 | R@5 | MRR |
|---|---|---|---|
| vector | **97.2%** | 100% | 0.986 |
| bm25 | 88.9% | 97.2% | 0.922 |
| rrf | 94.4% | 100% | 0.972 |
| **score_norm+rerank** | **94.4%** | **100%** | **0.968** |

**关键结论**：
- 多学科场景下**纯向量反而最优**（语义区分能力强）
- 精排对小语料收益显著（opt2 v2 评测 R@1 提升 +11pp）
- 融合权重 vw=0.5/bw=0.5（不是直觉的 0.6/0.4）

---

## P12. 出题/追问质量评测（1 页）

**LLM-as-judge 评分**（满分 2.0）：

| 维度 | 出题 | 追问 |
|---|---|---|
| 主题/针对性 | 2.00 | 2.00 |
| 难度/深度 | 2.00 | 1.88 |
| 清晰/简洁 | 2.00 | 2.00 |
| **真实知识引用** | **1.47** | —— |
| 总评 | **1.90** | **1.97** |

**已知弱点 + 下一步**：groundedness 仅 1.47 ——
把检索 top-3 注入 ASK_PROMPT，让 LLM 基于真实术语出题

---

## P13. 端到端冒烟（1 页）

**两条路径全过**：

| 模式 | 检查点 | 通过 | 耗时 |
|---|---|---|---|
| 练习 | 9 | 9 | 65s |
| 模拟面试 | 7 | 7 | 7.5s |

**关键路径**：
- 练习：JD→简历→规划→出题→评分→追问→收尾→复习计划
- 模拟：3 题自动推进 → 收尾

**总成本 ¥0.16** / ¥30 预算

---

## P14. 企业级架构三支柱（1 页）

```
┌────────────────────────────────────────────┐
│ 多实例部署（gunicorn + uvicorn worker）   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ worker 1 │ │ worker 2 │ │ worker 3 │  │
│  └──────────┘ └──────────┘ └──────────┘  │
└────────────────────────────────────────────┘
      ↓                 ↓                ↓
┌────────────┐  ┌─────────────┐  ┌──────────┐
│ Redis      │  │ MySQL       │  │ 异步队列 │
│ · 限流 Lua │  │ pool=20+40  │  │ 8 worker │
│ · 短期记忆 │  │ asyncmy     │  │ 10 优先级│
└────────────┘  └─────────────┘  └──────────┘
```

**为什么够撑百人并发**：
- FastAPI 单进程异步 + 20 池 + 40 overflow ≈ 100 并发连接
- 多 worker 进程叠加 → 数百并发
- Redis 限流防止雪崩

---

## P15. 多租户 & 计费（1 页）

**决策**：取消 BYOK，平台托管 key + 积分扣费

```
User ──login──> MAOO ──JWT──> PlatformAdapter
                                    ↓
                              ResolvedUser (业务侧只看到这个)
                                    ↓
                              积分扣费 (402 if 不足)
                                    ↓
                              LLM Gateway
```

**积分系统要点**：
- 预扣 → 调用 → 结算（多退少补）
- 幂等键 `(request_id, kind)`
- 充值幂等 `order_id`
- 流水持久化（`spend_ledger.json`）

---

## P16. 可观测性（1 页）

**5 类指标**：
1. **业务**：活跃用户、答题数、积分消耗
2. **RAG**：检索延迟、召回率、融合模式命中
3. **LLM**：调用次数、token、花费、降级次数
4. **系统**：CPU、内存、连接池等待
5. **错误**：4xx/5xx 分布、熔断次数

**接口**：`GET /health/metrics`（JSON）+ `/health/metrics/prom`（Prometheus 格式）

---

## P17. SSE 流式响应（1 页）

**问题**：客户端断网/刷新 → 已发送的事件丢失

**方案**：
- 服务端环形缓冲（默认 256 帧）
- 每帧带 seq
- 客户端断连重连时带 `Last-Event-ID` → 服务端补发

```python
# 简化示意
class SSERingBuffer:
    def __init__(self, max_size=256):
        self._buf = deque(maxlen=max_size)
    def append(self, seq, event):
        self._buf.append((seq, event))
    def replay_since(self, last_seq):
        return [e for s, e in self._buf if s > last_seq]
```

---

## P18. 难度自适应 FSM（1 页）

**问题**：初版 FSM 只写状态，出题仍用预设难度

**修复**：把 FSM 的输出真正用起来

```
[答对且深入] → 上调难度 → [答错或浅] → 下调难度
     ↑                              ↓
     └────────[保持难度] ←───────────┘
```

```python
def effective_difficulty(state, plan_item):
    fsm_difficulty = state.get("current_difficulty")
    plan_difficulty = plan_item.get("difficulty")
    # FSM 决策 > 预设
    return fsm_difficulty or plan_difficulty
```

---

## P19. 数据库设计要点（1 页）

**4 个核心表**：
- `users`：业务子用户（maoo_user_id 外键）
- `documents`：知识库文档（含 is_seed / status / category）
- `vectors`：向量（chunk_id + BLOB，**大端** float32）
- `score_records`：评分记录（含 key_missing / 追问触发条件）

**关键约束**：
- chunk_id = `{doc_id}#{chunk_index}`（向量与 BM25 一致，否则 RRF 失效）
- 向量 BLOB 大端（兼容历史 `>Nd` struct.pack）
- `category` 索引（按学科过滤）

---

## P20. Redis 短期记忆（1 页）

**会话快照设计**：
```json
{
  "session_id": "...",
  "user_id": 123,
  "current_question_idx": 3,
  "qa_history": [...],
  "score_records": [...],
  "difficulty_state": "medium",
  "ts": 1694694400
}
```

**TTL 24h**，落 MySQL 之前 Redis 是唯一真相来源（性能 + 防脏写）。

---

## P21. 部署形态（1 页）

**docker-compose 一键起**：

```yaml
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ...
    healthcheck: ...
  redis:
    image: redis:7-alpine
  backend:
    build: ./backend
    depends_on:
      mysql: { condition: service_healthy }
      redis: { condition: service_started }
  frontend:
    build: ./frontend
```

`docker compose up` 即可，4 个服务互连 + 健康检查

---

## P22. 测试金字塔（1 页）

```
              ┌──────────────┐
              │ e2e 冒烟     │  M5  2 套（练习 + 模拟）
              ├──────────────┤
              │ 质量评测     │  M4 LLM-as-judge
              ├──────────────┤
              │ 检索评测     │  v2 / M3
              ├──────────────┤
              │ 集成测试     │  65+ 用例
              ├──────────────┤
              │ 单元测试     │  pytest
              └──────────────┘
```

**63 passed in 5:29** —— 每个 P0 修复都有回归测试

---

## P23. 性能数据（1 页）

**检索延迟**（bge-m3 1024 维）：
- 单条 embedding：210ms
- 批量 32 条：430ms（cache 命中 0ms）
- 向量检索（975 chunk）：2.6MB / 16.6ms 装载
- BM25 重建（675 chunk）：1.48s（线程池，不阻塞事件循环）

**LLM 调用**（DeepSeek V4 Flash）：
- TTFT：364ms（关闭思考）/ 1688ms（默认思考）
- 单次聊天：~600 tokens / 1-2s

**Redis Lua 限流**：< 1ms / 调用

---

## P24. 关键失败案例（1 页）

**3 个值得讲的失败**：

1. **Docker 反复掉线** → 进程脱离 shell 会话被杀
   - **教训**：服务型测试必须自包含（脚本内启动 → 测量 → 关闭）
   
2. **缓存 key 污染** → rerank 缓存 key 混入 `_provider_used`
   - **教训**：跨调用状态不能进缓存 key
   
3. **25500 个孤儿向量** → 上一版误写入真实库的合成向量
   - **教训**：合成测试数据必须用临时表，不能污染生产库

---

## P25. 迭代节奏与决策（1 页）

**v1（opt/v1）**：14 个 P0 缺陷 + 7 节深度优化（6 周）
**v2（M1-M5）**：5 轮主题迭代（2 天）

每轮交付：
1. 完整可演示成果
2. 本轮报告
3. 全局报告增量更新
4. 测试用例 + 文档同步更新

**原则**：规划先行 → 评测基建先行 → 迭代不破坏正确性

---

## P26. 商业化考量（1 页）

**充值接口**：已实现 mock + 幂等键，待接真实支付渠道

**成本模型**：
- LLM：¥0.001 / 千 token（DeepSeek Flash）
- Embedding：¥0.05 / 百万 token（bge-m3）
- 用户答题成本：~¥0.001 / 次（含 1 出题 + 1 评分）

**收入模型（建议）**：
- 注册送 10000 积分（够 ~1000 次答题）
- 充值包：10/30/100 元 ≈ 1万/3万/10万 积分
- 企业版：年费 + 私有部署

---

## P27. 个人成长（1 页）

**作为测试工程师做这个项目**：
- 测试思维帮我**先建评测基建**（质量护栏先行）
- 灰盒测试帮我**理解设计模式**（不只验证功能）
- 性能测试帮我**关注指标**（任何优化都有数据支撑）
- 自动化测试帮我**安全重构**（63 测试兜底）

**输出物**：
- 1 个可上线的项目
- 3 份完整文档（总结报告 + 名词解释 + PPT）
- 5 轮迭代的真实数据

---

## P28. Q&A 准备（1 页）

**可能被问到的问题**：

1. **RAG 为什么选 bge-m3 而不是 OpenAI embedding？**
   → 成本（本地/硅基流动 ~¥0.05 vs OpenAI ~¥7）+ 中文效果相当

2. **为什么不用 LangChain / LlamaIndex？**
   → 控制粒度 + 避免抽象税（10 个 Agent 编排框架的隐性复杂度）

3. **DeepSeek V4 Pro 与 Flash 怎么选？**
   → 报告 / 评估走 Pro，常规出题 / 评分走 Flash

4. **怎么防止 prompt 注入？**
   → 输入侧 user_input 长度限制 + 关键词过滤；输出侧 JSON schema 校验

5. **MAOO 平台怎么对接？**
   → PlatformAdapter 协议，业务侧零感知

---

## P29. 项目截图/演示（1 页）

**4 张截图**（不上代码细节）：
1. 主页 / 上传知识库 / 个人中心
2. 练习模式 / 模拟面试界面
3. 评分详情 / 追问触发
4. 错题本 / 复习计划

---

## P30. 总结（1 页）

**1 句话总结**：
> 这是一个**面向生产的企业级 AI 应用**——从单点 LLM 调用演进到 8 Agent 编排 + 多 provider 网关 + 完整监控，所有优化都有可复现的评测数据。

**3 个核心数字**：
- 63 测试 / 5:29 全绿
- R@1=97.2%（多学科检索）
- ¥0.16 跑通完整 e2e

**1 个值得记忆的经验**：
> **没有评测的优化都是赌博** —— 先建评测基建，再优化

---

## 附录（讲完正片后翻阅）

### A. 性能调优检查清单
- [ ] 关闭 LLM 思考模式
- [ ] Reuse client + 连接池
- [ ] RAG 融合权重按数据调
- [ ] BM25 异步重建（不阻塞事件循环）
- [ ] 精排限制候选数（默认 20）
- [ ] 缓存 key 用主 model 而非 _provider_used

### B. 故障排查 Runbook
- 流式响应空白 → 检查 LLM 思考模式
- 401 降级失败 → 检查 provider 凭据隔离
- SSE 丢失事件 → 检查环形缓冲容量
- BM25 索引慢 → 检查数据库版本号

### C. 部署清单
- [ ] docker-compose up
- [ ] 注入 LLM Key
- [ ] 创建 admin 账号
- [ ] 上传种子知识库
- [ ] 配置域名 + HTTPS
- [ ] 设置监控告警
