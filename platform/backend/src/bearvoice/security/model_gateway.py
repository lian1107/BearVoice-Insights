import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from bearvoice.config import Settings
from bearvoice.modules.ingest.privacy import sanitize_voice_text


class ModelEgressDisabled(PermissionError):
    pass


class ModelPolicyViolation(PermissionError):
    pass


class PrivacyViolation(ValueError):
    pass


@dataclass(frozen=True)
class ModelRequest:
    provider: str
    model: str
    purpose: str
    payload: Mapping[str, object]
    run_id: str


@dataclass(frozen=True)
class ModelResponse:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0


class ModelAdapter(Protocol):
    async def generate(self, request: ModelRequest) -> ModelResponse: ...


def _iter_text(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _iter_text(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _iter_text(nested)


class ModelGateway:
    def __init__(
        self,
        settings: Settings,
        adapters: Mapping[str, ModelAdapter],
    ) -> None:
        self.settings = settings
        self.adapters = dict(adapters)
        self.last_log: dict[str, object] | None = None

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        adapters: Mapping[str, ModelAdapter] | None = None,
    ) -> "ModelGateway":
        return cls(settings or Settings(), adapters or {})

    def _assert_policy(self, request: ModelRequest) -> None:
        if request.provider not in self.settings.model_provider_allowlist:
            raise ModelPolicyViolation("模型提供商未经批准")
        if request.purpose not in self.settings.model_purpose_allowlist:
            raise ModelPolicyViolation("模型用途未经批准")
        if request.provider not in self.adapters:
            raise ModelPolicyViolation("获批提供商未配置适配器")

    @staticmethod
    def _assert_sanitized(payload: Mapping[str, object]) -> None:
        if any(sanitize_voice_text(text).findings for text in _iter_text(payload)):
            raise PrivacyViolation("模型载荷未通过隐私门禁")

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.settings.model_egress_enabled:
            raise ModelEgressDisabled("模型外发默认关闭")
        self._assert_policy(request)
        self._assert_sanitized(request.payload)
        response = await self.adapters[request.provider].generate(request)
        canonical_payload = json.dumps(
            request.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.last_log = {
            "payload_hash": hashlib.sha256(
                canonical_payload.encode("utf-8")
            ).hexdigest(),
            "provider": request.provider,
            "model": request.model,
            "purpose": request.purpose,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "run_id": request.run_id,
        }
        return response
