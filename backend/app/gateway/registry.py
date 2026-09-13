"""模型注册表：平台支持的多模型目录（统一 OpenAI 兼容调用面）。

为什么需要一层注册表
--------------------
初版只有 `LLM_MODEL` / `LLM_BASE_URL` 两个全局配置，语义是「一个平台一个模型」：
换模型要改环境变量重启，不同任务无法用不同模型，价格也无从计算。

注册表把「模型」变成一等公民：每个模型自带 provider、接入点、调用风格、
上下文窗口、计价与能力标签。上层只按 **task 语义** 申请模型，
不关心背后是哪家、走 chat 还是 responses。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# 计费单位：元 / 百万 token（与 observability.PRICING 对齐）
TIER_CHEAP = "cheap"
TIER_STANDARD = "standard"
TIER_STRONG = "strong"


@dataclass(frozen=True)
class ModelSpec:
    """一个可调用模型的完整描述。"""

    id: str                       # 对外模型名（也是传给 OpenAI SDK 的 model）
    label: str                    # 展示名
    provider: str                 # deepseek / aliyun / openai ...
    base_url: str                 # OpenAI 兼容接入点
    api_style: str = "chat"       # chat | responses
    context_window: int = 64_000
    in_price: float = 1.0         # 元 / 百万 输入 token
    out_price: float = 2.0        # 元 / 百万 输出 token
    tier: str = TIER_STANDARD
    supports_stream: bool = True
    tags: Tuple[str, ...] = field(default_factory=tuple)
    enabled: bool = True

    def to_public(self) -> Dict[str, object]:
        """脱敏后的对外描述（不含 base_url 之外的任何凭据信息）。"""
        return {
            "id": self.id, "label": self.label, "provider": self.provider,
            "context_window": self.context_window,
            "price_per_million": {"input": self.in_price, "output": self.out_price},
            "tier": self.tier, "tags": list(self.tags),
            "supports_stream": self.supports_stream,
        }


MODELS: Tuple[ModelSpec, ...] = (
    ModelSpec(
        id="deepseek-chat", label="DeepSeek V3（通用）", provider="deepseek",
        base_url="https://api.deepseek.com/v1", api_style="chat",
        context_window=64_000, in_price=1.0, out_price=2.0, tier=TIER_STANDARD,
        tags=("中文强", "性价比", "工具调用"),
    ),
    ModelSpec(
        id="deepseek-reasoner", label="DeepSeek R1（推理）", provider="deepseek",
        base_url="https://api.deepseek.com/v1", api_style="chat",
        context_window=64_000, in_price=4.0, out_price=16.0, tier=TIER_STRONG,
        tags=("长推理", "评估", "报告"),
    ),
    ModelSpec(
        id="deepseek-v4-flash", label="DeepSeek V4 Flash（低延迟）", provider="deepseek",
        base_url="https://api.deepseek.com", api_style="responses",
        context_window=128_000, in_price=0.5, out_price=1.5, tier=TIER_CHEAP,
        tags=("低延迟", "结构化抽取"),
    ),
    ModelSpec(
        id="qwen-plus", label="通义千问 Plus", provider="aliyun",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_style="chat",
        context_window=128_000, in_price=0.8, out_price=2.0, tier=TIER_STANDARD,
        tags=("中文强", "长上下文"),
    ),
    ModelSpec(
        id="qwen-turbo", label="通义千问 Turbo", provider="aliyun",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_style="chat",
        context_window=128_000, in_price=0.3, out_price=0.6, tier=TIER_CHEAP,
        tags=("极低成本",),
    ),
)

_BY_ID: Dict[str, ModelSpec] = {m.id: m for m in MODELS}


def get_model(model_id: Optional[str]) -> Optional[ModelSpec]:
    """按 id 取模型；支持前缀模糊匹配（如 "deepseek-chat-0324" → deepseek-chat）。"""
    if not model_id:
        return None
    mid = model_id.strip()
    if mid in _BY_ID:
        return _BY_ID[mid]
    for key, spec in _BY_ID.items():
        if mid.startswith(key):
            return spec
    return None


def list_models(*, enabled_only: bool = True) -> List[ModelSpec]:
    return [m for m in MODELS if m.enabled or not enabled_only]


def default_model_id() -> str:
    return MODELS[0].id
