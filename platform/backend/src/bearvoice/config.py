from typing import Literal
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration with private-by-default model access."""

    model_config = SettingsConfigDict(
        env_prefix="BEARVOICE_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://bearvoice:local-only-change-me@127.0.0.1:55432/bearvoice"
    )
    temporal_address: str = "127.0.0.1:7233"
    cache_url: str = "redis://127.0.0.1:6379/0"
    model_egress_enabled: bool = False
    model_provider_allowlist: tuple[str, ...] = ()
    model_purpose_allowlist: tuple[str, ...] = ()
    runtime_environment: Literal["development", "test", "production"] = "production"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    dev_auth_enabled: bool = False
    dev_auth_signing_key: str | None = None
    local_dev_session_enabled: bool = False
    local_dev_session_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    max_upload_bytes: int = Field(default=10_485_760, ge=1_024, le=52_428_800)
    data_retention_days: int = Field(default=365, ge=1)
    storage_backend: Literal["filesystem", "s3"] = "filesystem"
    object_store_root: str = "../.data/objects"
    s3_endpoint_url: str | None = None
    s3_endpoint_allowlist: tuple[str, ...] = ()
    s3_bucket: str = ""

    def production_readiness_issues(self) -> tuple[str, ...]:
        """Return safe, non-secret configuration failures for readiness checks."""

        if self.runtime_environment != "production":
            return ()

        issues: list[str] = []
        if self.dev_auth_enabled:
            issues.append("development bearer authentication must be disabled")
        if self.local_dev_session_enabled:
            issues.append("local development sessions must be disabled")
        if not all((self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)):
            issues.append("OIDC configuration is incomplete")
        for label, value in (
            ("OIDC issuer", self.oidc_issuer),
            ("OIDC JWKS URL", self.oidc_jwks_url),
        ):
            if value and urlparse(value).scheme != "https":
                issues.append(f"{label} must use HTTPS")
        if self.storage_backend != "s3":
            issues.append("production object storage must use S3")
        elif (
            not self.s3_endpoint_url
            or self.s3_endpoint_url not in self.s3_endpoint_allowlist
            or urlparse(self.s3_endpoint_url).scheme != "https"
            or not self.s3_bucket.strip()
        ):
            issues.append("production S3 configuration is incomplete or unapproved")
        if self.model_egress_enabled and (
            not self.model_provider_allowlist or not self.model_purpose_allowlist
        ):
            issues.append("model egress requires provider and purpose allowlists")
        return tuple(issues)
