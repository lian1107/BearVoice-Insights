from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from bearvoice.config import Settings
from bearvoice.security.auth import Principal, get_principal
from bearvoice.security.local_session import (
    LOCAL_DEV_SESSION_COOKIE,
    LocalDevSessionStore,
)


router = APIRouter(prefix="/auth", tags=["auth"])
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _hostname(value: str) -> str | None:
    return urlparse(value if "://" in value else f"//{value}").hostname


def _local_development_enabled(settings: Settings) -> bool:
    return (
        settings.runtime_environment == "development"
        and settings.local_dev_session_enabled
    )


def _assert_loopback_request(request: Request) -> None:
    if _hostname(request.headers.get("host", "")) not in LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="本地开发登录仅允许 localhost")
    origin = request.headers.get("origin")
    if origin and _hostname(origin) not in LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="本地开发登录来源无效")


@router.get("/options")
async def auth_options(request: Request) -> dict[str, bool]:
    settings: Settings = request.app.state.settings
    return {
        "local_dev_session": _local_development_enabled(settings),
        "oidc_configured": bool(
            settings.oidc_issuer
            and settings.oidc_audience
            and settings.oidc_jwks_url
        ),
    }


@router.post("/dev-session", status_code=status.HTTP_201_CREATED)
async def create_local_dev_session(
    request: Request,
    response: Response,
) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    if not _local_development_enabled(settings):
        raise HTTPException(status_code=404, detail="本地开发登录未启用")
    _assert_loopback_request(request)
    sessions: LocalDevSessionStore = request.app.state.local_dev_sessions
    token, expires_at = sessions.issue(
        {
            "sub": "local-dev-admin",
            "roles": ["admin"],
            "product_lines": ["养生壶"],
        },
        ttl_seconds=settings.local_dev_session_ttl_seconds,
    )
    response.set_cookie(
        key=LOCAL_DEV_SESSION_COOKIE,
        value=token,
        max_age=settings.local_dev_session_ttl_seconds,
        expires=expires_at,
        path="/api",
        secure=False,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"mode": "local_development", "expires_at": expires_at.isoformat()}


@router.get("/session")
async def current_session(
    principal: Principal = Depends(get_principal),
) -> dict[str, object]:
    return {
        "subject": principal.subject,
        "roles": sorted(principal.roles),
        "permissions": sorted(permission.value for permission in principal.permissions),
        "product_lines": sorted(principal.product_lines),
    }
