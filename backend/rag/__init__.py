"""RAG 模块 —— 文档解析、向量化存储、语义检索。

提供:
- DocumentLoader: 多格式文档解析（PDF/MD/TXT）
- VectorStore: Chroma 向量数据库的封装（分块 + Embedding + 检索）
- EmbeddingClient: 文本向量化客户端（DeepSeek Embedding API）
"""
