# SQL 事务隔离级别

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
