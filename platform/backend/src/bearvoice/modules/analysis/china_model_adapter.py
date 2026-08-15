from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from bearvoice.config import Settings
from bearvoice.security.model_gateway import ModelRequest, ModelResponse


ChinaModelProvider = Literal["deepseek", "glm", "minimax", "qwen", "custom"]
SUPPORTED_PROVIDERS: tuple[ChinaModelProvider, ...] = (
    "deepseek",
    "glm",
    "minimax",
    "qwen",
    "custom",
)


class ModelConfigurationError(ValueError):
    pass


class ModelTransportError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class ModelSafetyRefusal(RuntimeError):
    pass


@dataclass(frozen=True, repr=False)
class OpenAICompatibleProviderConfig:
    provider: ChinaModelProvider
    api_key: SecretStr
    base_url: str
    model: str
    timeout_seconds: float

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleProviderConfig("
            f"provider={self.provider!r}, base_url={self.base_url!r}, "
            f"model={self.model!r}, timeout_seconds={self.timeout_seconds!r}, "
            "api_key=SecretStr('**********'))"
        )


def _normalized_https_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ModelConfigurationError(
            "模型 base URL 必须是无用户信息、查询参数和片段的 HTTPS 地址"
        )
    return normalized


def provider_config_from_settings(
    settings: Settings,
    provider: ChinaModelProvider,
) -> OpenAICompatibleProviderConfig:
    if provider not in SUPPORTED_PROVIDERS:
        raise ModelConfigurationError(f"不支持的模型提供商：{provider}")

    prefix = "custom_ai" if provider == "custom" else provider
    api_key = getattr(settings, f"{prefix}_api_key")
    base_url = getattr(settings, f"{prefix}_base_url")
    model = getattr(settings, f"{prefix}_model")
    if api_key is None or not api_key.get_secret_value().strip():
        raise ModelConfigurationError(f"{provider} API key 未配置")
    if not base_url or not model or not model.strip():
        raise ModelConfigurationError(f"{provider} base URL 或 model 未配置")

    normalized_url = _normalized_https_base_url(base_url)
    approved_endpoints = {
        _normalized_https_base_url(item)
        for item in settings.model_endpoint_allowlist
    }
    if normalized_url not in approved_endpoints:
        raise ModelConfigurationError("模型端点未进入管理员批准的 endpoint allowlist")

    return OpenAICompatibleProviderConfig(
        provider=provider,
        api_key=api_key,
        base_url=normalized_url,
        model=model.strip(),
        timeout_seconds=settings.model_request_timeout_seconds,
    )


class OpenAICompatibleChatAdapter:
    """Minimal non-streaming adapter shared by approved China model endpoints."""

    def __init__(
        self,
        config: OpenAICompatibleProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.provider != self._config.provider:
            raise ModelConfigurationError("请求 provider 与适配器配置不一致")
        if request.model != self._config.model:
            raise ModelConfigurationError("请求 model 与管理员配置不一致")

        headers = {
            "Authorization": (
                f"Bearer {self._config.api_key.get_secret_value()}"
            ),
            "Content-Type": "application/json",
        }
        body = {**request.payload, "model": self._config.model, "stream": False}
        try:
            async with httpx.AsyncClient(
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self._config.base_url}/chat/completions",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise ModelTransportError(
                f"模型服务请求失败，状态码 {status_code}",
                retryable=(status_code in {408, 409, 425, 429} or status_code >= 500),
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelTransportError("模型服务请求或响应无效") from exc

        if not isinstance(data, dict):
            raise ModelTransportError("模型响应不是 JSON 对象")
        if data.get("input_sensitive") is True or data.get("output_sensitive") is True:
            raise ModelSafetyRefusal("模型服务拒绝了敏感输入或输出")
        base_resp = data.get("base_resp")
        if isinstance(base_resp, dict) and base_resp.get("status_code") not in (
            None,
            0,
        ):
            raise ModelSafetyRefusal("模型服务返回安全或业务拒绝")

        try:
            choice = data["choices"][0]
            finish_reason = choice["finish_reason"]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelTransportError("模型响应缺少完整 completion") from exc
        if finish_reason != "stop" or not isinstance(content, str) or not content.strip():
            raise ModelSafetyRefusal("模型响应被拒绝、截断或为空")

        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        return ModelResponse(
            content=content,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )
