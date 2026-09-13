# 规模化检索延迟实测（优化后：内存向量矩阵 / 真实 VectorStore.search 路径）

命令: `python bench/scale_probe.py --sizes 500,5000,20000 --queries 10 --dim 1024 --index auto`

环境: Python 3.13.14, 向量维度 1024, 逻辑核 16, 索引模式 auto

| chunk 数 | P50 | P95 | 最小 | 最大 | 索引类型 | 索引内存 | 冷装载 | 灌数据耗时 |
|---|---|---|---|---|---|---|---|---|
| 500 | 0.2ms | 0.3ms | 0.2ms | 0.5ms | exact | 1.95MB | 11.0ms | 0.2s |
| 5,000 | 0.7ms | 1.0ms | 0.5ms | 1.1ms | exact | 19.53MB | 113.0ms | 2.3s |
| 20,000 | 1.2ms | 1.3ms | 1.1ms | 1.4ms | hnsw | 78.12MB | 10471.9ms | 8.9s |
