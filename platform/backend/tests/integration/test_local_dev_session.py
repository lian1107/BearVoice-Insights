from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from bearvoice.config import Settings
from bearvoice.main import create_app
from bearvoice.security.auth import Principal, get_principal
from bearvoice.security.local_session import (
    LOCAL_DEV_SESSION_COOKIE,
    LocalDevSessionStore,
)


LOCAL_HEADERS = {
    "host": "localhost:4173",
    "origin": "http://localhost:4173",
}


def test_local_dev_session_is_disabled_by_default():
    client = TestClient(create_app(Settings()))

    response = client.post("/api/auth/dev-session", headers=LOCAL_HEADERS)

    assert response.status_code == 404


def test_local_dev_session_requires_development_and_loopback_host():
    settings = Settings(
        runtime_environment="development",
        local_dev_session_enabled=True,
    )
    client = TestClient(create_app(settings))

    remote = client.post(
        "/api/auth/dev-session",
        headers={"host": "bearvoice.internal", "origin": "https://bearvoice.internal"},
    )

    assert remote.status_code == 403


def test_local_dev_session_rejects_missing_browser_origin():
    settings = Settings(
        runtime_environment="development",
        local_dev_session_enabled=True,
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/auth/dev-session",
        headers={"host": "localhost:4173"},
    )

    assert response.status_code == 403


def test_local_dev_session_uses_short_lived_httponly_cookie():
    settings = Settings(
        runtime_environment="development",
        local_dev_session_enabled=True,
        local_dev_session_ttl_seconds=900,
    )
    client = TestClient(create_app(settings))

    login = client.post("/api/auth/dev-session", headers=LOCAL_HEADERS)

    assert login.status_code == 201
    assert login.json()["mode"] == "local_development"
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api" in cookie
    assert "max-age=900" in cookie

    session = client.get("/api/auth/session", headers=LOCAL_HEADERS)
    assert session.status_code == 200
    payload = session.json()
    assert payload["subject"] == "local-dev-admin"
    assert "admin" in payload["roles"]
    assert "养生壶" in payload["product_lines"]


def test_local_dev_session_cannot_be_enabled_in_production():
    settings = Settings(
        runtime_environment="production",
        local_dev_session_enabled=True,
    )
    client = TestClient(create_app(settings))

    response = client.post("/api/auth/dev-session", headers=LOCAL_HEADERS)

    assert response.status_code == 404


def test_cookie_authenticated_writes_require_same_origin():
    app = FastAPI()
    app.state.settings = Settings(
        runtime_environment="development",
        local_dev_session_enabled=True,
    )
    app.state.local_dev_sessions = LocalDevSessionStore()

    @app.post("/api/write")
    def write(principal: Principal = Depends(get_principal)):
        return {"subject": principal.subject}

    token, _ = app.state.local_dev_sessions.issue(
        {
            "sub": "local-dev-admin",
            "roles": ["admin"],
            "product_lines": ["养生壶"],
        },
        ttl_seconds=900,
    )
    client = TestClient(app)
    client.cookies.set(LOCAL_DEV_SESSION_COOKIE, token, path="/api")

    missing_origin = client.post(
        "/api/write",
        headers={"host": "localhost:4173"},
    )
    allowed = client.post("/api/write", headers=LOCAL_HEADERS)

    assert missing_origin.status_code == 403
    assert allowed.status_code == 200


def test_local_session_store_bounds_process_memory():
    sessions = LocalDevSessionStore(max_sessions=1)
    first, _ = sessions.issue({"sub": "first"}, ttl_seconds=900)
    second, _ = sessions.issue({"sub": "second"}, ttl_seconds=900)

    assert sessions.resolve(first) is None
    assert sessions.resolve(second) == {"sub": "second"}
