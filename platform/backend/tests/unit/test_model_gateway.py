import pytest

from bearvoice.config import Settings
from bearvoice.security.model_gateway import (
    ModelEgressDisabled,
    ModelGateway,
    ModelRequest,
    ModelResponse,
    PrivacyViolation,
)


class StubAdapter:
    def __init__(self):
        self.calls = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse(content="聚类名称", input_tokens=8, output_tokens=4)


async def test_model_gateway_denies_egress_without_admin_configuration():
    with pytest.raises(ModelEgressDisabled):
        await ModelGateway.from_settings().generate(
            ModelRequest(
                provider="approved-provider",
                model="private-model-v1",
                purpose="cluster_label",
                payload={"text": "脱敏文本"},
                run_id="run-1",
            )
        )


async def test_model_gateway_allows_only_whitelisted_sanitized_requests():
    adapter = StubAdapter()
    settings = Settings(
        model_egress_enabled=True,
        model_provider_allowlist=("approved-provider",),
        model_purpose_allowlist=("cluster_label",),
    )
    gateway = ModelGateway.from_settings(
        settings,
        adapters={"approved-provider": adapter},
    )
    request = ModelRequest(
        provider="approved-provider",
        model="private-model-v1",
        purpose="cluster_label",
        payload={"text": "脱敏后的养生壶清洁问题"},
        run_id="run-1",
    )

    response = await gateway.generate(request)

    assert response.content == "聚类名称"
    assert len(adapter.calls) == 1
    assert gateway.last_log == {
        "payload_hash": gateway.last_log["payload_hash"],
        "provider": "approved-provider",
        "model": "private-model-v1",
        "purpose": "cluster_label",
        "input_tokens": 8,
        "output_tokens": 4,
        "run_id": "run-1",
    }
    assert "养生壶" not in str(gateway.last_log)

    with pytest.raises(PrivacyViolation):
        await gateway.generate(
            ModelRequest(
                provider="approved-provider",
                model="private-model-v1",
                purpose="cluster_label",
                payload={"text": "请联系 13800138000"},
                run_id="run-2",
            )
        )
