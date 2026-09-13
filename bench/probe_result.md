# 外部依赖探活与延迟基线（真实调用）

时间：2026-09-13 13:06:59

- 成本护栏上限：¥30.0，本轮开始前已用：¥0.0000
- DeepSeek key：sk-7d480…d968（长度 35）
- Aliyun key：sk-ws-H.…VJsQ（长度 115）
- Embedding：BAAI/bge-m3 @ https://api.siliconflow.cn/v1
- Rerank：BAAI/bge-reranker-v2-m3 @ https://api.siliconflow.cn/v1

## 各端点可用模型（/models）

| provider | base_url | 结果 |
|---|---|---|
| deepseek | `https://api.deepseek.com/v1` | ✅ 2 个：deepseek-flash, deepseek-v4-pro |
| aliyun | `https://llm-cfwa544aykj7ljbo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` | ✅ 249 个：qwen3.8-max-0902, qwen3.7-text-embedding-flash, qwen3.7-text-rerank, ZHIPU/GLM-5.3-Flash, stepfun/step-3.7-flash, vanchin/deepseek-v4-pro, unisound/unisound-u2, vanchin/deepseek-v4-pro-0813, qwen3.8-flash, kimi-k3, qwen3.8-27b, ZHIPU/GLM-5.3, deepseek-v4-pro-0813, qwen3.8-2.4t-a95b … |
| siliconflow | `https://api.siliconflow.cn/v1` | ✅ 94 个：tencent/Hy4-preview, zai-org/GLM-5.3, deepseek-ai/DeepSeek-V4-Flash, meituan-longcat/LongCat-2.0, zai-org/GLM-5.2, moonshotai/Kimi-K2.7-Code, deepseek-ai/DeepSeek-V4-Pro, Qwen/Qwen3.8-27B, Pro/moonshotai/Kimi-K2.6, Pro/zai-org/GLM-5.1, Tongyi-MAI/Z-Image-Turbo, Tongyi-MAI/Z-Image, baidu/ERNIE-Image-Turbo, deepseek-ai/DeepSeek-V3.2 … |

## 探活结果

| 项目 | 结果 | 模型/端点 | 指标 | 延迟 | 备注 |
|---|---|---|---|---|---|
| embedding 探活 | ✅ | BAAI/bge-m3 | 维度 1024 | 210.0 ms |  |
| embedding 批量 32 条（冷） | ✅ | - | 32 条 | 429.9 ms（13.4 ms/条） | - |
| embedding 批量 32 条（缓存命中） | ✅ | - | 32 条 | 0.0 ms | 加速 42990.0× |
| embedding 单条 | ✅ | - | 1 条 | 215.0 ms | - |
| embedding 语义判别 | ✅ | - | 相关 0.7251 / 无关 0.3036 | 差值 0.4215 | 相关句更接近，语义有效 |
| rerank 探活 | ✅ | BAAI/bge-reranker-v2-m3 | 打分 [0.9888, 0.0] | 182.0 ms | 相关文档得分高于无关文档 |
| LLM deepseek-flash | ✅ | https://api.deepseek.com/v1 | JSON 解析成功 | 3262.1 ms | {"ok": true, "topic": "RAG"} |
| LLM deepseek-v4-pro | ✅ | https://api.deepseek.com/v1 | JSON 解析成功 | 1244.0 ms | {"ok": true, "topic": "RAG"} |
| LLM qwen3.8-flash | ✅ | https://llm-cfwa544aykj7ljbo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1 | JSON 解析成功 | 1325.7 ms | {"ok": true, "topic": "RAG"} |
| LLM qwen3.8-max-0902 | ✅ | https://llm-cfwa544aykj7ljbo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1 | JSON 解析成功 | 1680.1 ms | {"ok": true, "topic": "RAG"} |
| LLM kimi-k3 | ✅ | https://llm-cfwa544aykj7ljbo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1 | JSON 解析成功 | 2268.9 ms | {"ok": true, "topic": "RAG"} |
| LLM ZHIPU/GLM-5.3-Flash | ❌ | - | - | - | LLMError: Error code: 400 - {'error': {'message': 'The product is not activated, please confirm that |
| LLM vanchin/deepseek-v4-pro | ❌ | - | - | - | LLMError: Error code: 400 - {'error': {'message': 'The product is not activated, please confirm that |
| LLM deepseek-ai/DeepSeek-V4-Flash | ✅ | https://api.siliconflow.cn/v1 | JSON 解析成功 | 1079.5 ms | {"ok": true, "topic": "RAG"} |
| LLM Qwen/Qwen3.8-27B | ✅ | https://api.siliconflow.cn/v1 | JSON 解析成功 | 2464.9 ms | {"ok": true, "topic": "RAG"} |
| LLM 流式（TTFT/总时长） | ✅ | - | 首字 0 ms | 总计 1168.4 ms / 0 字 | 吞吐 0.0 字/秒 |
| **本轮探活合计** | - | - | 1010 tokens | ¥0.00288 | {"deepseek-flash": {"calls": 2, "in": 98, "out": 100}, "deepseek-v4-pro": {"calls": 1, "in": 110, "out": 61}, "qwen3.8-flash": {"calls": 1, "in": 80, "out": 61}, "qwen3.8-max-0902": {"calls": 1, "in": 80, "out": 50}, "kimi-k3": {"calls": 1, "in": 122, "out": 74}, "deepseek-ai/DeepSeek-V4-Flash": {"calls": 1, "in": 31, "out": 19}, "Qwen/Qwen3.8-27B": {"calls": 1, "in": 80, "out": 44}} |

## 成本

- 本轮累计花费：¥0.00288
- 剩余额度：¥29.99712
- 被护栏拒绝次数：0

```json
{
 "listing": {
  "deepseek": {
   "ok": true,
   "count": 2,
   "ids": [
    "deepseek-flash",
    "deepseek-v4-pro"
   ]
  },
  "aliyun": {
   "ok": true,
   "count": 249,
   "ids": [
    "qwen3.8-max-0902",
    "qwen3.7-text-embedding-flash",
    "qwen3.7-text-rerank",
    "ZHIPU/GLM-5.3-Flash",
    "stepfun/step-3.7-flash",
    "vanchin/deepseek-v4-pro",
    "unisound/unisound-u2",
    "vanchin/deepseek-v4-pro-0813",
    "qwen3.8-flash",
    "kimi-k3",
    "qwen3.8-27b",
    "ZHIPU/GLM-5.3",
    "deepseek-v4-pro-0813",
    "qwen3.8-2.4t-a95b",
    "qwen-image-3.0-pro",
    "qwen-image-3.0",
    "qwen3.8-max",
    "deepseek-v4-flash-0731",
    "qwen-audio-3.0-asr-flash",
    "qwen3.7-flash-2026-07-15",
    "qwen3.7-flash",
    "kimi/kimi-k3",
    "qwen3.7-text-embedding",
    "qwen-audio-3.0-realtime-flash",
    "qwen-audio-3.0-realtime-plus",
    "glm-5.2-fast-preview",
    "kimi/kimi-k2.7-code-highspeed",
    "xiaomi/mimo-v2.5-pro",
    "MiniMax/MiniMax-M3",
    "ZHIPU/GLM-5.2",
    "qwen-image-2.0-pro-2026-06-22",
    "test-sre-gpu-auto-handle",
    "fun-asr-flash-2026-06-15",
    "glm-5.2",
    "kimi/kimi-k2.7-code",
    "kimi-k2.7-code",
    "sre-gpu-auto-handle",
    "qwen3.7-max-2026-06-08",
    "qwen3.5-ocr",
    "qwen3.7-plus-2026-05-26",
    "qwen3.7-plus",
    "qwen3.7-max-2026-05-17",
    "qwen3.7-max-preview",
    "ZHIPU/GLM-5",
    "qwen3.7-max-2026-05-20",
    "qwen3.7-max",
    "qwen3.5-livetranslate-flash-realtime-2026-05-19",
    "qwen3.5-livetranslate-flash-realtime",
    "ZHIPU/GLM-5.1",
    "kimi/kimi-k2.6",
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "qwen-image-2.0-pro-2026-04-22",
    "qwen3.5-plus-2026-04-20",
    "qwen3.6-27b",
    "kimi-k2.6",
    "qwen3.6-max-preview",
    "qwen3.6-35b-a3b",
    "qwen3.6-flash-2026-04-16",
    "qwen3.6-flash",
    "glm-5.1",
    "vanchin/deepseek-v3.1-terminus",
    "vanchin/deepseek-v3",
    "vanchin/deepseek-r1",
    "vanchin/deepseek-ocr",
    "vanchin/deepseek-v3.2-think",
    "qwen3.5-omni-plus-realtime-2026-03-15",
    "qwen3.5-omni-plus-realtime",
    "qwen3.5-omni-plus-2026-03-15",
    "qwen3.5-omni-plus",
    "qwen3.5-omni-flash-realtime-2026-03-15",
    "qwen3.5-omni-flash-realtime",
    "qwen3.5-omni-flash-2026-03-15",
    "qwen3.5-omni-flash",
    "qwen3.6-plus-2026-04-02",
    "qwen3.6-plus",
    "wan2.7-image-pro",
    "wan2.7-image",
    "MiniMax/MiniMax-M2.7",
    "MiniMax/speech-2.8-hd",
    "MiniMax/speech-2.8-turbo",
    "MiniMax/speech-02-turbo",
    "MiniMax/speech-02-hd",
    "qwen-deep-research-2025-12-15",
    "qwen-image-2.0-2026-03-03",
    "qwen-image-2.0-pro",
    "qwen-image-2.0-pro-2026-03-03",
    "qwen-image-2.0",
    "qwen3-asr-flash-2026-02-10",
    "glm-5",
    "qwen-flash-character-2026-02-26",
    "MiniMax-M2.5",
    "qwen3.5-flash-2026-02-23",
    "qwen3.5-flash",
    "qwen3.5-122b-a10b",
    "qwen3.5-35b-a3b",
    "qwen3.5-27b",
    "qwen3-coder-next",
    "qwen3.5-397b-a17b",
    "qwen3.5-plus-2026-02-15",
    "qwen3.5-plus",
    "qwen3-asr-flash-realtime-2026-02-10",
    "MiniMax/MiniMax-M2.1",
    "MiniMax/MiniMax-M2.5",
    "qwen3-tts-vd-2026-01-26",
    "qwen3-tts-instruct-flash-2026-01-26",
    "qwen3-tts-instruct-flash",
    "qwen3-tts-vc-2026-01-22",
    "glm-4.7",
    "qwen3-max",
    "qwen3-tts-instruct-flash-realtime-2026-01-22",
    "qwen3-tts-instruct-flash-realtime",
    "qwen3-tts-vd-realtime-2026-01-15",
    "kimi-k2.5",
    "tongyi-xiaomi-analysis-flash",
    "tongyi-xiaomi-analysis-pro",
    "siliconflow/deepseek-v3.2",
    "siliconflow/deepseek-v3.1-terminus",
    "siliconflow/deepseek-v3-0324",
    "siliconflow/deepseek-r1-0528",
    "MiniMax-M2.1",
    "qwen3-vl-flash-2026-01-22",
    "qwen3-max-2026-01-23",
    "qwen3-tts-vc-realtime-2026-01-15",
    "qwen-image-edit-max-2026-01-16",
    "qwen-image-edit-max",
    "qwen-image-plus-2026-01-09",
    "qwen-flash-character",
    "qwen-image-max-2025-12-30",
    "qwen-image-max",
    "qwen-flash",
    "z-image-turbo",
    "qwen3-vl-plus-2025-12-19",

```
