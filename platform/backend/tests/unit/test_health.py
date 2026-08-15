from fastapi.testclient import TestClient

from bearvoice.main import create_app


def test_health_reports_service_and_no_model_egress():
    response = TestClient(create_app()).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "bearvoice",
        "status": "ok",
        "model_egress": "disabled",
    }
