import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from bearvoice.config import Settings
from bearvoice.modules.analysis.china_model_adapter import (
    ModelConfigurationError,
    ModelSafetyRefusal,
    OpenAICompatibleChatAdapter,
    OpenAICompatibleProviderConfig,
    provider_config_from_settings,
)
from bearvoice.modules.analysis.china_models import provider_options
from bearvoice.modules.analysis.semantic_engine import (
    SEMANTIC_ANALYSIS_PURPOSE,
    SemanticAnalysisEngine,
    SemanticInputError,
    SemanticOutputError,
)
from bearvoice.modules.analysis.semantic_models import VoiceSemanticInput
from bearvoice.security.model_gateway import (
    ModelGateway,
    ModelRequest,
    ModelResponse,
)


class StubAdapter:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse(content=self.content, input_tokens=10, output_tokens=20)


def _result(signals: list[dict[str, object]]) -> str:
    return json.dumps(
        {"schema_version": "1.0", "voice_id": "voice-1", "signals": signals},
        ensure_ascii=False,
    )


def _signal(**overrides: object) -> dict[str, object]:
    signal: dict[str, object] = {
        "signal_type": "defect",
        "lifecycle_stage": "use",
        "object_name": "壶盖",
        "issue": "壶盖漏水",
        "latent_need": "安全密封",
        "scenario": "倒水时",
        "evidence_text": "壶盖漏水",
        "confidence": 0.86,
        "uncalibrated": True,
        "risk_level": "high",
        "root_cause_hypotheses": ["密封圈尺寸待验证"],
        "missing_information": ["产品批次"],
        "improvement_directions": ["评估密封结构优化"],
        "validation_suggestions": ["按批次做水压对比测试"],
    }
    signal.update(overrides)
    return signal


def _engine(content: str) -> tuple[SemanticAnalysisEngine, StubAdapter]:
    adapter = StubAdapter(content)
    settings = Settings(
        model_egress_enabled=True,
        model_provider_allowlist=("deepseek",),
        model_purpose_allowlist=(SEMANTIC_ANALYSIS_PURPOSE,),
    )
    gateway = ModelGateway.from_settings(settings, adapters={"deepseek": adapter})
    return (
        SemanticAnalysisEngine(
            gateway,
            provider="deepseek",
            model="deepseek-v4-pro",
        ),
        adapter,
    )


async def test_normal_multi_signal_result_is_strict_and_persistence_ready():
    engine, adapter = _engine(
        _result(
            [
                _signal(),
                _signal(
                    signal_type="consultation",
                    issue="询问清洗方法",
                    evidence_text="怎么清洗",
                    risk_level="low",
                ),
            ]
        )
    )

    result = await engine.analyze(
        VoiceSemanticInput(
            voice_id="voice-1",
            text="壶盖漏水，怎么清洗？联系 13800138000",
            product_name="养生壶",
        ),
        run_id="run-1",
    )

    assert len(result.signals) == 2
    sent_payload = adapter.calls[0].payload
    assert "13800138000" not in str(sent_payload)
    assert "[手机号已脱敏]" in str(sent_payload)
    assert sent_payload["thinking"] == {"type": "disabled"}
    assert sent_payload["response_format"] == {"type": "json_object"}

    usage = await engine.analyze_with_usage(
        VoiceSemanticInput(
            voice_id="voice-1",
            text="壶盖漏水，怎么清洗？",
            product_name="养生壶",
        ),
        run_id="run-usage",
    )
    assert usage.input_tokens == 10
    assert usage.output_tokens == 20


async def test_boundary_zero_signal_is_valid_but_extra_fields_are_rejected():
    engine, _ = _engine(_result([]))
    result = await engine.analyze(
        VoiceSemanticInput(voice_id="voice-1", text="包装完好", product_name=None),
        run_id="run-1",
    )
    assert result.signals == []

    invalid_engine, _ = _engine(
        json.dumps(
            {
                "schema_version": "1.0",
                "voice_id": "voice-1",
                "signals": [],
                "summary": "不允许的额外字段",
            }
        )
    )
    with pytest.raises(SemanticOutputError):
        await invalid_engine.analyze(
            VoiceSemanticInput(voice_id="voice-1", text="包装完好"),
            run_id="run-1",
        )


async def test_deep_decision_fields_are_required_and_blank_items_are_rejected():
    missing_direction = _signal()
    missing_direction.pop("improvement_directions")
    missing_engine, _ = _engine(_result([missing_direction]))
    with pytest.raises(SemanticOutputError):
        await missing_engine.analyze(
            VoiceSemanticInput(voice_id="voice-1", text="壶盖漏水"),
            run_id="run-1",
        )

    blank_validation_engine, _ = _engine(
        _result([_signal(validation_suggestions=[" "])])
    )
    with pytest.raises(SemanticOutputError):
        await blank_validation_engine.analyze(
            VoiceSemanticInput(voice_id="voice-1", text="壶盖漏水"),
            run_id="run-1",
        )


async def test_missing_input_is_rejected_before_model_call():
    engine, adapter = _engine(_result([]))
    with pytest.raises(ValidationError):
        VoiceSemanticInput(voice_id="voice-1", text="")
    with pytest.raises(SemanticInputError):
        await engine.analyze(
            VoiceSemanticInput(voice_id="voice-1", text="正常"),
            run_id=" ",
        )
    assert adapter.calls == []


async def test_misaligned_evidence_is_bounded_to_source_and_calibration_claim_is_rejected():
    mismatch_engine, _ = _engine(
        _result([_signal(evidence_text="输入中不存在的证据")])
    )
    repaired = await mismatch_engine.analyze(
        VoiceSemanticInput(voice_id="voice-1", text="壶盖漏水"),
        run_id="run-1",
    )
    assert repaired.signals[0].evidence_text == "壶盖漏水"
    assert repaired.signals[0].missing_information[0] == (
        "模型证据片段未逐字对齐，已回退为脱敏原声片段，需人工缩短"
    )

    calibrated_engine, _ = _engine(_result([_signal(uncalibrated=False)]))
    with pytest.raises(SemanticOutputError):
        await calibrated_engine.analyze(
            VoiceSemanticInput(voice_id="voice-1", text="壶盖漏水"),
            run_id="run-1",
        )


async def test_provider_safety_refusal_is_not_reported_as_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer top-secret-key"
        assert request.url == "https://api.minimaxi.com/v1/chat/completions"
        request_body = json.loads(request.content)
        assert request_body["model"] == "MiniMax-M3"
        assert request_body["stream"] is False
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": _result([])},
                    }
                ],
                "output_sensitive": True,
            },
        )

    config = OpenAICompatibleProviderConfig(
        provider="minimax",
        api_key=SecretStr("top-secret-key"),
        base_url="https://api.minimaxi.com/v1",
        model="MiniMax-M3",
        timeout_seconds=10,
    )
    adapter = OpenAICompatibleChatAdapter(
        config,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelSafetyRefusal):
        await adapter.generate(
            ModelRequest(
                provider="minimax",
                model="MiniMax-M3",
                purpose=SEMANTIC_ANALYSIS_PURPOSE,
                payload={
                    "model": "attempted-override",
                    "stream": True,
                    "messages": [{"role": "user", "content": "安全文本"}],
                },
                run_id="run-1",
            )
        )
    assert "top-secret-key" not in repr(config)

    pii_engine, _ = _engine(
        _result(
            [
                _signal(
                    issue="请联系 13800138000",
                    root_cause_hypotheses=["13800138000"],
                    validation_suggestions=["回访 13900139000 核实"],
                )
            ]
        )
    )
    pii_result = await pii_engine.analyze(
        VoiceSemanticInput(voice_id="voice-1", text="壶盖漏水"),
        run_id="run-1",
    )
    assert pii_result.signals[0].issue == "请联系 [手机号已脱敏]"
    assert pii_result.signals[0].validation_suggestions == [
        "回访 [手机号已脱敏] 核实"
    ]
    assert pii_result.signals[0].root_cause_hypotheses == []
    assert pii_result.signals[0].missing_information[0] == (
        "模型输出含疑似隐私内容，已自动脱敏，需人工复核"
    )


def test_provider_configuration_requires_https_and_endpoint_approval():
    settings = Settings(
        custom_ai_api_key="secret",
        custom_ai_base_url="http://internal.example/v1",
        custom_ai_model="company-model",
        model_endpoint_allowlist=("http://internal.example/v1",),
    )
    with pytest.raises(ModelConfigurationError, match="HTTPS"):
        provider_config_from_settings(settings, "custom")

    settings = Settings(
        deepseek_api_key="secret",
        model_endpoint_allowlist=("https://example.invalid/v1",),
    )
    with pytest.raises(ModelConfigurationError, match="endpoint allowlist"):
        provider_config_from_settings(settings, "deepseek")


def test_provider_registry_never_exposes_keys_or_endpoints():
    settings = Settings(
        model_egress_enabled=True,
        model_provider_allowlist=("custom",),
        model_purpose_allowlist=(SEMANTIC_ANALYSIS_PURPOSE,),
        model_endpoint_allowlist=("https://private.example/v1",),
        custom_ai_api_key="registry-secret",
        custom_ai_base_url="https://private.example/v1",
        custom_ai_model="company-model",
    )
    options = provider_options(settings)

    custom = next(item for item in options if item.provider == "custom")
    assert custom.configured is True
    assert custom.approved is True
    assert custom.model == "company-model"
    assert "registry-secret" not in repr(options)
    assert "private.example" not in repr(options)
