# 规模化检索延迟实测（优化后：内存向量矩阵 / 真实 VectorStore.search 路径）

命令: `python bench/scale_probe.py --sizes 5000,20000,50000 --queries 10 --dim 1024 --index memory`

环境: Python 3.13.14, 向量维度 1024, 逻辑核 16, 索引模式 memory

| chunk 数 | P50 | P95 | 最小 | 最大 | 索引类型 | 索引内存 | 冷装载 | 灌数据耗时 |
|---|---|---|---|---|---|---|---|---|
| 5,000 | 0.6ms | 0.7ms | 0.4ms | 0.7ms | exact | 19.53MB | 107.5ms | 2.2s |
| 20,000 | 2.6ms | 2.7ms | 2.4ms | 3.0ms | exact | 78.12MB | 480.3ms | 9.3s |
| 50,000 | 6.0ms | 6.1ms | 5.8ms | 6.2ms | exact | 195.31MB | 1244.2ms | 23.6s |
