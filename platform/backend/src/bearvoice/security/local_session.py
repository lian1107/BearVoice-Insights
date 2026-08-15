import hashlib
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


LOCAL_DEV_SESSION_COOKIE = "bearvoice_local_dev_session"


@dataclass(frozen=True)
class StoredLocalSession:
    claims: Mapping[str, object]
    expires_at: datetime


class LocalDevSessionStore:
    """Process-local development sessions; raw tokens are never retained."""

    def __init__(self) -> None:
        self._sessions: dict[str, StoredLocalSession] = {}

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue(
        self,
        claims: Mapping[str, object],
        *,
        ttl_seconds: int,
    ) -> tuple[str, datetime]:
        if ttl_seconds < 60 or ttl_seconds > 86_400:
            raise ValueError("本地开发会话有效期必须在 60 秒到 24 小时之间")
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        self._sessions[self._digest(token)] = StoredLocalSession(
            claims=dict(claims),
            expires_at=expires_at,
        )
        return token, expires_at

    def resolve(self, token: str) -> Mapping[str, object] | None:
        digest = self._digest(token)
        session = self._sessions.get(digest)
        if session is None:
            return None
        if session.expires_at <= datetime.now(UTC):
            self._sessions.pop(digest, None)
            return None
        return session.claims
