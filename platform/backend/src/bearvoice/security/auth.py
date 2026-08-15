from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from urllib.parse import urlparse

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWTError

from bearvoice.config import Settings
from bearvoice.domain.enums import Permission
from bearvoice.security.local_session import LOCAL_DEV_SESSION_COOKIE, LocalDevSessionStore


ROLE_PERMISSIONS: Mapping[str, frozenset[Permission]] = {
    "product_manager": frozenset(
        {
            Permission.READ_VOICE,
            Permission.RUN_ANALYSIS,
            Permission.REVIEW_TAXONOMY,
            Permission.REVIEW_OPPORTUNITY,
        }
    ),
    "quality_reviewer": frozenset(
        {
            Permission.READ_VOICE,
            Permission.REVIEW_TAXONOMY,
            Permission.REVIEW_OPPORTUNITY,
        }
    ),
    "model_reviewer": frozenset(
        {
            Permission.READ_VOICE,
            Permission.MANAGE_EVALUATION,
        }
    ),
    "source_admin": frozenset(
        {
            Permission.READ_VOICE,
            Permission.MANAGE_SOURCES,
            Permission.RUN_ANALYSIS,
        }
    ),
    "management": frozenset(
        {
            Permission.READ_VOICE,
            Permission.READ_ALL_PRODUCT_LINES,
        }
    ),
    "admin": frozenset(Permission),
}


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    permissions: frozenset[Permission]
    product_lines: frozenset[str]

    @classmethod
    def from_claims(cls, claims: Mapping[str, object]) -> "Principal":
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="身份凭证无效",
            )
        raw_roles = claims.get("roles", [])
        raw_product_lines = claims.get("product_lines", [])
        if not isinstance(raw_roles, Sequence) or isinstance(raw_roles, str):
            raw_roles = []
        if not isinstance(raw_product_lines, Sequence) or isinstance(
            raw_product_lines, str
        ):
            raw_product_lines = []
        roles = frozenset(str(role) for role in raw_roles)
        permissions = frozenset(
            permission
            for role in roles
            for permission in ROLE_PERMISSIONS.get(role, frozenset())
        )
        return cls(
            subject=subject,
            roles=roles,
            permissions=permissions,
            product_lines=frozenset(str(item) for item in raw_product_lines),
        )


bearer = HTTPBearer(auto_error=False)


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="身份凭证无效",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_token(token: str, settings: Settings) -> Mapping[str, object]:
    try:
        if settings.dev_auth_enabled:
            if (
                settings.dev_auth_signing_key is None
                or len(settings.dev_auth_signing_key) < 32
            ):
                raise _authentication_error()
            return jwt.decode(
                token,
                settings.dev_auth_signing_key,
                algorithms=["HS256"],
                issuer="bearvoice-dev",
                audience="bearvoice-dev",
            )
        if not all(
            (
                settings.oidc_issuer,
                settings.oidc_audience,
                settings.oidc_jwks_url,
            )
        ):
            raise _authentication_error()
        signing_key = _jwk_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
        )
    except HTTPException:
        raise
    except (PyJWTError, ValueError, TypeError) as error:
        raise _authentication_error() from error


@lru_cache(maxsize=8)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(
        jwks_url,
        cache_keys=True,
        lifespan=300,
        timeout=5,
    )


def _assert_same_origin_local_write(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    if not origin:
        raise HTTPException(status_code=403, detail="本地开发写操作缺少来源校验")
    origin_host = urlparse(origin).hostname
    request_host = urlparse(f"//{host}").hostname
    if origin_host not in {"localhost", "127.0.0.1", "::1"} or request_host not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise HTTPException(status_code=403, detail="本地开发写操作来源无效")


def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    settings = getattr(request.app.state, "settings", None) or Settings()
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return Principal.from_claims(_decode_token(credentials.credentials, settings))
    if (
        settings.runtime_environment == "development"
        and settings.local_dev_session_enabled
    ):
        token = request.cookies.get(LOCAL_DEV_SESSION_COOKIE)
        sessions: LocalDevSessionStore | None = getattr(
            request.app.state,
            "local_dev_sessions",
            None,
        )
        if token and sessions is not None:
            claims = sessions.resolve(token)
            if claims is not None:
                _assert_same_origin_local_write(request)
                return Principal.from_claims(claims)
    raise _authentication_error()


def assert_permission(principal: Principal, permission: Permission) -> None:
    if permission not in principal.permissions:
        raise HTTPException(status_code=403, detail="无权执行该操作")


def require_permission(
    permission: Permission,
) -> Callable[[Principal], Principal]:
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        assert_permission(principal, permission)
        return principal

    return dependency


def assert_product_scope(product_line: str, principal: Principal) -> None:
    if Permission.READ_ALL_PRODUCT_LINES in principal.permissions:
        return
    if product_line not in principal.product_lines:
        raise HTTPException(status_code=403, detail="无权访问该产品线")


def issue_dev_token(
    settings: Settings,
    *,
    subject: str,
    roles: tuple[str, ...],
    product_lines: tuple[str, ...],
    expires_in: timedelta = timedelta(hours=1),
) -> str:
    if (
        not settings.dev_auth_enabled
        or settings.dev_auth_signing_key is None
        or len(settings.dev_auth_signing_key) < 32
    ):
        raise RuntimeError("本地开发身份模式未安全配置")
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "roles": list(roles),
            "product_lines": list(product_lines),
            "iss": "bearvoice-dev",
            "aud": "bearvoice-dev",
            "iat": now,
            "exp": now + expires_in,
        },
        settings.dev_auth_signing_key,
        algorithm="HS256",
    )
