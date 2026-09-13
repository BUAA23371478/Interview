# Redis 数据结构

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
