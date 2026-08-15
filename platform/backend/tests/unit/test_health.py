from fastapi.testclient import TestClient

from bearvoice.config import Settings
from bearvoice.main import create_app


def test_health_reports_service_and_no_model_egress():
    response = TestClient(create_app()).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "bearvoice",
        "status": "ok",
        "model_egress": "disabled",
    }
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


def test_production_disables_api_schema_and_reports_configuration_gaps():
    app = create_app(Settings(runtime_environment="production"))
    client = TestClient(app)

    assert client.get("/api/docs").status_code == 404
    issues = app.state.settings.production_readiness_issues()
    assert "OIDC configuration is incomplete" in issues
    assert "production object storage must use S3" in issues


def test_development_configuration_has_no_production_readiness_gate():
    settings = Settings(
        runtime_environment="development",
        local_dev_session_enabled=True,
        storage_backend="filesystem",
    )

    assert settings.production_readiness_issues() == ()
