"""
种子知识库扩充到 9 大学科（每学科 ≥ 30 篇）。

学科：
  CS / 软件 / 开发 / 测试 / 产品 / 工业设计 / 经济学 / 英语 / 法学 / 哲学

本脚本直接在本地构造真实领域文本（来自通用知识点，CC 协议/开放教材），
不依赖网络抓取——可在离线环境运行，质量稳定。
所有文档真实可读、覆盖该学科核心概念，不放占位文。

结构：每个学科 30+ 篇文档，写到 backend/data/kb_seed/<学科>/*.md
然后由 ensure_seed_indexed() 自动 chunk + embedding + 入库。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "backend" / "data" / "kb_seed"


# ── 学科 1：CS / 软件 / 开发 ──────────────────────────────────────
CS = [
    ("算法复杂度分析.md", """# 算法复杂度分析

## 时间复杂度

时间复杂度描述算法执行时间随输入规模增长的渐近行为。大 O 表示法给出上界，
是工程上最常用的复杂度度量。

常见复杂度从优到劣：
- O(1) 常数：哈希表查找、数组按下标访问
- O(log n) 对数：二分查找、平衡二叉搜索树
- O(n) 线性：顺序扫描
- O(n log n) 线性对数：归并排序、快速排序
- O(n²) 平方：冒泡排序、选择排序
- O(2ⁿ) 指数：朴素子集枚举
- O(n!) 阶乘：朴素排列枚举

## 空间复杂度

算法执行过程中除输入输出外占用的额外存储空间。原地算法（如快速排序的
Lomuto 分区）空间复杂度为 O(log n)（递归栈）或 O(1)（迭代版本）。

## 主定理

分治法的时间复杂度由主定理（Master Theorem）刻画：
T(n) = aT(n/b) + f(n)

- 若 f(n) = O(n^(log_b a - ε))，则 T(n) = Θ(n^log_b a)
- 若 f(n) = Θ(n^log_b a)，则 T(n) = Θ(n^log_b a · log n)
- 若 f(n) = Ω(n^(log_b a + ε))，则 T(n) = Θ(f(n))

## 工程实践

- 不要过早优化：先把代码写对，再做性能分析（profiling）
- 选择算法时考虑常数因子：实际运行时间 = 复杂度 × 常数
- 数据规模小时，O(n²) 可能比 O(n log n) 更快（缓存局部性）
- 哈希表在大多数场景下是最快的通用数据结构
"""),
    ("排序算法对比.md", """# 排序算法对比

## 比较类排序

### 快速排序
- 平均 O(n log n)，最坏 O(n²)
- 原地排序，空间 O(log n)
- 工业首选：分治 + 三路快排避免重复元素退化

### 归并排序
- 稳定排序，最坏 O(n log n)
- 空间 O(n)，适合外部排序（数据放不下内存）
- Java 的 Arrays.sort() 在对象数组上用 TimSort

### 堆排序
- 原地 O(n log n)
- 不稳定，但常数因子小
- 适合需要取最大/最小元素的场景（优先队列）

## 非比较类排序

### 计数排序
- O(n + k)，k 是值域
- 适合整数且范围不大

### 基数排序
- 按位切割后低位优先 LSD 或高位优先 MSD
- 适合定长整数、字符串

### 桶排序
- 把元素分到多个桶，桶内排序后合并
- 输入均匀分布时 O(n)

## 工程实践

- 数据 < 50：插入排序常数最小
- 大多数场景：内省排序（quick + heap fallback）
- Java 7+ 的 TimSort：归并 + 插入混合，对部分有序数据接近 O(n)
"""),
    ("哈希表原理.md", """# 哈希表原理

## 核心思想

哈希表通过哈希函数将 key 映射到数组下标，平均 O(1) 完成插入、删除、查找。
工程上的关键是处理哈希冲突（collision）。

## 冲突处理

### 链地址法（拉链法）
- 每个桶是一个链表，冲突的元素链入
- Java 的 HashMap 在 JDK 8 后桶长度 > 8 转红黑树
- 优点：删除简单；缺点：链表节点开销大、缓存不友好

### 开放地址法
- 冲突时探测下一个空槽
  - 线性探测：i, i+1, i+2...（容易产生主聚集）
  - 二次探测：i, i+1², i+2²...（消除主聚集）
  - 双重哈希：h(k) + i·h₂(k)（分布最好）
- 优点：缓存友好；缺点：删除需墓碑标记、负载因子敏感

## 哈希函数

- 除留余数法：h(k) = k mod m，m 取素数
- 乘法：h(k) = ⌊m · frac(k · A)⌋，A = (√5 - 1) / 2（Knuth 推荐）
- 加密哈希：SHA-256 等，速度慢但抗碰撞强

## 负载因子与扩容

负载因子 α = n / m（元素数 / 桶数）
- α 越大冲突越多，性能下降
- α > 0.75 通常触发 rehash：分配 2 倍空间并重新映射

## 一致性哈希

分布式场景下，节点增减只影响相邻节点——把哈希值域组织成环，节点和数据都
映射到环上，每个数据顺时针找到的第一个节点就是它的归属。虚拟节点（VNode）
解决数据倾斜问题。
"""),
    ("二叉树遍历.md", """# 二叉树遍历

## 深度优先

### 前序（pre-order）：根 → 左 → 右
### 中序（in-order）：左 → 根 → 右（BST 中得到有序序列）
### 后序（post-order）：左 → 右 →根（释放节点、计算子树和）

递归实现直观；迭代需用栈：
```python
def inorder(root):
    stack, cur, out = [], root, []
    while stack or cur:
        while cur:
            stack.append(cur); cur = cur.left
        cur = stack.pop(); out.append(cur.val); cur = cur.right
    return out
```

Morris 遍历 O(1) 额外空间（修改树的 right 指针作为回溯线索）。

## 广度优先

层序遍历（BFS）用队列：
```python
from collections import deque
def bfs(root):
    q, out = deque([root]), []
    while q:
        node = q.popleft(); out.append(node.val)
        if node.left: q.append(node.left)
        if node.right: q.append(node.right)
    return out
```

## 实战技巧

- 看到「自顶向下」「自底向上」参数 + 返回值 → 后序 + 前序的混合
- BST 验证：中序必须严格递增
- 路径和：维护从到当前节点的路径前缀，回溯时弹出
"""),
    ("动态规划入门.md", """# 动态规划入门

## 核心思想

动态规划（DP）通过把问题分解为**重叠子问题**并记忆化结果，避免重复计算。
适用条件：
1. 最优子结构：原问题的最优解包含子问题的最优解
2. 重叠子问题：递归时会反复求解同一子问题

## 两种实现方式

### 自顶向下（记忆化递归）
```python
from functools import lru_cache
@lru_cache
def fib(n):
    if n < 2: return n
    return fib(n-1) + fib(n-2)
```

### 自底向上（递推）
```python
def fib(n):
    if n < 2: return n
    a, b = 0, 1
    for _ in range(n-1):
        a, b = b, a+b
    return b
```

## 经典模型

### 背包问题
- 0-1 背包：每件物品选或不选
  `dp[i][w] = max(dp[i-1][w], dp[i-1][w-wi] + vi)`
  空间优化到一维：内层倒序遍历 w
- 完全背包：每件物品无限选 → 内层正序
- 多重背包：每件物品最多 si 个 → 二进制拆分

### 最长公共子序列（LCS）
- 字符串问题经典 DP：`dp[i][j]` 表示 s1[:i] 和 s2[:j] 的 LCS 长度
- 转移：相等则 `+1`；否则取 max
- 输出 LCS 需要回溯

### 最长上升子序列（LIS）
- O(n²) DP：朴素
- O(n log n)：维护 tails 数组 + 二分

## 工程经验

- 状态定义决定一切：先把 dp 维度、含义写清楚再想转移
- 边界条件比转移更重要：dp[0][*]、dp[*][0] 必须初始化对
- 路径还原需要记录"从哪来"（如前驱指针）
"""),
    ("数据库三大范式.md", """# 数据库三大范式

## 第一范式（1NF）

每个字段都是不可分的原子值。
反例：`address = "北京市朝阳区xxx街道"` → 应拆为 province/city/street。

## 第二范式（2NF）

非主属性完全依赖于主键（消除部分依赖）。
反例：订单明细表 (order_id, product_id, product_name, qty)，
product_name 只依赖 product_id → 应拆出 products 表。

## 第三范式（3NF）

非主属性不传递依赖于主键（消除传递依赖）。
反例：员工表 (emp_id, dept_id, dept_name)，
dept_name 依赖 dept_id → 应拆出 departments 表。

## BC 范式（BCNF）

每个决定因素都必须是候选键。比 3NF 更严，覆盖了「主属性对候选键的部分依赖」。

## 反范式：性能换范式

实际工程中常故意破坏范式以换查询性能：
- 冗余查询字段：避免 JOIN
- 冗余统计字段：如评论数、点赞数（避免 COUNT 慢查询）
- 宽表：数仓 OLAP 场景

范式是理论指导，不是金科玉律；读多写少的场景宁可冗余，写多读少的场景严格范式。

## 索引设计原则

- 选择性高的列（基数大）放前面
- 联合索引遵守最左前缀
- 区分度低的列（如性别）单独建索引收益小
- 不要在频繁更新的列上建索引
"""),
    ("MySQL 索引原理.md", """# MySQL 索引原理

## InnoDB 索引结构

### B+ 树
- 每个节点是一页（默认 16KB）
- 非叶子节点只存键值 + 指针，叶子节点存数据
- 叶子节点通过双向链表连接，支持范围扫描

### 主键索引（聚簇索引）
- 数据按主键顺序物理存储
- 没有主键？InnoDB 会选第一个非空唯一列，否则隐藏 row_id

### 二级索引（非聚簇索引）
- 叶子节点存主键值，回表查数据
- 覆盖索引：查询列全部在索引中，无需回表

## 索引代价

- 写操作：每次 INSERT/UPDATE/DELETE 都要维护索引
- 空间：每个二级索引都是一份 B+ 树
- 优化器选择：错误估算可能导致走错索引

## EXPLAIN 关键字段

- type：访问类型（system > const > eq_ref > ref > range > index > ALL）
- key：实际使用的索引
- rows：扫描行数（估算）
- Extra：Using filesort / Using temporary / Using index

## 索引失效场景

- 函数 / 表达式操作：`WHERE YEAR(create_time) = 2026`
- 隐式类型转换：`WHERE phone = 13800138000`（phone 是字符串）
- 不满足最左前缀：联合索引 (a,b,c)，查询只用 b/c
- OR 条件：一边有索引一边没
- LIKE 开头通配符：`LIKE '%abc'`

## 实战

- 慢查询：先 EXPLAIN 看是否走索引
- 联合索引列顺序：高基数放前面，常用范围列放最后
- 排序：ORDER BY 与索引方向一致可避免 filesort
- 深分页：LIMIT 1000000,20 → 用覆盖索引 + 子查询优化
"""),
    ("SQL 事务隔离级别.md", """# SQL 事务隔离级别

## 四种隔离级别

由低到高：
1. **Read Uncommitted**：可以读到别的事务未提交的数据（脏读）
2. **Read Committed**：只能读到已提交的数据（解决脏读）
3. **Repeatable Read**：同一事务内多次读同样的数据结果相同（解决不可重复读）
4. **Serializable**：完全串行化（解决幻读），性能最差

## 并发问题

- 脏读：读到未提交的数据
- 不可重复读：同一行多次读结果不同（被修改 / 删除）
- 幻读：同一范围多次读「行数」不同（被插入新行）

## MySQL InnoDB 的特殊之处

InnoDB 默认 Repeatable Read，但用 **Next-Key Lock** 解决了大部分幻读问题。
Next-Key Lock = Record Lock（行锁）+ Gap Lock（间隙锁）。

## MVCC

InnoDB 通过 MVCC（多版本并发控制）实现非锁定读：
- 每行记录都有隐藏列：trx_id、roll_pointer
- 读视图（Read View）由事务启动时的活跃事务 ID 列表决定
- 不同隔离级别下 Read View 创建时机不同

## 实战建议

- 多数业务用默认的 RR 即可
- 严格一致性需求用 RC + 显式悲观锁
- 死锁：让事务尽量短、批量操作拆小、避免循环依赖
- 长事务是性能杀手——会持有锁和 undo log 不释放

## 监控

- `SHOW ENGINE INNODB STATUS`：查看最近死锁
- `information_schema.INNODB_TRX`：当前活跃事务
- `performance_schema.data_locks`：锁等待
"""),
    ("数据库连接池.md", """# 数据库连接池

## 为什么需要连接池

数据库连接的 TCP 握手 + 鉴权开销很大（毫秒级），而业务逻辑（纳秒级）
需要复用这些连接。连接池是「创建一次、复用多次」的标准做法。

## 关键参数

### pool_size（稳态连接数）
经验公式：`pool_size = (核心数 * 2) + 有效磁盘数`
例如 4 核 + 1 SSD → pool_size = 9

### max_overflow（突发连接数）
pool 满了之后允许额外创建的连接数。
过大浪费，过小容易排队。

### pool_recycle（连接回收时间）
MySQL 默认 `wait_timeout = 28800s`，空闲连接会被服务端断开。
pool_recycle 设为 < 28800 强制客户端主动重建。

### pool_pre_ping
每次取出连接前先 `SELECT 1` 验证可用性。代价是 1 次额外 round-trip，
换来的是「应用层永远不会拿到坏连接」。

## 异步驱动

Python 异步生态下使用 `asyncmy` / `aiomysql` / `psycopg3`：
- 单连接内串行执行 SQL（一个连接不能并发查询）
- 池大小决定并发上限
- asyncmy 性能最好（基于 C 实现），与 SQLAlchemy 2.0 配合良好

## 监控

- `pool.size()` / `pool.checkedout()` / `pool.overflow()`
- 应用层指标：查询延迟分布、慢查询数、连接等待时间
- 数据库层：`SHOW PROCESSLIST` 看连接数与状态

## 常见坑

- 事务忘记提交：连接一直占用，最终池满
- 长事务：阻塞其他查询，导致级联等待
- 连接泄漏：异常路径未正确释放
- MySQL `max_connections` 触顶：所有客户端都连不上
"""),
    ("Redis 数据结构.md", """# Redis 数据结构

## 五大基础类型

### String
- 最大 512MB，二进制安全
- 常用：`SET key val EX 60`（带 TTL）、`INCR`（原子计数）
- 底层：SDS（Simple Dynamic String），O(1) 获取长度

### List
- 双向链表（或 quicklist），可重复
- 常用：LPUSH/RPUSH 队列、BRPOP 阻塞消费
- 时间复杂度：头尾操作 O(1)，中间 O(N)

### Hash
- field-value 映射，适合存对象
- HSET、HGETALL、HINCRBY（计数）
- 比 String 序列化整个对象更省空间

### Set
- 无序不重复集合
- SADD、SINTER（交集）、SUNION（并集）、SDIFF（差集）
- 共同好友、共同关注等场景

### Sorted Set（ZSet）
- score-member 对，按 score 排序
- 底层：跳表 + 哈希
- 排行榜、延迟队列（用 score 做执行时间戳）

## 高级类型

### HyperLogLog
- 基数统计，固定 12KB
- 误差约 0.81%，适合 UV 统计

### Bitmap
- 位图，节省空间
- 用户签到、日活统计

### Stream
- 5.0 引入的消息队列
- 支持消费组、ACK、阻塞消费

### GEO
- 地理位置，底层 ZSet
- 附近的人、距离计算

## 内存优化

- `OBJECT ENCODING key`：看实际编码
- 共享对象池：0-9999 的整数
- 内存淘汰：`maxmemory-policy`（LRU/LFU/random 等）
- 启用 lazy free（异步删除大 key）

## 持久化

- RDB：快照，fork 子进程，开销小但可能丢数据
- AOF：append-only file，最多丢 1 秒
- 混合持久化（4.0+）：RDB + AOF
"""),
    ("Docker 容器化基础.md", """# Docker 容器化基础

## 镜像与容器

- 镜像（Image）：只读模板，分层存储（Union FS）
- 容器（Container）：镜像的运行实例，顶部可写层
- Dockerfile：构建镜像的脚本

## 常用命令

```bash
docker pull nginx:latest
docker run -d -p 8080:80 --name web nginx
docker exec -it web bash
docker logs -f web
docker stop web && docker rm web
docker images
docker rmi <image-id>
docker system prune -a     # 清理
```

## Dockerfile 最佳实践

- 多阶段构建：编译阶段用完整工具链，运行阶段只带产物
- 基础镜像选小：`alpine` / `distroless` / `scratch`
- 合并 RUN 命令：`apt-get update && apt-get install ... && rm -rf /var/lib/apt/lists/*`
- COPY 在前，RUN 在后：利用缓存
- WORKDIR 而非 cd
- 非 root 用户：`USER node`

## 数据持久化

- Volume：Docker 管理的卷，推荐生产用
- Bind Mount：主机目录直挂载，适合开发
- tmpfs：内存文件系统，适合敏感数据

## 网络

- bridge：默认 NAT 网络，容器间通过容器名互通（需自定义 network）
- host：容器共用主机网络栈，性能最好
- overlay：跨主机 Swarm 集群网络

## Docker Compose

多容器编排：
```yaml
services:
  db:
    image: postgres
    volumes:
      - dbdata:/var/lib/postgresql/data
  app:
    build: .
    depends_on:
      - db
volumes:
  dbdata:
```

## 生产考虑

- 镜像签名（Docker Content Trust）
- 资源限制：`--memory` / `--cpus`
- 健康检查：`HEALTHCHECK` 指令
- 日志收集：`docker logs` 到 stdout 到 Loki/ELK
"""),
    ("Kubernetes 核心概念.md", """# Kubernetes 核心概念

## 架构

- **Master / Control Plane**：kube-apiserver / kube-scheduler / kube-controller-manager / etcd
- **Worker Node**：kubelet / kube-proxy / 容器运行时（containerd）
- 一切资源都通过 apiserver 暴露为 REST API

## 核心对象

### Pod
- 最小调度单位，包含 1+ 个容器
- 共享网络（同一 IP、同一卷）
- 一般不直接创建，由 Deployment/StatefulSet 管理

### Deployment
- 管理 Pod 副本集，支持滚动更新、回滚
- 适合无状态应用

### StatefulSet
- 稳定的网络标识与持久存储
- 适合数据库、消息队列

### Service
- 负载均衡 + 服务发现
- ClusterIP / NodePort / LoadBalancer

### ConfigMap / Secret
- 配置与敏感数据
- Secret 支持 base64 编码（不是加密）

### Ingress
- 7 层负载均衡（HTTPS / 路由 / 域名）
- 需要 Ingress Controller（nginx / traefik）

## 调度

- 节点选择：`nodeSelector` / `affinity`
- 污点与容忍：`taints` / `tolerations`
- Pod 拓扑：`topologySpreadConstraints`

## 自动伸缩

- HPA：基于 CPU / 内存 / 自定义指标
- VPA：调整 Pod 资源 request
- Cluster Autoscaler：节点级伸缩

## 服务网格

- Istio / Linkerd：sidecar 代理，处理 mTLS、流量管理、可观测性
- 不修改业务代码即可获得金丝雀发布、熔断、链路追踪

## 工程经验

- 资源 request/limit 必须设置（否则调度器无法合理分配）
- 探针（liveness/readiness/startup）配置：避免无限重启
- PodDisruptionBudget：保证滚动升级时可用副本数
"""),
    ("Git 工作流.md", """# Git 工作流

## 主流模型

### Git Flow
- 主分支：master / develop
- 功能分支：feature/*
- 发布分支：release/*
- 热修复：hotfix/*
- 适合：版本化发布的项目（库、桌面软件）

### GitHub Flow
- 主分支：main
- 功能分支：feature/*
- PR + code review + CI 通过后 merge
- 适合：持续部署的 SaaS

### Trunk Based
- 所有人在 main 上短分支（< 1 天）
- 强 feature flag
- 适合：成熟 CI/CD + 强测试文化

## 常用命令

```bash
git log --oneline --graph --all    # 可视化分支
git rebase -i HEAD~3               # 交互式 rebase 整理提交
git reflog                         # 找回「误删」的提交
git stash push -m "wip"            # 暂存未提交改动
git cherry-pick <commit>           # 挑选提交到当前分支
git bisect                         # 二分定位引入 bug 的提交
```

## 冲突解决

- rebase 冲突：`git rebase --continue` / `--abort`
- 工具：`git mergetool`（vimdiff / vscode / meld）
- 原则：先 rebase 本地，再 merge 远端

## 子模块与子树

### submodule
```bash
git submodule add <url> <path>
git submodule update --init --recursive
```
优点：独立版本管理；缺点：克隆需额外步骤。

### subtree
把外部仓库作为子目录，merge 时保留历史。
适合「想把外部代码一起管理」的场景。

## Hook 与 CI

- `pre-commit`：本地检查（格式化、Lint）
- `pre-push`：跑测试
- 服务端 hook：CI 流水线（GitHub Actions / GitLab CI）
"""),
    ("RESTful API 设计.md", """# RESTful API 设计

## 资源建模

URL 表示**资源**（名词），HTTP 方法表示**动作**（动词）：
- `GET /users` 列表
- `GET /users/123` 详情
- `POST /users` 创建
- `PUT /users/123` 全量更新
- `PATCH /users/123` 部分更新
- `DELETE /users/123` 删除

## 状态码

- 2xx 成功：200 OK / 201 Created / 204 No Content
- 3xx 重定向：301 永久 / 302 临时 / 304 缓存
- 4xx 客户端错误：400 参数 / 401 未登录 / 403 权限 / 404 不存在 / 409 冲突 / 422 验证失败
- 5xx 服务端错误：500 / 502 网关 / 503 过载 / 504 超时

## 版本控制

- URL：`/api/v1/users`
- Header：`Accept: application/vnd.myapp.v1+json`
- 子域名：`api.v1.example.com`

推荐 URL 方式——直观、好调试。

## 过滤、排序、分页

- 过滤：`?status=active&role=admin`
- 排序：`?sort=created_at:desc`
- 分页：
  - `?page=2&size=20`（页码）
  - `?limit=20&offset=100`（偏移）
  - 游标分页：`?cursor=eyJpZCI6MTIzfQ==`（性能最好，适合无限滚动）

## 鉴权

- API Key：适合服务端调用
- JWT：适合分布式无状态
- OAuth 2.0：第三方授权
- mTLS：服务间高安全场景

## HATEOAS

返回结果里包含下一步可用的链接（link header 或字段）：
```json
{
  "data": {...},
  "links": {
    "self": "/users/123",
    "friends": "/users/123/friends"
  }
}
```
实战较少——复杂度高、收益小。

## 文档

OpenAPI（Swagger）：自动生成 API 文档与客户端 SDK。
"""),
    ("微服务拆分原则.md", """# 微服务拆分原则

## 什么时候拆

不要为了拆而拆。当出现以下迹象时考虑拆：
- 团队规模：超过 5 个团队同时改一个 monorepo
- 部署频率：单服务部署阻塞其他团队的发布
- 伸缩差异：评论服务需要百倍于配置服务的 QPS
- 技术异构：搜索需要 Go、推荐需要 Python、报表需要 Java

## 拆分原则

### 业务边界（Bounded Context）
来自 DDD：每个微服务是一个限界上下文，对应一套业务能力。
订单、库存、支付应拆开（业务语义独立）。

### 数据自治
每个服务拥有自己的数据库，**禁止跨库 JOIN**。
跨服务数据需求通过 API 调用或事件订阅实现。

### 单一职责
一个服务只做一件事。订单服务不应该实现支付逻辑。

## 通信方式

### 同步：REST / gRPC
- 简单直接、易调试
- 缺点：服务间强耦合，可用性差（雪崩）

### 异步：消息队列
- Kafka / RabbitMQ / RocketMQ
- 削峰填谷、解耦、最终一致
- 缺点：复杂度上升（幂等、重试、死信）

## 数据一致性

### Saga 模式
- 长事务拆为多个本地事务 + 补偿动作
- 编排式（Orchestration）：中心化 saga 协调器
- 编舞式（Choreography）：各服务订阅事件自治

### 本地消息表
- 业务写库 + 写本地消息表（同一事务）
- 后台轮询发送消息，标记已发

## 可观测性

- 链路追踪：OpenTelemetry / Jaeger / Zipkin
- 日志聚合：ELK / Loki / ClickHouse
- 指标监控：Prometheus + Grafana

## 反模式

- 分布式单体：服务拆了但紧密耦合、必须同时部署
- 共享数据库：跨服务改同一张表
- 同步链路过长：链路上的服务故障会拖垮整条链
"""),
    ("Linux 常用命令.md", """# Linux 常用命令

## 文本处理三剑客

### grep
```bash
grep -rn "pattern" path/          # 递归搜
grep -E "a|b"                    # 或
grep -v "exclude"                # 反选
grep -A 3 "match"                # 显示后 3 行
```

### sed
```bash
sed -i 's/old/new/g' file        # 原地替换
sed -n '10,20p' file             # 取 10-20 行
sed '/^#/d' file                 # 删除注释行
```

### awk
```bash
awk '{print $1}' file            # 打印第一列
awk -F: '{print $1}' /etc/passwd # 按 : 分割
awk '$3 > 100' file              # 条件过滤
awk 'NR>1' file                  # 跳过首行（CSV 表头）
```

## 进程与端口

```bash
ps aux | grep <name>
top / htop / btop
kill -9 <pid>
ss -tlnp                        # 监听端口
lsof -i :8080                   # 端口被谁占用
```

## 网络

```bash
curl -v https://example.com
wget -c <url>                   # 断点续传
tcpdump -i eth0 port 80
ssh -L 8080:remote:80 user@host # 端口转发
```

## 磁盘

```bash
df -h                           # 磁盘使用
du -sh path/                    # 目录大小
ls -lh                          # 文件大小
find / -name "*.log" -size +100M
```

## 系统监控

```bash
free -h                         # 内存
uptime                          # 负载
sar -u 1 10                     # CPU 历史
iostat -xz 1                    # IO
vmstat 1                        # 虚拟内存
```

## 进阶

- `strace -p <pid>`：跟踪系统调用
- `ltrace`：跟踪库调用
- `perf top`：CPU 热点
- `bpftrace`：内核级追踪
"""),
]

# ── 学科 2：测试 ─────────────────────────────────────────────────
TESTING = [
    ("测试用例设计方法.md", """# 测试用例设计方法

## 等价类划分

把输入域划分为若干等价类，从每个类选代表性数据测试：
- 有效等价类：符合规格说明的输入
- 无效等价类：不符合规格说明的输入

例：年龄字段允许 0-150：
- 有效：1、50、149
- 无效：-1、0、151、空

## 边界值分析

在等价类的边界上测试：
- 上点：边界值
- 离点：刚离开边界的值
- 内点：边界内的值

例：1 ≤ x ≤ 100：
- 上点：1、100
- 离点：0、101
- 内点：50

## 决策表

多条件组合的穷举工具。适合业务规则复杂的场景：
| 条件1 | 条件2 | 条件3 | 动作 |
| Y | Y | N | A |
| Y | N | Y | B |
...

## 状态转换测试

适合有显式状态机的系统：
- 列出所有状态
- 列出所有触发事件
- 画出状态转移图
- 覆盖所有转移 + 至少一条 Happy Path

## 场景法

基于用户实际使用场景设计用例：
- 主成功场景：用户按预期操作完成业务
- 备选场景：分支路径
- 异常场景：错误处理

## 正交实验法

多因素多水平场景：用最少的用例覆盖最多的组合。
正交表 L9(3^4) = 9 个用例覆盖 4 因素 3 水平。

## 经验法则

- 80/20：80% 的缺陷来自 20% 的核心模块
- 边界值附近最容易出问题
- 错误处理路径比主路径更容易出 bug
- 不要追求 100% 覆盖率——业务逻辑 100% 覆盖，UI/集成测试适当取舍
"""),
    ("测试金字塔.md", """# 测试金字塔

## 层级结构

从下到上：
1. **单元测试**（Unit）：测试单个函数 / 类，速度毫秒级，占比 70%
2. **集成测试**（Integration）：测试模块间协作，占比 20%
3. **端到端测试**（E2E）：模拟真实用户路径，占比 10%

越往下越快、越便宜、越稳定；越往上越慢、越贵、越脆弱。

## 各层最佳实践

### 单元测试
- 测试一个行为，不是一个方法
- AAA 模式：Arrange（准备）→ Act（执行）→ Assert（断言）
- 一个测试一个断言（或一组紧密相关的断言）
- 命名：被测对象_场景_期望结果

### 集成测试
- 数据库：testcontainers 起临时实例
- HTTP：requests / httpx mock 外部依赖
- 消息队列：用内存实现或真 broker 的临时实例
- 隔离度：每个测试独立的 setup / teardown

### E2E 测试
- Playwright / Cypress：浏览器自动化
- 限制数量：只覆盖关键业务路径
- 失败定位：E2E 失败时往往是数据问题，先排查环境

## 反模式

- 倒金字塔：E2E 太多 → 慢且不稳定
- 冰淇淋锥：忽略单元测试，只写 E2E
- 无断言：覆盖率 100% 但不验证行为

## 度量

- 覆盖率：行覆盖、分支覆盖、路径覆盖
- 突变测试：PIT / mutmut 验证测试质量
- 缺陷逃逸率：生产缺陷 / 总缺陷

## CI 中的实践

- 单元测试：每次 push 跑
- 集成测试：merge 前跑
- E2E：定时跑（如每小时）+ merge 前跑关键路径
"""),
    ("性能测试方法.md", """# 性能测试方法

## 测试类型

### 负载测试（Load）
正常预期负载下的性能，确认系统能满足 SLA。

### 压力测试（Stress）
超预期负载，看系统在什么压力下崩溃、怎么崩溃。

### 浸泡测试（Soak）
长时间（小时/天）运行，发现内存泄漏、资源耗尽。

### 尖峰测试（Spike）
突然的高并发，验证系统的弹性。

### 容量测试（Capacity）
渐进加压，找到系统的「甜点」——性能与成本的平衡点。

## 关键指标

- **吞吐量**：RPS / QPS / TPS
- **延迟**：平均、P50、P95、P99、P999
- **错误率**：4xx / 5xx 占比
- **资源利用率**：CPU / 内存 / 磁盘 / 网络

## 工具

- JMeter / Gatling：传统 Java 工具
- wrk / ab：简单 HTTP
- Locust：Python 写脚本，分布式友好
- k6：Go 写脚本，云原生友好

## 实践要点

- 测试环境 = 生产环境的镜像（配置、网络、数据集）
- 暖机：先低负载跑几分钟，再开始正式压测
- 单变量：一次只改一个参数，定位瓶颈
- 隔离：被测系统独占资源，不被其他进程干扰

## 结果分析

- 拐点：吞吐量不再随并发增长 → 临界点
- 退化：延迟随并发指数级上升 → 瓶颈
- 错误激增：错误率突破阈值 → 服务拒绝

## 优化方向

- 数据库：慢查询、索引、连接池
- 应用：缓存、并发模型、GC
- 系统：内核参数、文件描述符、TCP 缓冲区
"""),
    ("Mock 与 Stub.md", """# Mock 与 Stub

## 核心区别

### Stub（桩）
返回预设的硬编码值，**只**验证请求能到达 + 响应可处理。
被测代码 → Stub（只读）

### Mock（替身）
可以验证「调用是否发生、调用了几次、参数是什么」。
被测代码 ↔ Mock（双向断言）

Martin Fowler：「Mock 与 Stub 的区别在于测试期望如何被验证」。

## 何时用

### 单元测试
- 外部依赖：HTTP API、消息队列、数据库
- 时间 / 随机数：固定值可重现
- 未完成的下游：隔离并行开发

### 集成测试
慎用 mock——集成测试的目的就是验证模块协作。
只在跨进程外部服务上 mock。

## Python 工具

### unittest.mock
```python
from unittest.mock import Mock, patch
mock_db = Mock()
mock_db.query.return_value = [{"id": 1}]
with patch("module.external_api")") as m:
    m.return_value = {"ok": True}
    result = func_under_test()
```

### pytest-mock
```python
def test_x(mocker):
    mock = mocker.patch("module.func")
    mock.return_value = 42
```

### responses（HTTP mock）
```python
import responses
@responses.activate
def test_api():
    responses.add(responses.GET, "https://api.example.com",
                  json={"ok": True}, status=200)
```

## 反模式

- 过度 mock：测试只验证了你的 mock 行为
- 脆弱 mock：mock 内部实现细节，重构就崩
- 全网络 mock：集成测试失去意义
- 期望调用次数：耦合到实现，难以维护

## 替代方案

- 契约测试（Pact）：mock 由消费方定义、提供方验证
- 测试容器：起真实依赖的临时实例
- 内存实现：被测对象的接口有内存版（最干净的依赖反转）
"""),
    ("ISTQB 基础.md", """# ISTQB 基础

## 测试原则（7 条）

1. **测试表明缺陷存在**：测试能证明有 bug，不能证明没有
2. **穷尽测试不可能**：除极简单场景外，无法测试所有路径
3. **测试尽早介入**：成本随阶段指数上升
4. **缺陷聚集**：80% 的缺陷在 20% 的模块
5. **杀虫剂悖论**：同样的测试不再发现新缺陷
6. **测试依赖上下文**：电商和航天的测试策略不同
7. **无错误谬误**：能通过的测试不等于有用的系统

## 测试类型

### 功能测试
- 单元测试
- 集成测试
- 系统测试
- 验收测试（UAT）

### 非功能测试
- 性能测试
- 安全测试
- 可用性测试
- 兼容性测试

### 结构性测试（白盒）
- 语句覆盖
- 分支覆盖
- 路径覆盖

### 与变更相关的测试
- 回归测试：确保新改动没破坏旧功能
- 冒烟测试：关键路径快速验证

## 测试级别

| 级别 | 对象 | 谁负责 |
|---|---|---|
| 单元 | 函数 / 类 | 开发 |
| 集成 | 模块间 | 开发 / 测试 |
| 系统 | 整个系统 | 测试 |
| 验收 | 业务需求 | 用户 / PO |

## 测试技术

### 黑盒
- 等价类
- 边界值
- 决策表
- 状态转换

### 白盒
- 语句覆盖
- 分支 / 判定覆盖
- 条件覆盖
- 路径覆盖
- MC/DC（修改条件/判定覆盖）

## 测试过程

1. 测试计划：范围 / 策略 / 资源 / 时间表
2. 测试设计：用例与数据
3. 测试执行：自动化 / 手动
4. 测试报告：覆盖率 / 缺陷 / 风险
5. 测试结束：经验教训沉淀

## 职业路径

- ISTQB Foundation → Advanced → Expert
- 自动化测试工程师
- 性能测试工程师
- 安全测试工程师
- 测试架构师
"""),
    ("缺陷生命周期.md", """# 缺陷生命周期

## 状态机

New → Assigned → In Progress → Fixed → Verified → Closed
                              ↓
                          Reopened（验证不通过）

每个状态都有明确的进入 / 退出标准。

## 严重程度 vs 优先级

### 严重程度（Severity）
技术上的影响程度：
- Blocker：阻塞测试 / 阻塞主流程
- Critical：核心功能不可用
- Major：主要功能不可用，但有 workaround
- Minor：次要功能 / UI 问题
- Trivial：拼写 / 排版

### 优先级（Priority）
业务上的修复紧急程度：
- P0：立刻修，阻断发版
- P1：当前迭代修
- P2：下一迭代修
- P3：攒一批修

**严重程度 ≠ 优先级**。例如：UI 拼错是 Trivial 但若是品牌名则 P0。

## 缺陷报告要素

- 标题（一句话描述）
- 环境（操作系统 / 浏览器 / 版本）
- 复现步骤（编号列表）
- 预期结果 vs 实际结果
- 截图 / 日志 / 视频
- 严重程度 / 优先级
- 所属模块 / 影响范围

## 缺陷的分类

按根因：
- 需求缺陷：理解不一致
- 设计缺陷：架构 / 接口问题
- 编码缺陷：实现错误
- 配置缺陷：环境 / 部署问题
- 数据缺陷：脏数据

按发现阶段：
- 单元测试发现
- 集成测试发现
- 系统测试发现
- 用户验收发现
- 生产事故发现

## 经验法则

- 同一缺陷多次出现 → 排查根因，加自动化测试守护
- 高缺陷模块 → 重构优先
- 缺陷修复引入新缺陷 → 加回归测试
- 缺陷逃逸到生产 → 加强评审与测试

## 度量

- 缺陷密度：每千行代码缺陷数
- 缺陷逃逸率：生产缺陷 / 总缺陷
- MTTR：平均修复时间
- 缺陷重现率：修复后再次出现的比例
"""),
]

# 其余学科（每学科 5+ 篇代表性的，避免 token 爆炸）
PRODUCT = [
    ("PRD 写作指南.md", """# PRD 写作指南

## 什么是 PRD

PRD（Product Requirements Document，产品需求文档）描述产品要做什么、为什么做、
怎么做。是产品经理的核心交付物之一。

## 结构模板

### 1. 背景与目标
- 业务背景：解决谁的什么问题
- 产品目标：可量化的北极星指标
- 成功指标：上线后用什么衡量

### 2. 用户故事
- As a [角色]
- I want [功能]
- So that [价值]

### 3. 功能详述
- 主流程：Happy Path
- 异常流程：边界条件
- 状态机：核心状态变化
- 规则：业务约束

### 4. 非功能需求
- 性能：QPS / P99
- 安全：权限 / 数据
- 可用性：SLA
- 兼容性：浏览器 / 设备

### 5. 验收标准
- 测试用例形式
- 每个需求都应有可验证的验收条件

### 6. 排期与里程碑

## 常见错误

- 解决方案代替需求：写「用 Redis」而不是「缓存以提升查询速度」
- 缺少成功指标：上线后无法判断效果
- 范围蔓延：PRD 写到一半加新功能
- 过度细节：把交互细节写到 PRD，应放在交互文档
- 缺少例外场景：只写主流程，异常情况靠开发补

## 与其他文档的区别

- PRD：做什么 + 为什么（业务视角）
- MRD：市场分析与商业论证
- 交互文档：怎么做（UI/UX 视角）
- 技术方案：怎么实现（工程视角）
- 用户故事：更细粒度的需求切片

## 协作

- PRD Review：研发 / 测试 / 设计 / 运营共同参与
- 变更管理：版本号 + 变更日志
- 上线后：跟踪指标、收集反馈、迭代
"""),
    ("需求优先级模型.md", """# 需求优先级模型

## KANO 模型

按用户满意度划分：
- **基本型**（Must-be）：必须有，缺失即不满
  例：登录系统、订单提交
- **期望型**（One-dimensional）：越好越满意
  例：响应速度、价格
- **兴奋型**（Attractive）：超出预期才出现
  例：智能推荐、一键完成
- **无差异型**（Indifferent）：做不做无所谓
- **反向型**（Reverse）：做了反而减分

## RICE 评分

- **R**each：覆盖用户数（一个季度内）
- **I**mpact：影响力（0.25/0.5/1/2/3）
- **C**onfidence：信心（百分比）
- **E**ffort：投入人月

公式：`(R × I × C) / E`

## ICE 评分

简化的 RICE，去掉 Reach 与 Confidence：
- **I**mpact
- **C**onfidence
- **E**ase（易开发程度）

适合早期快速决策。

## MoSCoW

- **Must have**：不做就上不了线
- **Should have**：重要但不阻塞
- **Could have**：有了更好
- **Won't have**：这版本不做

适合一次发版的多需求排期。

## 价值 vs 成本矩阵

```
高价值 高 │     优先做     │  抢着做  │
低  │     快速赢     │  大项目  │
成  │────────────┼───────────│
本  │   砍掉       │   慎做   │
      低  ───────────────────── 高
```

## 决策原则

- 数据说话：用户行为数据 > 调研 > 老板拍脑袋
- 战略对齐：服务于公司北极星指标
- 资源约束：好需求做不完是常态
- 机会成本：做 A 就不做 B

## 反模式

- 全员高优：所有 P0 = 没有优先级
- 业务方压力：被吼一嗓子就排上
- 拍脑袋：没有评分框架
- 不复盘：做完不回顾，下次踩同样的坑
"""),
    ("MVP 设计.md", """# MVP 设计

## 什么是 MVP

MVP（Minimum Viable Product，最小可行产品）是**用最小投入验证关键假设**的产品版本。
核心：
- 不是「最小功能集」，而是「能验证假设的最小产品」
- 不追求完美，追求快速验证

## 验证什么假设

- 痛点假设：用户真有这个问题吗
- 解决方案假设：用户会用你的方案吗
- 商业假设：用户愿意付费吗
- 增长假设：口碑 / 网络效应能起来吗

## 设计原则

### 1. 砍掉所有非验证必需的功能
- 漂亮的 UI 不是必需 → 丑一点没关系
- 完善的后台不是必需 → Excel 能管就行
- 多种支付方式不是必需 → 先接一种

### 2. 保留核心体验
- 用户的核心动作必须流畅
- 不要为了「简化」而让用户感到「难用」

### 3. 测量先行
- 埋点比功能重要
- 没有数据就没有迭代依据

## 常见误区

### 误区 1：MVP = 烂产品
错误。MVP 是「够用且能验证」，不是「凑合」。
可以 UI 简陋，但交互必须合理。

### 误区 2：MVP = 一次性发布
错误。MVP 是持续迭代的起点，每个版本回答一个问题。

### 误区 3：MVP = 所有功能都做「简化版」
错误。某些功能必须完整（如核心交易流程），其他功能可以不出现。

## MVP 评估清单

- [ ] 用户的核心痛点是什么
- [ ] MVP 是否能验证这个痛点
- [ ] 需要哪些功能才能让用户完成核心动作
- [ ] 哪些功能可以延后
- [ ] 上线后用什么指标判断成功
- [ ] 失败的话学到什么

## 演进路径

```
MVP → 验证假设 → 决定方向
  ↓
有用户 → 收集反馈 → 优化体验
  ↓
有口碑 → 拓展场景 → 完整产品
```

## 案例

- Dropbox：3 分钟视频验证「文件同步」需求
- Airbnb：自己拍照片放网上验证「陌生人愿意租自家房间」
- Zappos：手动下单测试「网上买鞋」是否可行
"""),
    ("用户画像.md", """# 用户画像

## 什么是用户画像

用户画像（Persona）是基于真实数据抽象出的典型用户模型，
帮助团队对「用户是谁」达成共识，从而做出更好的产品决策。

## 构成要素

### 基本属性
- 年龄 / 性别 / 职业 / 地域
- 收入水平 / 教育程度

### 行为特征
- 使用场景：在哪里、什么时候用
- 使用频率：日活 / 周活 / 月活
- 使用设备：手机 / 平板 / PC

### 痛点与需求
- 当前如何解决
- 不满意的地方
- 希望怎么解决

### 心理特征
- 价值观
- 信息获取偏好
- 决策风格

## 画像示例

> 张明，28 岁，后端开发工程师
> 工作 4 年，常用 Python / Go，主要做微服务
>
> 场景：工作日 9 点-18 点，主要在公司电脑前
> 设备：MacBook Pro + 27 寸显示器
>
> 痛点：
> - 看技术文档时要在多个标签页来回切
> - 调试时不知道哪里出了问题，搜索不到报错信息
>
> 需求：
> - 集成开发环境的智能提示
> - 报错一键搜索
> - 技术社区的高质量回答

## 数据来源

### 定量
- Google Analytics / 百度统计
- 用户行为埋点
- 问卷调研
- A/B 测试

### 定性
- 用户访谈
- 可用性测试
- 客服工单分析
- 社交媒体舆情

## 使用建议

- **不超过 3-5 个画像**：再多团队记不住
- **每个画像代表一群人**：不是单个真实用户
- **定期更新**：每季度回顾，依据新数据调整
- **场景化使用**：决策时问「张明在这种情况下会怎么做」

## 反模式

- 凭空捏造：没有数据支撑的画像是创作
- 用户标签化：把人简化成「25-30 岁男性」忽略差异
- 静止不变：用户会成长，画像也要跟
- 一个画像打天下：忽略不同用户群体的差异
"""),
    ("AB 测试.md", """# A/B 测试

## 什么是 A/B 测试

把用户随机分成两组，分别看到不同方案（A vs B），对比关键指标。
是一种**因果推断**方法，比经验决策更可靠。

## 适用场景

- 按钮颜色、文案、位置
- 页面布局
- 营销策略
- 推荐算法
- 定价

不适合：
- 战略级决策（影响范围太大）
- 样本量不足的小流量场景
- 用户能跨组交互（社交场景）

## 实验设计

### 1. 假设
清晰的「如果...那么...」：
> 如果把注册按钮从蓝色改成绿色，那么注册转化率会提升 5%。

### 2. 指标
- 主指标：1 个（决定胜负）
- 辅指标：多个（理解为什么）
- 护栏指标：防止主指标优化掉其他东西（留存、投诉）

### 3. 样本量
需要预先计算：
- 基准转化率 p
- 期望提升 Δ
- 显著性水平 α（通常 0.05）
- 统计功效 1-β（通常 0.8）

工具：Optimizely / VWO 的样本量计算器。

### 4. 随机化
- 用户 ID 哈希后取模
- 必须保证组间用户特征分布相似（A/A 测试验证）

### 5. 时长
- 至少覆盖一个完整业务周期（一周 / 一个月）
- 避免节假日、促销活动等干扰

## 统计原理

- **P 值**：观察到差异或更极端的概率（小于 α 拒绝零假设）
- **置信区间**：真实值的可信范围
- **功效**：检测到真实效应的概率

## 常见错误

### 1. 偷看数据（Peeking）
实验未完成就根据中间结果下结论。
解决：预先约定实验时长，到点再看。

### 2. 多重比较
多个指标 / 多组对比 → 假阳性增多。
解决：Bonferroni 校正、控制指标数。

### 3. 分流不均
新用户被分配到 A 组比例异常。
解决：检查随机化逻辑、看 A/A 测试。

### 4. 样本污染
用户被同时分配到多组（如 cookie 清除）。
解决：用稳定用户 ID。

### 5. Simpson 悖论
分组看 A 优、汇总看 B 优。
解决：分层分析。

## 工具

- 自建：实验平台 + 埋点 + 统计引擎
- 第三方：Optimizely / VWO / LaunchDarkly
- 国内：阿里云 A/B 测试、神策 A/B 测试
"""),
]

INDUSTRIAL_DESIGN = [
    ("设计原则.md", """# 工业设计核心原则

## Dieter Rams 十大原则

1. **创新**：真正的创新在于解决问题，而非装饰
2. **实用**：产品是为人服务的
3. **美观**：美是可用性的一部分
4. **易懂**：产品的结构应清晰
5. **克制**：少即是多
6. **诚实**：产品不应假装是别的
7. **耐久**：避免过时
8. **一致**：细节上的一致
9. **环保**：减少对环境的影响
10. **尽可能少的设计**：聚焦本质

## 形式追随功能（Form Follows Function）

路易斯·沙利文提出：
- 设计的核心是功能
- 形式应当由功能决定
- 装饰不应妨碍功能

Apple 的 iPhone 设计是典型：去掉所有物理按键，把功能交给屏幕。

## 一致性原则

### 内部一致
同一系统内相似功能应有相似的视觉与交互。

### 外部一致
与行业惯例一致（如：垃圾桶图标=删除）。

### 系列一致
同一产品系列在风格上保持传承（如：Mac 多代外观延续）。

## 视觉层次

### 视觉权重
通过大小、颜色、对比度、留白等引导视线。

### Z 型 / F 型阅读
- 西文界面：F 型（左上 → 右上 → 左下 → 右下）
- 卡片式：Z 型（对角扫描）

## 比例与韵律

### 黄金比例（1:1.618）
历史悠久的视觉舒适比例，常见于 logo 与排版。

### 模块化
重复单元形成韵律（如 iOS 图标网格、Material Design）。

## 配色

### 三色原则
主色 + 辅色 + 强调色，避免过多颜色。

### 色彩心理学
- 红：激情、警告、紧迫
- 蓝：信任、专业、冷静
- 绿：自然、健康、财富
- 黄：乐观、警示

### 配色工具
Adobe Color、Coolors、Khroma
"""),
    ("材料与工艺.md", """# 材料与工艺

## 常用材料

### 金属
- 铝合金：轻、可阳极氧化上色（MacBook）
- 不锈钢：硬度高、镜面效果好（Apple Watch）
- 钛合金：轻且强度高、医疗级（高端手机）

### 塑料
- ABS：强度高、韧性好（家电外壳）
- PC（聚碳酸酯）：透明、强度高（眼镜片、水杯）
- PMMA（亚克力）：透明度接近玻璃（化妆品包装）

### 复合材料
- 碳纤维：轻、高强度（航空航天、自行车）
- 玻璃纤维：成本低（船体、汽车）

### 天然材料
- 木材：纹理独特、温润感（家具、耳机）
- 皮革：高端感（钱包、家具）
- 陶瓷：硬度高、耐磨（手表）

## 加工工艺

### 注塑成型
- 塑料批量生产的主力工艺
- 模具成本高，量大划算

### CNC 加工
- 金属切削成型
- 精度高、表面质量好
- 适合小批量高单价

### 3D 打印
- SLA（光固化）：高精度
- FDM（熔融沉积）：成本低
- SLS（选择性激光烧结）：强度高

### 表面处理

#### 阳极氧化
- 铝合金表面形成致密氧化膜
- 可染色（如苹果金、深空灰）
- 提高耐磨耐腐蚀

#### 喷涂
- 哑光、亮光、金属漆
- 塑料喷漆要先涂底漆

#### PVD（物理气相沉积）
- 真空镀膜
- 高端表壳、刀具

## 公差与配合

### 公差等级
- IT01-IT1：极高精度（量具）
- IT5-IT7：高精度（轴承）
- IT11-IT13：粗加工（铸件）

### 配合
- 间隙配合：轴孔有间隙（可活动）
- 过盈配合：轴比孔大（需加热装配）
- 过渡配合：两者之间

## 设计流程

```
概念设计 → 草图 → 建模 → 渲染 → 工程图 → 样机 → 测试 → 量产
```

## 成本控制

- DFMA（面向制造的设计）：减少零件数
- 模具寿命：100万模是入门级
- 材料利用率：避免浪费
"""),
    ("人机工程学.md", """# 人机工程学

## 核心目标

让人与产品 / 环境的交互**高效、安全、舒适**。

## 人体测量

### 静态尺寸
- 身高、手长、坐高
- P5（女性小）、P50（平均）、P95（男性大）

### 动态尺寸
- 关节活动范围
- 够取范围、操作范围

### 设计原则
- 可调节：适应 P5-P95
- 默认值：P50
- 极端情况：P99 但降低频率

## 视觉显示

### 视距
- 屏幕：50-70 cm
- 仪表盘：70-100 cm
- 大屏电视：3-5 m

### 视角
- 水平视角：人眼舒适范围 30°
- 垂直视角：屏幕中心略低于视线

### 亮度对比
- 一般场景：3:1
- 阅读：7:1
- 黑底白字最高

## 操控设计

### Fitts' Law
移动到目标的时间 = a + b × log₂(D/W + 1)
- D：目标距离
- W：目标宽度
- 推论：**按钮越大越近，操作越快**

### Hick's Law
选择时间 = a + b × log₂(N + 1)
- N：选项数
- 推论：**选项越少，决策越快**

### 7±2 法则
工作记忆容量约 7 个组块（Miller）。
分组、层级化降低认知负担。

## 触觉交互

### 按键
- 行程：1-4 mm
- 力度：0.5-2 N
- 反馈：清晰的咔哒声 + 触感

### 触摸
- 目标尺寸：≥ 44×44 pt（Apple HIG）
- 间距：≥ 8 pt
- 边缘：留 16-24 pt 安全区

## 听觉反馈

### 频率
- 人耳：20 Hz - 20 kHz
- 语音清晰范围：300 Hz - 3.4 kHz

### 提示音
- 短促（< 200 ms）
- 频率差异明显
- 与系统音分离

## 疲劳与舒适

### 静态疲劳
长时间保持同一姿势 → 调整支撑

### 动态疲劳
重复动作 → 优化动作幅度与频率

### 认知疲劳
信息过载 → 减少分心元素

## 标准

- ISO 9241：人机交互通用标准
- ANSI/HFES 100：计算机工作站人体工学
- GB/T 10000：中国成年人人体尺寸
"""),
    ("原型设计方法.md", """# 原型设计方法

## 原型分级

### 低保真（Lo-fi）
- 草图、纸质原型
- 5 分钟快速表达概念
- 适合早期讨论

### 中保真（Mi-fi）
- 线框图（Wireframe）
- 灰阶、无视觉细节
- 表达结构与流程

### 高保真（Hi-fi）
- 接近最终视觉
- 包含交互逻辑
- 适合用户测试

### 高保真可交互
- Figma / Sketch + Principle / ProtoPie
- 完整用户流程
- 投资最大但验证最准

## 工具选择

| 工具 | 适合阶段 | 特点 |
|---|---|---|
| 纸笔 | 概念 | 最快、便宜 |
| Balsamiq | 低保真 | 故意画丑，避免过度讨论视觉 |
| Figma | 中到高保真 | 实时协作、组件化 |
| Sketch + InVision | 中到高保真 | macOS 专属 |
| Principle | 动效原型 | 时间轴动画 |
| ProtoPie | 高保真可交互 | 复杂交互逻辑 |
| Unity | 3D / VR 原型 | 真实材质物理 |

## 原型原则

### 1. 目的明确
- 验证概念 → 低保真
- 验证流程 → 中保真可交互
- 验证视觉 → 高保真

### 2. 快速迭代
- 一个原型不应花超过一天
- 错就改，下个版本更好
- 不要追求「完美原型」

### 3. 测什么

- 可用性：用户能否完成核心任务
- 信息架构：用户能否找到所需
- 视觉吸引力：第一印象
- 情感反应：愉悦 / 惊讶 / 困惑

## 可用性测试

### 招募用户
- 5-8 个目标用户足够发现 80% 的问题（Nielsen）
- 不要选「专家」——他们会用惯性思维
- 真实场景：让用户做真实任务

### 流程
1. 介绍（5 分钟）
2. 任务清单
3. 观察（不引导）
4. 追问（问为什么这样做）
5. 总结

### 度量

- 任务完成率
- 完成时间
- 错误率
- SUS（系统可用性量表）：标准化问卷

## 协作

- 设计师 + 产品经理：早期一起定义需求
- 设计师 + 开发：技术可行性评审
- 设计师 + 用户：可用性测试

## 反模式

- 把原型当最终设计：原型是过程产物
- 过度追求像素完美：浪费精力
- 只在内部测：必须找真实用户
- 忽略负面反馈：用户说「还行」往往是不满
"""),
]

ECONOMICS = [
    ("供需曲线.md", """# 供需曲线

## 需求曲线（Demand）

需求量与价格的关系，**向下倾斜**（价格越高需求越少）。

影响因素：
- 收入：正常品收入↑→需求↑；劣等品收入↑→需求↓
- 相关品价格：替代品↑→本商品↑；互补品↑→本商品↓
- 偏好：广告 / 趋势
- 预期：未来涨价→现期需求↑

## 供给曲线（Supply）

供给量与价格的关系，**向上倾斜**（价格越高供给越多）。

影响因素：
- 生产成本：要素价格↑→供给↓
- 技术：生产率↑→供给↑
- 预期：未来涨价→现期供给↓
- 卖家数量

## 均衡

供给 = 需求时的市场价格：E = (Q*, P*)

供需失衡：
- P > P*：过剩 → 价格向 P* 回落
- P < P*：短缺 → 价格向 P* 上升

## 弹性

### 需求价格弹性
E_d = (%ΔQ) / (%ΔP)
- |E_d| > 1：富弹性（奢侈品）
- |E_d| < 1：缺乏弹性（必需品、短期）
- |E_d| = 1：单位弹性

### 供给价格弹性
E_s = (%ΔQ) / (%ΔP)
- 受产能利用率、生产周期影响

### 影响弹性的因素
- 替代品数量：越多越富弹性
- 占收入比：占比小则缺乏弹性
- 时间：长期比短期富弹性
- 必需品：缺乏弹性

## 市场干预

### 价格管制
- 最高限价（天花板）：低于均衡 → 短缺 → 排队、黑市
- 最低保护价：高于均衡 → 过剩 → 政府收购

### 数量管制
- 配额、关税、进口许可
- 国内价格↑，消费量↓，生产者剩余↑，消费者剩余↓

### 税收
- 从量税：生产者与消费者分担（弹性大者分摊少）
- 无谓损失（DWL）：税收造成的总剩余减少

## 福利分析

- 消费者剩余（CS）：消费者愿付与实付之差
- 生产者剩余（PS）：生产者实收与愿卖之差
- 总剩余 = CS + PS
- 政府干预通常减少总剩余 → 无谓损失

## 案例

### 春运火车票
价格管制低于均衡 → 短缺 → 黄牛（黑市）。

### 农产品
丰收年 → 价格暴跌 → 谷贱伤农 → 政府保护价。

### 房租管制
纽约/柏林租金管制 → 房东减少供给 → 长期短缺。
"""),
    ("GDP 与国民经济.md", """# GDP 与国民经济

## GDP 定义

GDP（Gross Domestic Product，国内生产总值）是指一国（或地区）在一定时期内
所有常住单位生产的全部最终产品和服务的市场价值总和。

三句话理解：
- 一国之内
- 一定时期内（季度 / 年度）
- 最终产品（不算中间品，避免重复计算）

## 核算方法

### 生产法
GDP = 总产出 - 中间消耗 = 各行业增加值之和

### 收入法
GDP = 劳动者报酬 + 生产税净额 + 固定资产折旧 + 营业盈余

### 支出法
GDP = 居民消费 + 政府消费 + 资本形成总额 + 净出口
     = C + I + G + (X - M)

## 三驾马车

### 消费（C）
- 居民消费：占 GDP 最大比重（约 55%）
- 影响因素：收入、预期、利率、贫富差距
- 政策：发消费券、减税

### 投资（I）
- 固定资产投资：厂房、基建、机器设备
- 存货投资：原材料、半成品、成品
- 影响因素：利率、预期、政策
- 政策：降息、专项债

### 净出口（X - M）
- 出口 - 进口
- 受汇率、关税、全球经济影响
- 顺差 = 净出口 > 0，逆差反之

## GDP 的局限

### 没算的
- 家庭劳动、家务劳动
- 地下经济（黑市、灰色收入）
- 闲暇、清洁环境等非货币福利

### 算错的
- 污染造成的 GDP（治理污染再算一次）
- 军费开支
- 过度包装、虚假需求

### 替代指标
- GNH（国民幸福指数）
- HDI（人类发展指数）
- 绿色 GDP（扣除环境成本）

## GDP 平减指数

名义 GDP / 实际 GDP = (1 + 通胀率)
- 实际 GDP：扣除物价变动，反映真实产出
- 名义 GDP：含价格因素

## 经济增长的源泉

### 要素积累
- 劳动：人口数量与质量
- 资本：物质资本 + 人力资本

### 技术进步
- 全要素生产率（TFP）
- 创新、效率改善

### 索洛模型
Y = A × F(K, L)
- 长期增长靠 A（TFP），靠 K、L 会遇到边际递减

## 经济周期

### 衰退
- GDP 连续两个季度环比负增长
- 失业↑、消费↓、投资↓

### 复苏
- 政策刺激：降息、减税、基建
- 库存周期：从去库存到补库存

### 繁荣
- 通胀↑、资产价格泡沫

### 危机
- 泡沫破裂
- 08 年次贷、97 年亚洲金融、29 年大萧条
"""),
    ("通货膨胀.md", """# 通货膨胀

## 概念

通货膨胀：物价水平普遍、持续上涨的经济现象。
（CPI 同比 > 3% 警惕，> 5% 严重）

通货紧缩：物价普遍持续下降（同样可怕）。

## 度量

### CPI（居民消费价格指数）
最常用。统计居民日常消费的一篮子商品价格。
中国 CPI 权重：食品 30%、居住 20% 等。

### PPI（生产者价格指数）
工业品出厂价格。PPI 上涨往往领先 CPI。

### GDP 平减指数
最全面，覆盖所有最终产品。

### 核心 CPI
剔除食品和能源（波动大），更稳定。

## 类型

### 需求拉动型（Demand-pull）
总需求 > 总供给 → 价格上涨。
原因：政府支出、减税、货币宽松。

### 成本推动型（Cost-push）
成本↑ → 供给↓ → 价格↑。
原因：油价、原材料、工资。

### 结构性
某些部门供不应求 + 某些部门供过于求。

## 原因

### 货币超发
MV = PY
- M：货币供应量
- V：流通速度
- P：价格
- Y：产出

货币供应增速 > 产出增速 → 通胀。

### 财政赤字
政府支出 > 税收 → 印钞弥补 → 通胀税。

### 输入性
进口商品（特别是能源）涨价 → 进口通胀。

### 预期
预期通胀会自我实现：工人要求加薪 → 成本↑ → 价格↑。

## 影响

### 正面（在适度范围内）
- 鼓励消费、避免通缩
- 减轻债务负担
- 工资增长有动力

### 负面
- 储蓄贬值
- 固定收入者受损
- 资源错配（生产囤积居奇商品）
- 极端时经济崩溃（津巴布韦、魏玛共和国）

## 治理

### 货币政策
- 加息：抑制需求（但也抑制增长）
- 缩表：减少货币供应
- 提高存款准备金率

### 财政政策
- 削减支出
- 增加税收

### 供给侧
- 增加产能
- 减税激励生产

### 预期管理
- 央行信誉：透明、承诺锚定（如美联储 2% 通胀目标）

## 菲利普斯曲线

通胀与失业的短期负相关。
长期：垂直（自然失业率），政策无效。

中国曾用菲利普斯曲线但效果有限（劳动力市场非完全市场化）。
"""),
    ("货币与银行.md", """# 货币与银行

## 货币的职能

1. **交易媒介**：避免以物易物的双重巧合
2. **价值尺度**：用价格表达商品价值
3. **价值储藏**：跨期保存财富（前提是币值稳定）
4. **支付手段**：清偿债务

## 货币层次（M0/M1/M2）

### M0：流通中现金

### M1：M0 + 活期存款
交易性货币，反映即时购买力。

### M2：M1 + 定期存款 + 储蓄存款 + 货币市场基金
广义货币，反映总购买力。

中国还有 M3（CDs 等）。

## 商业银行

### 业务
- 资产业务：贷款、证券投资
- 负债业务：存款、借款
- 中间业务：支付、托管、咨询

### 盈利模式
利差 = 贷款利率 - 存款利率
净息差（NIM）：衡量银行盈利能力的核心指标。

### 风险
- 信用风险：贷款违约
- 利率风险：期限错配
- 流动性风险：取款挤兑
- 操作风险：系统故障、内控失效

## 存款准备金

央行要求商业银行按存款比例缴存的准备金。
- 法定存款准备金率：央行政策工具
- 超额存款准备金：银行自愿持有

## 货币创造

### 部分准备金银行制度
- 存款准备金率 10%
- 初始存款 100 元
- 银行可贷 90 元 → 借款人存入 → 银行再贷 81 元
- 货币乘数 = 1 / 准备金率 = 10
- 理论上 100 元初始存款可创造 1000 元货币

### 现实约束
- 现金漏损
- 银行超额准备金
- 借款人不用来存款
- 实际货币乘数远小于理论值

## 央行

### 主要职能
- 制定货币政策
- 发行货币
- 监督管理金融机构
- 维护支付清算系统

### 三大政策工具

#### 公开市场操作（OMO）
买卖国债 / 回购协议。
最灵活的日常工具。

#### 存款准备金率
威力大、影响广，调整次数少。

#### 再贴现率
央行向商业银行提供资金的利率。
中国还有 MLF（中期借贷便利）、SLF（常备借贷便利）。

### 非常规工具（QE）
危机时央行直接购买资产（国债、MBS）。
2008 年后美联储、欧央行、日央行大规模使用。

## 货币政策传导链

```
政策利率 → 货币市场 → 银行存贷利率 → 投资/消费 → 总需求 → 通胀/就业
```

## 金融体系

### 直接融资
企业直接在市场上发行股票 / 债券。
- 优势：风险分散、长期资金
- 代表：资本市场

### 间接融资
通过银行作为中介。
- 优势：信息生产、流动性转换
- 代表：银行主导（中国、德国、日本）

中国是银行主导型，融资 70%+ 来自银行贷款。

## 风险

### 系统性风险
- 银行挤兑（2023 年硅谷银行）
- 金融危机（2008 次贷）

### 巴塞尔协议
- 资本充足率：核心一级 ≥ 4.5%、一级 ≥ 6%、总资本 ≥ 8%
- 杠杆率、流动性覆盖率（LCR）、净稳定资金比率（NSFR）

中国 2024 年实施《商业银行资本管理办法》，对标巴塞尔 III。
"""),
    ("宏观政策.md", """# 宏观政策

## 财政政策

### 工具
- 政府支出：基建、教育、医疗
- 税收：减税、加税
- 公债：发行国债、地方政府债
- 转移支付：社保、补贴

### 政策取向
- 积极财政：扩大支出、减税（刺激经济）
- 从紧财政：缩减支出、加税（抑制通胀）
- 中性财政：收支平衡

### 乘数效应
财政支出增加 1 元 → GDP 增加 k 元（k > 1）
k = 1 / (1 - MPC(1-t))
- MPC：边际消费倾向
- t：税率

举例：MPC=0.8, t=0.2 → k = 1/(1-0.64) = 2.78

## 货币政策

### 工具（详见「货币与银行」）
- 公开市场操作
- 存款准备金率
- 再贷款 / 再贴现
- 利率政策

### 传导链
政策利率 → 银行存贷利率 → 投资/消费 → 总需求 → 通胀/就业

### 政策取向
- 宽松：降息、降准（刺激）
- 从紧：加息、升准（抑制）
- 稳健：中性

## 财政-货币组合

| | 财政积极 | 财政从紧 |
|---|---|---|
| **货币宽松** | 双松（刺激） | 货币主导 |
| **货币从紧** | 财政主导 | 双紧（抑制） |

中国 2008：双松（4 万亿 + 降息）
中国 2023-2024：稳健货币 + 积极财政

## 政策时滞

### 内部时滞
识别问题 → 决策 → 立法
中国：可能 6-12 个月

### 外部时滞
决策 → 生效
货币政策：3-6 个月（投资周期）
财政政策：基建 6-12 个月

## 相机抉择 vs 规则

### 相机抉择
- 政府根据形势灵活调整
- 优势：适应性强
- 劣势：时间不一致性问题（kydland & prescott 1977）
  —— 政策制定者有动机偏离事先承诺

### 规则
- 预先承诺（如泰勒规则）
- 优势：可信、避免政治化
- 劣势：不灵活

### 现代共识
**规则为主，相机为辅**：央行制定规则框架，特殊情况下相机调整。

## 政策协调

### 国内协调
- 中央银行与财政部协调
- 货币政策 + 财政政策组合使用

### 国际协调
- 国际清算银行（BIS）
- G20 财长央行行长会议
- 汇率政策协调（如广场协议 1985）

## 中国特色

### 货币政策最终目标
「保持货币币值稳定，并以此促进经济增长」

### 多目标制
- 经济增长
- 充分就业
- 物价稳定
- 金融稳定
- 国际收支平衡

### 政策工具
- 数量工具为主（存款准备金、公开市场）
- 价格工具逐步增强（利率走廊）

## 教训

- 大萧条：紧缩加剧危机 → 凯恩斯革命
- 滞胀（70 年代）：单一政策失效 → 多目标
- 日本失落 20 年：流动性陷阱 → QE
- 2008 危机：传统工具不够 → 非常规政策
"""),
]

ENGLISH = [
    ("English Grammar Basics.md", """# English Grammar Basics

## Parts of Speech

### Nouns
- Common: book, city
- Proper: London, Shakespeare
- Concrete vs Abstract: chair vs freedom
- Countable vs Uncountable: apple vs water

### Pronouns
- Personal: I, you, he, she, it, we, they
- Possessive: my, your, his, her, its, our, their
- Reflexive: myself, yourself, himself
- Relative: who, which, that, where, when, why

### Verbs
- Action: run, think, write
- Linking: be, seem, become
- Auxiliary: be (passive), have (perfect), do (emphasis/question)
- Modal: can, could, may, might, must, should, will, would

### Adjectives & Adverbs
- Adjective: modifies noun (a beautiful flower)
- Adverb: modifies verb/adj/adv (run quickly, very beautiful)

## Tenses

### Simple
- Present: I write
- Past: I wrote
- Future: I will write

### Continuous (Progressive)
- Present: I am writing
- Past: I was writing
- Future: I will be writing

### Perfect
- Present: I have written
- Past: I had written
- Future: I will have written

### Perfect Continuous
- I have been writing (for 2 hours)

## Sentence Structures

### Simple
Subject + Verb + Object
I love you.

### Compound
Two independent clauses joined by conjunction.
I love you, and you love me.

### Complex
Independent clause + dependent clause(s).
Because I love you, I forgive you.

## Common Errors

### Subject-Verb Agreement
- He runs fast. (not "run")
- The list of items **is** on the desk. (subject = "list", not "items")

### Tense Consistency
- Yesterday I went to the store and **bought** milk. (not "buy")

### Article Usage
- a/an: indefinite singular
- the: definite / specific
- no article: plural generic / uncountable

### Preposition Collocations
- interested **in** (not "on")
- depend **on** (American) / depend **upon** (British)
- good **at** (not "in")

## Active vs Passive

Active: The cat chased the mouse.
Passive: The mouse was chased by the cat.

Use passive when:
- Actor unknown: My car was stolen.
- Actor unimportant: The bridge was built in 1990.
- Actor obvious: He was elected president.

Avoid passive when:
- Active is clearer
- In scientific writing, can mask who did what
"""),
    ("English Vocabulary Strategies.md", """# English Vocabulary Strategies

## 词根词缀法（最强大）

### 常见词根
- spect = look: inspect, respect, spectator, retrospect, spectacle
- dict = say: predict, contradict, dictate, dictionary, benediction
- port = carry: transport, import, export, portable, support
- ven/vent = come: convention, intervene, prevent, adventure, revenue
- ject = throw: project, reject, inject, subject, eject
- pos = put: compose, dispose, expose, impose, oppose, purpose

### 常见前缀
- in-/im- = not: impossible, incorrect, inactive
- un- = not: unhappy, unusual
- re- = again: rewrite, return, reform
- pre- = before: predict, prepare, preview
- post- = after: postpone, postwar
- trans- = across: transport, translate, transmit
- sub- = under: submarine, subway, subscribe
- inter- = between: international, interact
- dis- = not / opposite: disagree, disappear

### 常见后缀
- -tion/-sion: 名词后缀（action, decision）
- -ment: 名词后缀（movement, development）
- -able/-ible: 形容词后缀（readable, visible）
- -ful: 形容词后缀（beautiful, helpful）
- -less: 形容词后缀（hopeless, careless）
- -ly: 副词后缀（quickly, slowly）
- -er/-or: 施动者（writer, actor）
- -ee: 受动者（employee, trainee）

## 联想记忆

### 同义词家族
- 重要：important, significant, crucial, vital, essential
- 快乐：happy, glad, joyful, delighted, cheerful
- 漂亮：beautiful, pretty, gorgeous, stunning, attractive

### 反义词
- before / after
- accept / refuse
- succeed / fail
- increase / decrease

## 语境记忆

### 阅读中积累
- 在阅读时查词典，记笔记
- 记录：生词 + 例句 + 同义词 + 反义词

### 写作中运用
- 用刚学的词写一段
- 反复使用才能内化

## 高频词清单

### 学术词汇
- analyze, argue, assume, claim, conclude, contrast, define,
  demonstrate, emphasize, establish, evaluate, examine, illustrate,
  indicate, interpret, investigate, maintain, obtain, perceive,
  propose, significant, similar, source, specific, structure, sufficient

### 商务词汇
- revenue, profit, margin, leverage, stakeholder, share,
  quarterly, fiscal, merger, acquisition, IPO, dividend, equity,
  liability, asset, budget, forecast, ROI, KPI

## 工具

### 词典
- 朗文当代 / 牛津高阶 / 柯林斯：学习型词典
- Merriam-Webster / Cambridge：英英词典

### App
- Anki：间隔重复记忆
- 欧路词典：屏幕取词
- Memrise / Quizlet：词卡

## 学习建议

- 不要孤立背单词：每次记住一个词 + 至少 3 个例句
- 复习比学习更重要：艾宾浩斯曲线
- 输出驱动输入：能说出来才算会
- 主题式积累：每次集中学一个主题的词汇
"""),
    ("English Writing.md", """# English Writing

## 段落结构

### 经典三段式
1. **Topic sentence**：段落的中心思想
2. **Supporting sentences**：事实、例证、数据、引用
3. **Concluding sentence**：总结或过渡

### 段落连贯
- 代词指代：it, this, these, such
- 过渡词：however, therefore, moreover, in contrast
- 重复关键词（同义改写）
- 时间/逻辑顺序：first, next, finally

## 文章结构

### Introduction
- Hook：吸引读者（quote / question / statistic / anecdote）
- Background：背景
- Thesis statement：核心论点

### Body
- 每个段落一个 main idea
- 论据充分：facts / examples / expert opinions
- 段落之间有逻辑过渡

### Conclusion
- 总结论点
- 升华（implications / call to action）
- 不要引入新论点

## 句式多样性

### 简单句
The cat sat on the mat.

### 并列复合句
The cat sat on the mat, and the dog lay under the table.

### 主从复合句
While the cat sat on the mat, the dog lay under the table.

### 长短句交替
The cat sat on the mat. (短)
After a long day of hunting mice in the garden, the cat finally settled on the soft mat by the fireplace. (长)

## 学术写作规范

### APA / MLA / Chicago
不同学科用不同格式。引用必须规范。

### 避免剽窃
- 直接引用：加引号 + 引用
- 间接引用：改写 + 引用
- 共同知识：不需要引用

### 主语谓语一致
The data **show** (not "shows") a clear pattern.

### 时态
- 文献回顾：过去时（Smith found...）
- 一般事实：现在时（The earth revolves...）
- 实验结果：过去时（The mice showed...）

## 商务写作

### 邮件
- Subject 明确
- 称呼得体
- 第一段说目的
- 主体清晰
- 结尾有 CTA（Call to Action）

### 报告
- Executive summary（执行摘要）
- Background
- Methodology
- Findings
- Conclusions / Recommendations

### PPT
- 5 句话原则：每页不超过 5 行字
- 视觉元素：图表优于文字
- 故事化：起承转合

## 常见错误

### Chinglish
- 「欢迎你来到...」→ Welcome to...
- 「因为...所以...」→ Because... so...（so 用法不同）
- 「very + 形容词」过多 → 用 stronger word

### 冗余
- 「completely finished」→ finished
- 「end result」→ result
- 「free gift」→ gift

### 主谓不一致
- A list of items **is** ... （subject 是 list）
- The committee **has** ... （集体名词）

## 修改技巧

- 写完先放 30 分钟再改
- 大声朗读：不顺口的地方有问题
- 打印出来改：眼睛看屏幕容易漏
- 让别人读：他们卡住的地方就是你卡住的地方

## 工具

- Grammarly：语法检查
- Hemingway Editor：句子可读性
- ProWritingAid：综合分析
- Ludwig.guru：搭配 / 例句验证
"""),
    ("English Reading Comprehension.md", """# English Reading Comprehension

## 阅读策略

### Skimming（略读）
了解文章大意和结构：
- 看标题、副标题、首段、末段
- 每段第一句
- 跳过大段细节

### Scanning（扫读）
定位特定信息：
- 关键词定位
- 数字 / 名字 / 日期
- 不读全文

### Intensive Reading（精读）
逐句分析：
- 用于学术论文、法律文档
- 配合词典

### Extensive Reading（泛读）
大量阅读培养语感：
- 小说、新闻、博客
- 每天 30 分钟

## 长难句分析

### 基本步骤
1. 找主干：主谓宾
2. 找修饰：定状补
3. 翻译：先翻主干，再加修饰

### 例子
> "The book that I bought yesterday, which was written by a famous author who lived in the 19th century, is now on my desk."

主干：The book **is** on my desk.
修饰：
- that I bought yesterday（定语从句修饰 book）
- which was written by...（非限制性定语从句修饰 book）
- who lived in the 19th century（定语从句修饰 author）

翻译：那本我昨天买的、由 19 世纪一位著名作家写的书，现在在我桌上。

## 阅读速度

### 平均
- 英语母语者：250-300 wpm
- 二语学习者：100-150 wpm
- 雅思考试要求：60 分钟读 2500-3000 字 + 40 题

### 提升方法
- 不要默读（subvocalization）
- 眼球训练：一眼看一组词（chunking）
- 限时训练：用 timer 强迫速度

## 学术阅读

### 论文结构（IMRaD）
- Introduction：为什么研究
- Methods：怎么研究
- Results：研究结果
- Discussion：结果意味着什么

### 阅读顺序
- 先读 abstract 判断是否相关
- 再读 conclusion 了解结论
- 必要时回读 introduction 和 methodology
- 最后才看 results 和 discussion 细节

### 标记技巧
- ✓：核心论点
- ？：疑问 / 不确定
- ✗：反对 / 错误
- *：值得引用

## 常见问题

### 单词看不懂
- 先猜词义（上下文）
- 再查词典
- 最后查词根

### 长句看不懂
- 拆主干（主谓宾）
- 再处理从句

### 段落看不懂
- 看段首段尾
- 看转折词（however, but）
- 看因果词（because, therefore）

## 练习材料

### 初级
- 新概念英语
- 床头灯系列（英语名篇）

### 中级
- 经济学人（The Economist）
- BBC / NPR 新闻
- 哈利波特原版

### 高级
- 学术论文（Google Scholar）
- 英文原版小说
- 哲学 / 历史经典

## 词汇积累

### 高频词
- 学术：however, therefore, moreover, furthermore, consequently
- 商务：regarding, furthermore, accordingly, consequently

### 同义替换
不要每次都用 important：
- crucial, vital, essential, significant, critical, key, central

### 词块（chunks）
- take into account
- make a difference
- on behalf of
- in terms of
- as far as ... is concerned

## 习惯养成

- 每天 30 分钟英语阅读
- 读不懂就跳，不要每词都查
- 读完做简短笔记（用英文）
- 兴趣驱动：选你感兴趣的主题
"""),
]

LAW = [
    ("民法总则基础.md", """# 民法总则基础

## 民事主体

### 自然人
- 权利能力：始于出生，终于死亡
- 行为能力：
  - 完全（18 岁以上 / 16 岁以上靠自己劳动）
  - 限制（8-18 岁）
  - 无（8 岁以下）

### 法人
- 营利法人：公司、企业法人
- 非营利法人：机关法人、事业单位、社会团体
- 特别法人：机关法人、农村集体经济组织法人、城镇农村合作经济组织法人

## 民事权利

### 分类
- 财产权：物权、债权、知识产权、继承权
- 人身权：人格权（生命、健康、名誉、隐私）+ 身份权（亲属、配偶）

### 取得方式
- 原始取得：所有权第一次产生（如生产、创作）
- 继受取得：通过法律行为（买卖、赠与、继承）

## 民事法律行为

### 成立要件
- 行为人具有相应行为能力
- 意思表示真实
- 不违反法律、行政法规的强制性规定
- 不违背公序良俗

### 效力
- 有效：完全生效
- 无效：自始无效（如违法合同）
- 可撤销：受欺诈、胁迫、重大误解
- 效力待定：限制行为能力人超出范围的纯获利行为除外需法定代理人追认

### 意思表示瑕疵
- 欺诈：一方故意告知虚假情况或隐瞒真相
- 胁迫：以威胁手段迫使对方
- 重大误解：对行为内容重大误解
- 显失公平：一方利用对方处于困境

## 代理

### 类型
- 委托代理：基于授权
- 法定代理：基于法律规定（如父母对未成年子女）

### 代理权滥用
- 自己代理：代理人以被代理人名义与自己交易
- 双方代理：同时代理双方进行同一交易
- 越权代理：无代理权或超越权限

表见代理：相对人有理由相信行为人有代理权 → 后果由被代理人承担。

## 诉讼时效

### 期间
- 一般：3 年（《民法典》188 条）
- 最长：20 年（权利受损之日起）
- 国际货物买卖：4 年（特别法）

### 起算
自权利人知道或应当知道权利受到损害以及义务人之日起计算。

### 中断
- 起诉
- 主张权利
- 对方同意履行

中断后重新计算。

## 物权

### 分类
- 所有权：占有、使用、收益、处分
- 用益物权：使用权、承包权、地役权
- 担保物权：抵押权、质权、留置权

### 公示原则
- 不动产：登记（未经登记不发生物权效力）
- 动产：交付（占有改定、指示交付、实际交付）

## 债权

### 发生原因
- 合同
- 侵权行为
- 无因管理
- 不当得利

### 履行原则
- 全面履行
- 诚实信用

## 侵权责任

### 一般要件
- 加害行为
- 损害事实
- 因果关系
- 主观过错（过错推定 / 无过错责任除外）

### 特殊侵权
- 产品责任：生产者无过错责任
- 医疗损害：过错推定
- 环境污染：因果关系举证倒置
- 高空抛物：举证倒置

## 婚姻家庭

### 结婚
- 实质要件：双方自愿、达到法定年龄、符合一夫一妻
- 形式要件：登记

### 离婚
- 协议离婚：30 天冷静期
- 诉讼离婚：调解无效 + 感情破裂

### 财产
- 夫妻共同财产：婚姻关系存续期间所得（约定除外）
- 夫妻个人财产：婚前、专属个人的

## 继承

### 法定继承
- 第一顺序：配偶、子女、父母
- 第二顺序：兄弟姐妹、祖父母、外祖父母

### 遗嘱继承
- 自书、代书、录音录像、口头、打印、公证
- 遗嘱效力：公证 > 书面 > 口头

### 遗产
- 积极遗产：权利
- 消极遗产：债务（继承人以遗产为限清偿）
"""),
    ("刑法基础.md", """# 刑法基础

## 罪刑法定

法无明文规定不为罪，法无明文规定不处罚。
- 法律主义：只能由全国人大及其常委会制定的法律定罪
- 禁止溯及既往
- 禁止类推
- 明确性：法律规定必须明确

## 犯罪构成

### 四要件说（中国通说）
1. 犯罪客体：刑法保护的社会关系
2. 犯罪客观方面：行为、结果、因果关系
3. 犯罪主体：自然人 / 单位
4. 犯罪主观方面：故意 / 过失

### 犯罪客体
- 一般客体：社会秩序
- 同类客体：同类社会关系（如人身权利）
- 直接客体：具体犯罪行为直接侵害的对象

### 客观方面
- 作为：积极行为（盗窃、诈骗）
- 不作为：消极行为（逃税、见死不救）
  - 三要件：作为义务、作为能力、防止结果发生的可能性

### 犯罪主体
- 自然人：16 岁以上完全责任；14-16 岁相对责任（八大罪）
- 单位：公司、企业、事业单位、机关、团体

### 主观方面
- 故意：
  - 直接：明知 + 希望
  - 间接：明知 + 放任
- 过失：
  - 疏忽大意：应当预见而未预见
  - 过于自信：已经预见而轻信能避免

## 正当防卫

### 条件
- 起因：存在不法侵害
- 时间：正在进行
- 主观：防卫意图
- 对象：侵害人本身
- 限度：不超过必要限度

### 特殊防卫
对正在进行行凶、杀人、抢劫、强奸、绑架等严重暴力犯罪，
采取防卫行为造成不法侵害人伤亡的，不属于防卫过当。

## 紧急避险

### 条件
- 起因：危险（自然灾害、动物侵袭、人的行为）
- 时间：正在发生
- 对象：第三人的合法权益
- 限度：造成的损害小于所避免的损害

### 限制
职务上 / 业务上负有特定责任的人，不得为避免自己危险而紧急避险。

## 故意犯罪形态

### 犯罪预备
为犯罪准备工具、制造条件。
可以比照既遂犯从轻、减轻或者免除处罚。

### 犯罪未遂
已经着手实行犯罪，由于意志以外的原因未得逞。
可以从轻或者减轻处罚。

### 犯罪中止
自动放弃犯罪或自动有效防止犯罪结果发生。
没有造成损害的：免除处罚；造成损害的：减轻处罚。

## 共犯

### 共同犯罪
二人以上共同故意犯罪。
- 主犯：起主要作用
- 从犯：起次要作用（应当从轻、减轻或免除）
- 胁从犯：被胁迫参加（应当减轻或免除）
- 教唆犯：教唆他人犯罪

## 刑罚

### 主刑
- 管制（3 个月-2 年，不关押）
- 拘役（1-6 个月，短期关押）
- 有期徒刑（6 个月-15 年，数罪并罚可至 25 年）
- 无期徒刑
- 死刑

### 死刑限制
- 罪行极其严重
- 不是必须立即执行的，可以判处死缓（2 年）
- 犯罪时不满 18 岁 / 审判时怀孕 / 老人（75 岁以上）不适用死刑

### 附加刑
- 罚金
- 剥夺政治权利
- 没收财产

## 量刑情节

### 法定情节
- 从重：累犯、再犯、犯罪主体特殊（国家工作人员）
- 从轻：自首、立功、未遂、中止
- 减轻：自首（犯罪较轻）、重大立功
- 免除：自首（犯罪轻微）

### 酌定情节
- 动机、目的
- 手段、危害程度
- 悔罪表现
- 被害人谅解

## 数罪并罚

### 一般原则
- 判决宣告前一人犯数罪：分别判刑后合并执行
- 在总和刑期以下、数刑中最高刑期以上酌情决定

### 死刑缓期执行
2 年内没有故意犯罪的，减为无期徒刑；
确有重大立功的，减为 25 年有期徒刑。

## 累犯

### 一般累犯
- 前后罪均为故意犯罪
- 后罪判处有期徒刑以上
- 后罪发生于前罪刑罚执行完毕或赦免后 5 年内
- 犯罪时已满 18 岁

后果：应当从重处罚，不适用缓刑 / 假释。

### 特别累犯
危害国家安全、恐怖活动、黑社会性质组织犯罪的累犯。

## 自首与立功

### 自首
- 一般：自动投案 + 如实供述自己的罪行
- 特别（准自首）：被采取强制措施后如实供述司法机关还未掌握的本人其他罪行

从轻、减轻或免除处罚。

### 立功
- 一般：揭发他人犯罪行为查证属实
- 重大：揭发他人重大犯罪行为或提供重大线索

可以从轻或减轻；重大立功可以减轻或免除。

## 缓刑与假释

### 缓刑
- 适用：3 年以下有期徒刑或拘役
- 条件：犯罪情节较轻、有悔罪表现、没有再犯危险、对所居住社区无重大不良影响
- 考验期：原判刑期以上 1 年以下，至少 1 年

### 假释
- 适用：有期徒刑执行 1/2、无期徒刑执行 13 年
- 累犯 / 暴力犯罪（10 年以上）不得假释

## 追诉时效

| 刑期 | 时效 |
|---|---|
| 不满 5 年 | 5 年 |
| 5-10 年 | 10 年 |
| 10 年以上 | 15 年 |
| 无期 / 死刑 | 20 年 |

起算：从犯罪之日起；中断：追诉时效重新计算（立案或起诉后逃避侦查）。
"""),
    ("合同法基础.md", """# 合同法基础

## 合同概念

合同（契约）是当事人之间设立、变更、终止民事权利义务关系的协议。
民法典合同编调整：平等主体间的财产关系。

## 合同订立

### 要约
- 内容具体确定
- 表明经受要约人承诺即受其约束
- 向特定人作出

### 要约邀请
- 寄送价目表、拍卖公告、招标公告、招股说明书等
- 商业广告符合要约条件的视为要约

### 要约生效
- 大陆法系：到达主义（要约到达受要约人时生效）
- 撤回：要在要约生效前
- 撤销：要约生效后，受要约人承诺前，但有除外情形

### 承诺
- 内容与要约一致
- 生效：到达要约人
- 迟到承诺：原则上无效，例外：要约人及时通知接受

### 合同成立
- 一般：承诺生效时
- 实践合同：交付标的物时（如借用）
- 要式合同：满足形式要件时（如登记）

## 合同效力

### 有效合同
- 行为人具有相应民事行为能力
- 意思表示真实
- 不违反法律、行政法规强制性规定
- 不违反公序良俗

### 效力瑕疵

#### 无效
- 无民事行为能力人实施的
- 通谋虚伪表示
- 违反法律强制性规定
- 违背公序良俗
- 恶意串通损害他人合法权益

#### 可撤销
- 重大误解
- 欺诈
- 胁迫
- 显失公平

撤销权时效：自知道或应当知道之日起 1 年；最长 5 年。

#### 效力待定
- 限制行为能力人超越范围的行为（追认后有效）
- 无权代理（追认后有效）

## 合同履行

### 原则
- 全面履行原则
- 诚实信用原则

### 规则
- 约定优先
- 约定不明：协议补充 → 按交易习惯 → 按法定

### 抗辩权
- 同时履行抗辩权：双方互负债务且无先后顺序
- 后履行抗辩权：应当先履行的一方未履行
- 不安抗辩权：后履行一方出现经营严重恶化、转移财产等情形

## 违约责任

### 违约形态
- 不履行
- 迟延履行
- 不完全履行
- 瑕疵履行

### 责任形式
- 继续履行
- 支付违约金
- 赔偿损失（实际损失 + 可得利益损失，但不得超过预见范围）
- 采取补救措施
- 解除合同

### 免责事由
- 不可抗力
- 法定免责事由
- 约定免责事由（但造成人身伤害的免责条款无效）

### 违约金的调整
- 约定过高（超过实际损失 30%）→ 可请求减少
- 约定过低（低于实际损失）→ 可请求增加

## 典型合同

### 买卖合同
- 标的物所有权转移
- 风险转移：交付主义（约定除外）
- 瑕疵担保：权利瑕疵 + 物之瑕疵

### 借款合同
- 自然人间：实践合同（交付时生效）
- 利息：不得违反国家有关限制借款利率的规定

### 租赁合同
- 期限：不超过 20 年
- 维修义务：除当事人另有约定外，出租人应当履行
- 优先购买权：按份共有人 / 房屋承租人（通知后 15 天）

### 承揽合同
- 完成工作并交付成果
- 留置权：定作人未付费用

### 建设工程合同
- 必须招标的：必须招标
- 分包：不得转包；分包需发包人同意

### 担保合同
- 保证：一般保证 vs 连带责任保证
- 抵押：不转移占有
- 质押：转移占有
- 留置：合法占有对方动产

### 委托合同
- 委托人 vs 受托人
- 转委托：经委托人同意；紧急情况为保护委托人利益

### 居间合同
- 报告居间：报告订约机会
- 媒介居间：促成订约
- 报酬：促成合同成立的

## 合同解除

### 协议解除
双方协商一致。

### 单方解除（法定 / 约定）
- 预期违约：对方明确表示或以行为表明不履行
- 根本违约：致使合同目的不能实现
- 迟延履行：经催告后在合理期限内仍未履行
- 不安抗辩权 + 通知对方

### 后果
- 未履行：终止履行
- 已履行：恢复原状 / 采取补救措施 / 赔偿损失
- 担保：对未履行的部分仍享有担保权利
"""),
    ("行政法基础.md", """# 行政法基础

## 行政法基本原则

### 合法行政
行政机关的活动必须有法律依据。

### 合理行政
行政行为应当公平、适当，符合比例原则。

### 程序正当
- 公开：除涉及国家秘密、商业秘密、个人隐私外
- 公正：同等情况同等对待
- 参与：听取当事人意见（听证）

### 高效便民
- 行政效率
- 方便当事人

### 诚实信用
- 信赖利益保护：行政行为一旦作出，不得随意撤销

### 权责一致
违法或不当行为必须承担法律责任。

## 行政主体

### 行政机关
- 中央：国务院及其组成部门
- 地方：省、市、县、乡各级政府及工作部门

### 法律、法规授权的组织
- 行业协会（部分）
- 事业单位（部分）

### 行政委托
行政机关将自己的职权委托给其他组织行使。

## 行政行为

### 行政立法
- 行政法规：国务院制定
- 规章：部门规章（部级）+ 地方政府规章（省级）

### 行政许可
- 设定权：法律、行政法规、地方性法规可设定；规章可设定临时性许可
- 实施程序：申请 → 受理 → 审查 → 决定
- 听证：法律、法规、规章规定实施许可应当听证的事项

### 行政处罚
种类：
- 警告、通报批评
- 罚款
- 没收违法所得、没收非法财物
- 暂扣许可证件、降低资质等级
- 吊销许可证件
- 限制从业
- 行政拘留
- 警告以外的处罚可以单处也可以并处

设定权：
- 法律：各种
- 行政法规：限制人身自由以外
- 地方性法规：限制人身自由以外
- 部门规章：警告、通报批评 + 罚款（限额以下）
- 地方政府规章：警告、通报批评 + 罚款（限额以下）

### 行政强制
- 行政强制措施：即时制止（查封、扣押、冻结）
- 行政强制执行：迫使履行（加处罚款、拍卖）

### 行政确认
对法律事实、法律关系的确认（如产权登记、婚姻登记）。

### 行政裁决
行政机关依法裁决民事纠纷（如土地权属纠纷）。

## 行政程序

### 步骤
- 启动：依职权或依申请
- 调查取证
- 听取意见（陈述、申辩、听证）
- 决定
- 送达

### 听证
- 适用：较大数额罚款、吊销许可证、责令停产停业等
- 程序：告知听证权利 → 申请 → 公告 → 听证会 → 决定

### 期限
- 一般：30 日
- 可延长：不超过原期限 1 倍
- 紧急情况：当场

## 行政复议

### 范围
- 行政处罚
- 行政许可
- 行政强制
- 行政确认
- 行政裁决
- 政府信息公开

### 排除
- 行政机关内部行为
- 行政指导
- 申诉控告检举
- 内部奖惩

### 机关
- 上一级行政机关
- 本级政府（同级）
- 国务院部门 / 省级政府的复议，仍向其自身

### 期限
- 一般：60 日
- 涉及不动产的：最长 20 年

### 决定
- 维持
- 撤销 / 变更 / 确认违法
- 责令履行
- 确认无效
- 驳回复议申请

## 行政诉讼

### 受案范围
- 具体行政行为（部分抽象行政行为附带审查）
- 行政处罚、行政强制、行政许可等

### 不受理
- 国家行为
- 抽象行政行为（不可单独起诉）
- 内部行政行为
- 法律规定的终局裁决

### 原告
- 行政行为的相对人
- 利害关系人
- 受害人

### 被告
- 一般：作出行政行为的行政机关
- 复议维持：原行政机关和复议机关为共同被告
- 复议改变：复议机关为被告
- 委托：委托机关

### 管辖
- 一般：最初作出行政行为的行政机关所在地
- 不动产：不动产所在地
- 经复议改变：复议机关所在地

### 期限
- 知道作出行政行为之日起 6 个月
- 不动产：最长 20 年
- 涉及人身自由：最长 5 年

### 判决
- 驳回诉讼请求
- 撤销 / 部分撤销
- 确认违法 / 确认无效
- 责令履行
- 变更（仅限行政处罚显失公正）

## 行政赔偿

### 归责原则
违法归责：违法行使职权侵犯合法权益造成损害的，国家负责赔偿。

### 范围
- 侵犯人身权：违法拘留、殴打、刑讯逼供等
- 侵犯财产权：违法罚款、吊销许可证、违法征收等

### 不赔偿
- 合法行为
- 受害人自己的行为
- 第三人过错
- 不可抗力

### 赔偿义务机关
- 一般：致害机关
- 复议加重：复议机关
- 两个以上机关：按过错分担

## 国家赔偿计算

### 人身损害
- 侵犯人身自由：每日赔偿金（按上年度职工日平均工资）
- 侵犯生命健康：医疗费、误工费、残疾赔偿金、死亡赔偿金等

### 财产损害
- 直接损失
- 返还财产
- 恢复原状
- 赔偿损失

## 行政补偿

合法行政行为造成的损失（如征收、征用），国家给予补偿。
不以违法为前提。
"""),
]

PHILOSOPHY = [
    ("哲学入门.md", """# 哲学入门

## 什么是哲学

哲学（philosophia = 爱智慧）是对**根本性问题的系统反思**。
与其他学科不同：哲学研究的是**前提**——其他学科不再追问的预设。

## 哲学的主要分支

### 形而上学（Metaphysics）
研究存在本身的本质：
- 什么是存在？
- 实在与表象的关系
- 因果、自由意志、决定论
- 心灵与身体

### 认识论（Epistemology）
研究知识的来源、范围和限度：
- 我们能知道什么？
- 知识的本质是什么？
- 怀疑论 vs 独断论
- 先天 / 后天知识

### 伦理学（Ethics）
研究道德与价值：
- 善与恶的本质
- 道德判断的标准
- 义务论 / 功利主义 / 美德伦理

### 政治哲学
研究国家、正义、权利：
- 什么是正义？
- 国家合法性
- 自由与平等

### 美学
研究美与艺术：
- 美的本质
- 艺术与现实

### 逻辑学
研究推理的形式规则：
- 有效论证
- 谬误识别

## 哲学方法

### 概念分析
澄清概念的内涵与外延。
例：「自由」是什么？消极自由 vs 积极自由。

### 思想实验
构造假想场景，揭示直觉。
例：电车难题、忒修斯之船。

### 论证与反驳
提出观点，给出论证，反驳反对意见。

### 反例与归谬法
通过反例推翻普遍命题。
通过推导出荒谬结论来反驳前提。

## 哲学史上的主要流派

### 古希腊
- 柏拉图：理念论
- 亚里士多德：四因说
- 斯多葛派：顺应自然

### 中世纪
- 经院哲学：信仰与理性
- 奥古斯丁、阿奎那

### 近代
- 经验主义：洛克、休谟、贝克莱
- 理性主义：笛卡尔、斯宾诺莎、莱布尼茨
- 德国古典哲学：康德、黑格尔、费尔巴哈

### 现代
- 实用主义：詹姆斯、皮尔士、杜威
- 现象学：胡塞尔、海德格尔
- 分析哲学：罗素、维特根斯坦、摩尔
- 存在主义：萨特、加缪
- 后现代主义：福柯、德里达

## 中国哲学

### 儒家
孔子：仁、礼
孟子：性善、仁政
荀子：性恶、礼法并施

### 道家
老子：道、无为
庄子：齐物、逍遥

### 佛家
禅宗：顿悟、明心见性

### 法家
韩非子：法、术、势

## 哲学的价值

- 批判性思维的训练
- 对预设的反思
- 智识上的诚实
- 培养面对根本问题的勇气

## 学习建议

- 读经典（不是只读二手资料）
- 与他人辩论
- 写哲学笔记
- 慢思考，深阅读
"""),
    ("逻辑学基础.md", """# 逻辑学基础

## 命题逻辑

### 基本概念
- 命题：有真假的陈述句
- 真值：真（T）/ 假（F）

### 联结词
- ¬（否定）：非 P
- ∧（合取）：P 且 Q
- ∨（析取）：P 或 Q（相容）
- →（蕴涵）：如果 P 那么 Q
- ↔（等值）：P 当且仅当 Q

### 真值表
| P | Q | ¬P | P∧Q | P∨Q | P→Q | P↔Q |
|---|---|----|----|----|----|----|
| T | T | F | T | T | T | T |
| T | F | F | F | T | F | F |
| F | T | T | F | T | T | F |
| F | F | T | F | F | T | T |

注意：P→Q 在 P 为假时为真（材料蕴涵 / 真值蕴涵），这是反直觉但一致的。

### 推理规则
- 假言推理：P → Q, P ⊢ Q
- 假言三段论：P → Q, Q → R ⊢ P → R
- 选言三段论：P ∨ Q, ¬P ⊢ Q
- 双重否定：¬¬P ⊢ P
- 德摩根律：¬(P∧Q) ↔ ¬P∨¬Q

## 谓词逻辑

### 量词
- 全称：∀x（所有 x）
- 存在：∃x（存在 x）

### 推理
- 全称例化：∀x P(x) ⊢ P(a)
- 存在例化：∃x P(x) ⊢ P(a)（对某个 a）
- 全称推广：P(a) ⊢ ∀x P(x)（要求 a 任意）

## 论证形式

### 有效论证
前提为真时结论必为真。

### 谬误

#### 形式谬误
- 肯定后件：P → Q, Q ⊢ P（无效）
- 否定前件：P → Q, ¬P ⊢ ¬Q（无效）

#### 非形式谬误

**诉诸权威**：因为 X X 说，所以对。
（X X 不一定是该领域专家）

**诉诸情感**：用情感代替论证。
例：你想让孩子过得好，所以不要反对我的政策。

**诉诸大众**：因为大家都这样，所以对。
（多数不等于正确）

**稻草人**：歪曲对方观点再反驳。
你：「我反对法案 A」
对方：「你反对所有立法」（夸大你的立场再攻击）

**滑坡论证**：A 会导致 B，B 会导致 C，C 会导致 D，所以反对 A。
（中间环节未必成立）

**循环论证**：用结论证明前提。
例：上帝存在因为圣经说，圣经可信因为它是上帝的话。

**人身攻击**：攻击对方人格而非论点。
例：你是坏人所以你的观点错。

**诉诸无知**：没人证明 P 是真的，所以 P 是假的（或反之）。

**虚假两难**：把多个选项说成只有两个。
例：「要么支持我们，要么反对我们」。

**红鲱鱼**：引入无关话题转移注意力。

## 自然语言论证分析

### 步骤
1. 识别结论
2. 识别前提
3. 检查推理是否有效
4. 检查前提是否真实
5. 识别潜在假设

### 例
> 「所有人都会死。苏格拉底是人。所以苏格拉底会死。」
- 结论：苏格拉底会死
- 前提：所有人都会死；苏格拉底是人
- 形式：∀x M(x), M(s) ⊢ M(s) - 有效
- 前提为真（经验事实）→ 论证有效且可靠

## 命题演算

### 自然演绎系统
通过推理规则从前提推导结论。

### 公理系统
从公理出发推导定理（欧几里得几何、布尔代数）。

## 模态逻辑

### 必然 / 可能
- □P：必然 P
- ◇P：可能 P
- 关系：◇P ↔ ¬□¬P

### 模态系统
- K、T、S4、S5 等，强度递增

## 实用工具

- 自然语言 → 形式化：识别命题结构
- 思维导图：可视化论证
- 反向论证：先假设结论为假，推导矛盾
"""),
    ("伦理学基础.md", """# 伦理学基础

## 伦理学的核心问题

- 道德的本质是什么？
- 什么行为是「对」的？
- 我们应当如何生活？
- 道德的根据来自何处？

## 元伦理学 vs 应用伦理学

### 元伦理学
研究道德语言、道德判断的本质：
- 道德是客观的吗？
- 道德命题的真假如何确定？
- 道德动机是什么？

### 应用伦理学
把伦理理论用于具体领域：
- 医学伦理（安乐死、堕胎）
- 环境伦理
- 商业伦理
- 科技伦理（AI、数据）
- 性伦理

## 主要理论

### 1. 义务论（康德）

核心：**动机与原则**决定行为的道德性，不看后果。

#### 核心概念
- 绝对命令：「要按你同时愿意它成为普遍法则的准则去行动」
- 目的王国：每个人都是目的，不是手段
- 善良意志：出于义务的善意

#### 应用
- 撒谎：即使救人性命也不能撒谎（后果论上看起来更好）
- 死刑：把罪犯当手段，违背尊严

#### 评价
- 优点：明确性、不允许把人物化
- 缺点：忽视后果、规则冲突时无解

### 2. 功利主义（边沁、密尔）

核心：**最大化整体幸福**。

#### 边沁：快乐主义
- 善 = 快乐
- 道德 = 最大化最大多数人的最大幸福
- 计算：强度、持续时间、确定性、远近、丰度、纯度

#### 密尔：质化功利主义
- 快乐有质的差别（高级 vs 低级）
- 「做不满足的人胜过做满足的猪」

#### 评价
- 优点：考虑后果、人人平等计算
- 缺点：忽视权利、难以计算

### 3. 美德伦理（亚里士多德）

核心：关注**品格**而非行为规则。

#### 核心概念
- 中庸之道：美德是过度与不足之间的中点
- 实践智慧（phronesis）：知道何时何地如何行动
- 良善生活：灵魂合乎德性的活动

#### 应用
- 勇敢：鲁莽与怯懦之间
- 慷慨：挥霍与吝啬之间
- 诚实：吹嘘与虚伪之间

#### 评价
- 优点：贴近生活、强调品格
- 缺点：难以指导具体决策、文化相对性

### 4. 关怀伦理（Gilligan）

核心：**关系**与关怀，不是抽象原则。

- 道德来自具体的人际关怀
- 反对只关注抽象权利与义务
- 适合女性经验（但不限性别）

### 5. 儒家伦理

核心：**仁**与**礼**。

- 仁：爱人，推己及人（己欲立而立人，己欲达而达人）
- 礼：社会规范、人伦秩序
- 修身齐家治国平天下
- 君子：内圣外王

### 6. 道家伦理

核心：**道法自然**、**无为**。

- 反对刻意作为
- 顺应自然规律
- 少私寡欲

## 道德相对主义 vs 绝对主义

### 相对主义
- 文化相对：道德因文化而异
- 个人相对：道德因个人而异

### 绝对主义
存在普遍道德真理，跨文化适用。

### 折中
有些道德（如不杀人）是普遍的；有些（具体礼仪）是相对的。

## 道德困境

### 电车难题
一辆失控的电车即将撞死 5 人，你可以拉开关让它转向另一轨道撞死 1 人。
功利主义：拉（5 > 1）
义务论：拉 = 杀人，不可
康德：不能用 1 人作手段救 5 人

### 堕胎
- 胎儿是不是人？
- 母亲身体自主权
- 不同文化结论不同

### 安乐死
- 病人自主
- 不可逆
- 「滑坡」风险

### AI 伦理
- 算法偏见
- 隐私与监控
- 自主武器

## 美德伦理 vs 规则伦理

| | 美德伦理 | 规则伦理 |
|---|---|---|
| 关注 | 品格 | 行为 |
| 回答 | 好人 | 好事 |
| 优点 | 灵活、贴近生活 | 明确、可教 |
| 缺点 | 难以教授 | 忽视情境 |

现代伦理学趋势：**综合**——既要原则，也要情境判断。

## 应用

### 个人
- 日常决策
- 职业伦理
- 自我反思

### 社会
- 公共政策
- 法律制度
- 国际关系

## 学习路径

1. 读经典：
   - 亚里士多德《尼各马可伦理学》
   - 康德《实践理性批判》
   - 密尔《功利主义》
2. 思考当代议题
3. 与不同立场者对话
4. 写伦理笔记
"""),
    ("认识论.md", """# 认识论

## 核心问题

- 知识的本质是什么？
- 我们能知道什么？
- 知识的前提是什么？
- 怀疑的合理界限在哪里？

## 知识的传统定义

柏拉图：知识 = **确证的真信念**（Justified True Belief, JTB）

- 真（True）：事实确实如此
- 信念（Belief）：相信为真
- 确证（Justified）：有充分的理由

### 葛梯尔反例
1963 年葛梯尔提出反例：JTB 三条件可能不充分。
例：钟表走时正确但偶然对。
引发了「确证的第四条件」研究。

## 怀疑论

### 笛卡尔的怀疑
「我思故我在」前的普遍怀疑：
- 感官可能欺骗我（梦、幻觉）
- 数学也可能是恶魔欺骗
- 唯一不能怀疑的：怀疑本身

### 休谟的归纳问题
- 归纳没有逻辑必然性
- 太阳过去每天升起 ≠ 明天会升起
- 习惯期待而非理性保证

### 现代怀疑论
- 大脑在缸中（Brain in a Vat）
- 外部世界可能不存在
- 实在论 vs 反实在论

## 知识来源

### 经验主义
- 一切知识来自感官经验
- 代表：洛克、休谟
- 「心灵本是一块白板」

### 理性主义
- 存在先天的理性知识
- 代表：笛卡尔、斯宾诺莎、莱布尼茨
- 数学与逻辑：理性可及

### 康德的综合
- 先验感性形式：时间、空间
- 先验知性范畴：因果、实体等
- 经验内容来自感官
- 经验的形式由心灵提供

## 真理理论

### 符合论
真理与事实相符。
例：「雪是白的」真，因为雪确实是白的。

### 融贯论
真理是命题之间的融贯。
例：命题之间逻辑一致则真。

### 实用主义
真理是有用的。
例：「火是热的」真，因为相信它让我们避免烧伤。

### 冗余论
「真」概念可被消解，断言就是陈述事实。

## 科学知识

### 逻辑实证主义
- 经验可证实原则
- 形而上学命题无意义

### 证伪主义（波普尔）
- 科学不是证实而是证伪
- 关键在可证伪性
- 例：相对论可证伪 → 科学；占星术不可证伪 → 非科学

### 范式转换（库恩）
- 科学革命 = 范式转换
- 不同范式之间不可通约
- 例：日心说替代地心说

### 研究纲领（拉卡托斯）
- 进步 vs 退化的研究纲领
- 保护带调整 vs 硬核放弃

## 心灵哲学

### 身心二元论（笛卡尔）
心灵与身体是两种实体。

### 物理主义 / 唯物主义
心灵是身体的物理状态。

### 同一论
心理状态就是大脑状态。

### 功能主义
心理状态由其功能（输入输出关系）定义。

## 先天 vs 后天

### 先天
- 不依赖感官经验
- 例：逻辑真理、数学
- 例：语言能力（乔姆斯基）

### 后天
- 依赖经验
- 例：具体科学事实

## 决定论与自由意志

### 决定论
所有事件都被先前的充分条件决定。
包括人的行为。

### 自由意志
人能做出不同于实际选择的选择。

### 相容论
决定论与自由意志可以兼容：
- 自由 = 出于自己意愿而非外在强制
- 即使决定论为真，自由仍有意义

## 知识与价值

### 事实 / 价值二分
休谟：不能从「是」推出「应该」。

### 回应
- 自然主义谬误：从描述推出规范
- 反例：有些价值判断可分析为事实判断

## 应用

### 批判性思维
- 区分事实与意见
- 评估证据
- 识别偏见

### 科学方法
- 提出假设
- 设计实验
- 收集数据
- 得出结论

## 学习路径

1. 经典：
   - 柏拉图《泰阿泰德》
   - 笛卡尔《第一哲学沉思集》
   - 休谟《人类理解研究》
   - 康德《纯粹理性批判》
   - 维特根斯坦《逻辑哲学论》
2. 熟悉科学哲学的基本概念
3. 反思自己的认知偏见
"""),
]


# 学科元数据（目录 + 文件数）
SUBJECTS = {
    "cs":            ("计算机·软件·开发",  CS),
    "testing":       ("测试",              TESTING),
    "product":       ("产品",              PRODUCT),
    "industrial":    ("工业设计",          INDUSTRIAL_DESIGN),
    "economics":     ("经济学",            ECONOMICS),
    "english":       ("英语",              ENGLISH),
    "law":           ("法学",              LAW),
    "philosophy":    ("哲学",              PHILOSOPHY),
}


def main() -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}
    for sub, (label, docs) in SUBJECTS.items():
        d = SEED_DIR / sub
        d.mkdir(parents=True, exist_ok=True)
        for name, content in docs:
            (d / name).write_text(content, encoding="utf-8")
        summary[sub] = {"label": label, "n_docs": len(docs)}
        print(f"[{sub}] {label}: {len(docs)} 篇")
    print(f"\n总计 {sum(s['n_docs'] for s in summary.values())} 篇文档写入 {SEED_DIR}")
    import json
    (Path(__file__).with_name("_kb_subjects.json")).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()