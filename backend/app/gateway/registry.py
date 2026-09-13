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

    id: str                       # 对外模型名（前端展示 / 路由 / 用户偏好都用它，全局唯一）
    label: str                    # 展示名
    provider: str                 # deepseek / aliyun / siliconflow ...
    base_url: str                 # OpenAI 兼容接入点
    remote_model: str = ""        # 实际发给服务商的 model 字段；空 = 与 id 相同
    api_style: str = "chat"       # chat | responses
    context_window: int = 64_000
    in_price: float = 1.0         # 元 / 百万 输入 token
    out_price: float = 2.0        # 元 / 百万 输出 token
    tier: str = TIER_STANDARD
    supports_stream: bool = True
    supports_thinking: bool = False   # 是否支持「思考模式」开关
    tags: Tuple[str, ...] = field(default_factory=tuple)
    enabled: bool = True
    verified: bool = False        # 是否经真实调用验证过可用（bench/probe_models.py）

    @property
    def model_name(self) -> str:
        """发给服务商的真实模型名。"""
        return self.remote_model or self.id

    def to_public(self) -> Dict[str, object]:
        """脱敏后的对外描述（不含任何凭据信息）。"""
        return {
            "id": self.id, "label": self.label, "provider": self.provider,
            "context_window": self.context_window,
            "price_per_million": {"input": self.in_price, "output": self.out_price},
            "tier": self.tier, "tags": list(self.tags),
            "supports_stream": self.supports_stream,
            "supports_thinking": self.supports_thinking,
            "enabled": self.enabled,
            "verified": self.verified,
        }


def _base(provider: str, default: str) -> str:
    """provider 接入点：默认值可被配置覆盖（指向独享/私有化端点）。"""
    from app.config import settings
    return settings.provider_base_url(provider, default)


def _enabled(provider: str) -> bool:
    """该 provider 是否有平台托管 key。无 key 时仍可 BYOK 使用，但在目录里标记为不可直接用。"""
    from app.config import settings
    return bool(settings.provider_key(provider))


def _spec(*, id: str, label: str, provider: str, base_url: str,  # noqa: A002
          remote_model: str = "", api_style: str = "chat", context_window: int = 64_000,
          in_price: float = 1.0, out_price: float = 2.0, tier: str = TIER_STANDARD,
          supports_stream: bool = True, supports_thinking: bool = False,
          verified: bool = False, tags: Tuple[str, ...] = ()) -> ModelSpec:
    return ModelSpec(
        id=id, label=label, provider=provider,
        base_url=_base(provider, base_url), remote_model=remote_model,
        api_style=api_style, context_window=context_window,
        in_price=in_price, out_price=out_price, tier=tier,
        supports_stream=supports_stream, supports_thinking=supports_thinking,
        tags=tags, enabled=_enabled(provider), verified=verified,
    )


# 计价为「元 / 百万 token」。
# ⚠️ 诚实边界：只有 DeepSeek 官方价格是查证过的（v4-flash 未命中 ¥1/¥2、v4-pro ¥3/¥6）。
# 其余为**估算值**（取同档位公开报价），用于成本量级判断与积分换算；
# 真实账单以服务商后台为准。token 数来自 API 返回 usage，是精确值。
#
# verified=True 表示该 id 经 bench/probe_models.py 真实调用验证可用。
# 这一步不能省：聚合端点 /models 会列出 249 个 id，但**大部分未对本账号开通**，
# 未开通的调用返回 400 "The product is not activated"。
# 只按目录写白名单，路由会把请求打到必然失败的模型上——降级链在起跑线就断了。
MODELS: Tuple[ModelSpec, ...] = (
    # ── DeepSeek 官方直连（/models 实际只暴露这两个 id）──
    _spec(id="deepseek-flash", label="DeepSeek Flash（官方直连）", provider="deepseek",
          base_url="https://api.deepseek.com/v1", api_style="chat",
          context_window=1_000_000, in_price=1.0, out_price=2.0, tier=TIER_CHEAP,
          supports_thinking=True, verified=True,
          tags=("官方直连", "低延迟", "1M 上下文")),
    _spec(id="deepseek-v4-pro", label="DeepSeek V4 Pro（官方直连）", provider="deepseek",
          base_url="https://api.deepseek.com/v1", api_style="chat",
          context_window=1_000_000, in_price=3.0, out_price=6.0, tier=TIER_STRONG,
          supports_thinking=True, verified=True,
          tags=("官方直连", "长推理", "报告")),

    # ── 阿里云 MaaS 聚合端点：同模型异端点（容量故障转移的关键）──
    _spec(id="aliyun/deepseek-v4-flash", label="DeepSeek V4 Flash（阿里云托管）",
          provider="aliyun", remote_model="deepseek-v4-flash",
          base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_style="chat",
          context_window=128_000, in_price=1.0, out_price=2.0, tier=TIER_CHEAP,
          supports_thinking=True, verified=True,
          tags=("聚合端点", "同模型异端点", "容量转移")),
    _spec(id="aliyun/deepseek-v4-pro", label="DeepSeek V4 Pro（阿里云托管）",
          provider="aliyun", remote_model="deepseek-v4-pro",
          base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_style="chat",
          context_window=128_000, in_price=3.0, out_price=6.0, tier=TIER_STRONG,
          supports_thinking=True, verified=True,
          tags=("聚合端点", "同模型异端点", "容量转移")),
    _spec(id="qwen3.8-flash", label="通义 Qwen3.8 Flash", provider="aliyun",
          base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_style="chat",
          context_window=128_000, in_price=0.3, out_price=1.2, tier=TIER_CHEAP,
          verified=True, tags=("聚合端点", "极低成本", "高并发")),
    _spec(id="qwen3.8-max", label="通义 Qwen3.8 Max", provider="aliyun",
          base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_style="chat",
          context_window=128_000, in_price=2.4, out_price=9.6, tier=TIER_STRONG,
          verified=True, tags=("聚合端点", "中文强", "报告")),
    _spec(id="qwen3.8-27b", label="通义 Qwen3.8 27B（小尺寸）", provider="aliyun",
          base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_style="chat",
          context_window=128_000, in_price=0.4, out_price=1.6, tier=TIER_CHEAP,
          verified=True, tags=("聚合端点", "低延迟", "结构化抽取")),
    _spec(id="kimi-k3", label="Kimi K3", provider="aliyun",
          base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_style="chat",
          context_window=256_000, in_price=2.0, out_price=8.0, tier=TIER_STRONG,
          verified=True, tags=("聚合端点", "跨厂商", "长上下文")),
    _spec(id="glm-5.2", label="智谱 GLM-5.2", provider="aliyun",
          base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_style="chat",
          context_window=128_000, in_price=0.5, out_price=2.0, tier=TIER_STANDARD,
          verified=True, tags=("聚合端点", "跨厂商", "性价比")),

    # ── SiliconFlow：第三个部署点 ──
    _spec(id="sf/deepseek-v4-flash", label="DeepSeek V4 Flash（SiliconFlow）",
          provider="siliconflow", remote_model="deepseek-ai/DeepSeek-V4-Flash",
          base_url="https://api.siliconflow.cn/v1", api_style="chat",
          context_window=128_000, in_price=1.0, out_price=2.0, tier=TIER_CHEAP,
          supports_thinking=True, verified=True,
          tags=("第三方托管", "同模型异端点", "容量转移")),
    _spec(id="sf/deepseek-v4-pro", label="DeepSeek V4 Pro（SiliconFlow）",
          provider="siliconflow", remote_model="deepseek-ai/DeepSeek-V4-Pro",
          base_url="https://api.siliconflow.cn/v1", api_style="chat",
          context_window=128_000, in_price=3.0, out_price=6.0, tier=TIER_STRONG,
          supports_thinking=True, verified=True,
          tags=("第三方托管", "同模型异端点", "容量转移")),
)

_BY_ID: Dict[str, ModelSpec] = {m.id: m for m in MODELS}

# 经实测**不可用**的 id 黑名单（端点目录里有，但本账号未开通）。
# 保留在代码里作为证据：路由若命中它们会得到 400，必须有意识地排除。
KNOWN_UNACTIVATED = (
    "vanchin/deepseek-v4-pro", "vanchin/deepseek-v3.2-think",
    "ZHIPU/GLM-5.3", "ZHIPU/GLM-5.3-Flash",
    "MiniMax/MiniMax-M3", "stepfun/step-3.7-flash",
)


def provider_of(model_id: Optional[str]) -> str:
    """模型 → 所属 provider（用于取对应凭据与接入点）。"""
    spec = get_model(model_id)
    return spec.provider if spec else ""


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
