# MySQL 索引原理

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
