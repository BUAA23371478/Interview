# 模型可用性探测（真实调用）

时间：2026-09-13 13:07:47

## deepseek `https://api.deepseek.com/v1`

| 模型 | 可用 | 延迟 | 回复 | 判定 |
|---|---|---|---|---|
| `deepseek-flash` | ✅ | 1560.0 ms | 正常 | - |
| `deepseek-v4-pro` | ✅ | 608.6 ms | 正常 | - |

## aliyun `https://llm-cfwa544aykj7ljbo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`

| 模型 | 可用 | 延迟 | 回复 | 判定 |
|---|---|---|---|---|
| `deepseek-v4-flash` | ✅ | 903.4 ms | 正常 | - |
| `deepseek-v4-pro` | ✅ | 930.6 ms | 正常 | - |
| `vanchin/deepseek-v4-pro` | ❌ | 589.2 ms |  | not_activated |
| `vanchin/deepseek-v3.2-think` | ❌ | 712.7 ms |  | not_activated |
| `qwen3.8-flash` | ✅ | 498.3 ms | 正常 | - |
| `qwen3.8-max` | ✅ | 380.3 ms | 正常 | - |
| `qwen3.8-max-0902` | ✅ | 423.0 ms | 正常 | - |
| `qwen3.8-27b` | ✅ | 220.1 ms | 正常 | - |
| `qwen3.7-plus` | ✅ | 1075.1 ms | 正常 | - |
| `qwen3.7-flash` | ✅ | 380.2 ms | 正常 | - |
| `qwen3.7-max` | ✅ | 967.4 ms | 正常 | - |
| `kimi-k3` | ✅ | 917.5 ms | 正常 | - |
| `kimi-k2.6` | ✅ | 513.0 ms | 正常 | - |
| `ZHIPU/GLM-5.3` | ❌ | 465.9 ms |  | not_activated |
| `ZHIPU/GLM-5.3-Flash` | ❌ | 609.1 ms |  | not_activated |
| `glm-5.2` | ✅ | 518.8 ms | 正常 | - |
| `glm-5` | ✅ | 724.6 ms | 正常 | - |
| `MiniMax/MiniMax-M3` | ❌ | 189.6 ms |  | not_activated |
| `stepfun/step-3.7-flash` | ❌ | 659.1 ms |  | not_activated |

## siliconflow `https://api.siliconflow.cn/v1`

| 模型 | 可用 | 延迟 | 回复 | 判定 |
|---|---|---|---|---|
| `deepseek-ai/DeepSeek-V4-Flash` | ✅ | 939.4 ms | 正常 | - |
| `deepseek-ai/DeepSeek-V4-Pro` | ✅ | 733.2 ms | 正常 | - |
| `Qwen/Qwen3.8-27B` | ✅ | 548.0 ms | 正常 | - |
| `zai-org/GLM-5.3` | ✅ | 1887.6 ms | 正常 | - |

## 流式输出形态实验（思考模式的影响）

### deepseek-flash

- 关闭思考 + 256 token：正文 69 字 / 思维链 0 字 / 正文首字 782.7 ms / 总 1083.3 ms / 预览「RAG（检索增强生成）就是让大模型在回答问题前，先去外部知识库检索相关资料，再基于检索到的内容生成答案，从而减少幻觉、提」
- 默认(思考开启) + 64 token：正文 0 字 / 思维链 145 字 / 正文首字 None ms / 总 1371.5 ms
- 默认(思考开启) + 768 token：正文 58 字 / 思维链 211 字 / 正文首字 987.9 ms / 总 1082.6 ms / 预览「RAG（检索增强生成）是一种让大模型在生成回答前先从外部知识库检索相关信息并据此作答，从而提升准确性和时效性的技术。」

### deepseek-v4-pro

- 关闭思考 + 256 token：正文 70 字 / 思维链 0 字 / 正文首字 364.0 ms / 总 945.6 ms / 预览「RAG（检索增强生成）是一种在生成模型作答前，先从外部知识库中检索相关信息并作为上下文注入，从而提升回答准确性、时效性与」
- 默认(思考开启) + 64 token：正文 0 字 / 思维链 139 字 / 正文首字 None ms / 总 1108.8 ms
- 默认(思考开启) + 768 token：正文 60 字 / 思维链 152 字 / 正文首字 1688.0 ms / 总 2027.7 ms / 预览「RAG（检索增强生成）是一种先从外部知识库检索相关信息，再把检索结果作为上下文交给大语言模型生成更准确、可靠回答的技术。」


**本轮花费 ¥0.00288**（上限 ¥30.0）
