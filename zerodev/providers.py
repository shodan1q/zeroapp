"""LLM provider registry.

Central metadata for every supported AI provider. Claude talks to the
official Anthropic SDK; every other vendor is integrated through its
officially documented OpenAI-compatible endpoint, so one HTTP client
implementation (in ``zerodev/llm.py``) covers them all.

Adding a provider = adding one ``ProviderSpec`` entry here, plus the three
optional env fields (``{id}_api_key`` / ``{id}_model`` / ``{id}_base_url``)
in ``zerodev/config.py``. The settings API and the Dashboard UI both render
from this registry, so no further wiring is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderSpec:
    """Static description of one AI provider."""

    id: str
    label: str
    description: str
    kind: str  # "anthropic" | "openai_compat"
    default_base_url: str
    default_model: str
    suggested_models: tuple[str, ...] = field(default_factory=tuple)
    requires_api_key: bool = True
    # Request parameter name for the output-token cap on this endpoint.
    max_tokens_param: str = "max_tokens"
    key_hint: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    spec.id: spec
    for spec in (
        ProviderSpec(
            id="claude",
            label="Claude (Anthropic)",
            description="官方 Anthropic SDK，支持 API Key 或 Pro/Max 订阅 OAuth Token",
            kind="anthropic",
            default_base_url="",
            default_model="claude-opus-4-8",
            suggested_models=(
                "claude-opus-4-8",
                "claude-sonnet-4-6",
                "claude-haiku-4-5",
            ),
            key_hint="sk-ant-... 或 claude setup-token 生成的订阅 token",
        ),
        ProviderSpec(
            id="openai",
            label="OpenAI (GPT)",
            description="OpenAI 官方 API，GPT 系列模型",
            kind="openai_compat",
            default_base_url="https://api.openai.com/v1",
            default_model="gpt-5.1",
            suggested_models=("gpt-5.1", "gpt-5", "gpt-4.1", "gpt-4o"),
            max_tokens_param="max_completion_tokens",
            key_hint="sk-...，从 platform.openai.com 获取",
        ),
        ProviderSpec(
            id="relay",
            label="中转站 (OpenAI 兼容)",
            description=(
                "第三方 API 中转/聚合服务，走 OpenAI 兼容端点。Base URL 与模型名由服务商决定，"
                "配置后用 `zerodev llm probe` 拉取可用模型列表确认。"
            ),
            kind="openai_compat",
            # Intentionally blank: a relay's endpoint and model aliases are
            # site-specific, so guessing a default would silently send the key
            # somewhere the user never chose.
            default_base_url="",
            default_model="",
            suggested_models=(),
            max_tokens_param="max_completion_tokens",
            key_hint="中转站控制台签发的 key，通常不是 sk-proj- 开头的官方格式",
        ),
        ProviderSpec(
            id="gemini",
            label="Google Gemini",
            description="Google AI Studio，走官方 OpenAI 兼容端点",
            kind="openai_compat",
            default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            default_model="gemini-2.5-pro",
            suggested_models=("gemini-2.5-pro", "gemini-2.5-flash", "gemini-3-pro-preview"),
            key_hint="从 aistudio.google.com 获取 API Key",
        ),
        ProviderSpec(
            id="deepseek",
            label="DeepSeek",
            description="深度求索官方 API",
            kind="openai_compat",
            default_base_url="https://api.deepseek.com/v1",
            default_model="deepseek-chat",
            suggested_models=("deepseek-chat", "deepseek-reasoner"),
            key_hint="从 platform.deepseek.com 获取",
        ),
        ProviderSpec(
            id="qwen",
            label="通义千问 (Qwen)",
            description="阿里云百炼 DashScope，OpenAI 兼容模式",
            kind="openai_compat",
            default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            default_model="qwen-max",
            suggested_models=("qwen-max", "qwen-plus", "qwen-turbo", "qwen3-coder-plus"),
            key_hint="从 bailian.console.aliyun.com 获取",
        ),
        ProviderSpec(
            id="zhipu",
            label="智谱 GLM",
            description="智谱开放平台 GLM 系列",
            kind="openai_compat",
            default_base_url="https://open.bigmodel.cn/api/paas/v4",
            default_model="glm-4.6",
            suggested_models=("glm-4.6", "glm-4.5", "glm-4-plus"),
            key_hint="从 open.bigmodel.cn 获取",
        ),
        ProviderSpec(
            id="moonshot",
            label="月之暗面 Kimi",
            description="Moonshot 开放平台 Kimi 系列",
            kind="openai_compat",
            default_base_url="https://api.moonshot.cn/v1",
            default_model="kimi-k2-turbo-preview",
            suggested_models=("kimi-k2-turbo-preview", "kimi-k2-0905-preview", "moonshot-v1-32k"),
            key_hint="从 platform.moonshot.cn 获取",
        ),
        ProviderSpec(
            id="ollama",
            label="Ollama (本地)",
            description="本地 Ollama 服务，无需 API Key，数据不出本机",
            kind="openai_compat",
            default_base_url="http://localhost:11434/v1",
            default_model="llama3.1",
            suggested_models=("llama3.1", "qwen3", "deepseek-r1", "gemma3"),
            requires_api_key=False,
            key_hint="本地服务无需密钥",
        ),
    )
}

DEFAULT_PROVIDER = "claude"


def get_provider_spec(provider_id: str) -> ProviderSpec:
    """Return the spec for ``provider_id``, falling back to Claude."""
    return PROVIDERS.get(provider_id, PROVIDERS[DEFAULT_PROVIDER])
