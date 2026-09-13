# 规模化检索延迟实测（优化后：内存向量矩阵 / 真实 VectorStore.search 路径）

命令: `python bench/scale_probe.py --sizes 100000 --queries 10 --dim 1024 --index hnsw`

环境: Python 3.13.14, 向量维度 1024, 逻辑核 16, 索引模式 hnsw

| chunk 数 | P50 | P95 | 最小 | 最大 | 索引类型 | 索引内存 | 冷装载 | 灌数据耗时 |
|---|---|---|---|---|---|---|---|---|
| 100,000 | 1.4ms | 1.6ms | 1.3ms | 1.6ms | hnsw | 390.62MB | 104804.2ms | 46.0s |
