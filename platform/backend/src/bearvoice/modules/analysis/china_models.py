from collections.abc import Iterable
from dataclasses import dataclass

from bearvoice.config import Settings
from bearvoice.modules.analysis.china_model_adapter import (
    ChinaModelProvider,
    ModelConfigurationError,
    OpenAICompatibleChatAdapter,
    SUPPORTED_PROVIDERS,
    provider_config_from_settings,
)
from bearvoice.modules.analysis.semantic_engine import SemanticAnalysisEngine
from bearvoice.modules.analysis.semantic_models import (
    VoiceSemanticInput,
    VoiceSemanticResult,
)
from bearvoice.security.model_gateway import ModelGateway


@dataclass(frozen=True)
class ProviderOption:
    provider: ChinaModelProvider
    configured: bool
    approved: bool
    model: str | None


def provider_options(settings: Settings | None = None) -> tuple[ProviderOption, ...]:
    """Return UI-safe provider state without keys or endpoint addresses."""

    resolved = settings or Settings()
    options: list[ProviderOption] = []
    for provider in SUPPORTED_PROVIDERS:
        prefix = "custom_ai" if provider == "custom" else provider
        secret = getattr(resolved, f"{prefix}_api_key")
        model = getattr(resolved, f"{prefix}_model")
        base_url = getattr(resolved, f"{prefix}_base_url")
        configured = bool(
            secret is not None
            and secret.get_secret_value().strip()
            and model
            and model.strip()
            and base_url
        )
        try:
            provider_config_from_settings(resolved, provider)
            policy_ready = True
        except ModelConfigurationError:
            policy_ready = False
        options.append(
            ProviderOption(
                provider=provider,
                configured=configured,
                approved=(
                    resolved.model_egress_enabled
                    and provider in resolved.model_provider_allowlist
                    and "voice_semantic_analysis"
                    in resolved.model_purpose_allowlist
                    and policy_ready
                ),
                model=model.strip() if model and model.strip() else None,
            )
        )
    return tuple(options)


def build_model_gateway_from_settings(
    settings: Settings | None = None,
    *,
    providers: Iterable[ChinaModelProvider] | None = None,
) -> ModelGateway:
    resolved = settings or Settings()
    selected = tuple(
        resolved.model_provider_allowlist if providers is None else providers
    )
    adapters = {}
    for provider in selected:
        config = provider_config_from_settings(resolved, provider)
        adapters[provider] = OpenAICompatibleChatAdapter(config)
    return ModelGateway.from_settings(resolved, adapters=adapters)


def build_semantic_engine(
    provider: ChinaModelProvider,
    settings: Settings | None = None,
) -> SemanticAnalysisEngine:
    """Build one explicitly selected and administratively approved provider."""

    resolved_settings = settings or Settings()
    config = provider_config_from_settings(resolved_settings, provider)
    adapter = OpenAICompatibleChatAdapter(config)
    gateway = ModelGateway.from_settings(
        resolved_settings,
        adapters={provider: adapter},
    )
    return SemanticAnalysisEngine(
        gateway,
        provider=provider,
        model=config.model,
    )


async def analyze_voice(
    *,
    voice_id: str,
    text: str,
    product_name: str | None,
    provider: ChinaModelProvider,
    run_id: str,
    settings: Settings | None = None,
) -> VoiceSemanticResult:
    """Stable application-facing entry point; result.signals is persistence-ready."""

    engine = build_semantic_engine(provider, settings)
    return await engine.analyze(
        VoiceSemanticInput(
            voice_id=voice_id,
            text=text,
            product_name=product_name,
        ),
        run_id=run_id,
    )
