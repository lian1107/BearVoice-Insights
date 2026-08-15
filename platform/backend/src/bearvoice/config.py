from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr
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
    model_endpoint_allowlist: tuple[str, ...] = ()
    model_request_timeout_seconds: float = Field(default=45.0, ge=1.0, le=300.0)
    semantic_batch_size: int = Field(default=20, ge=1, le=100)
    semantic_max_concurrency: int = Field(default=4, ge=1, le=20)
    semantic_retry_max_attempts: int = Field(default=3, ge=1, le=8)
    semantic_retry_initial_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    model_job_max_calls: int = Field(default=500, ge=1, le=100_000)
    model_daily_max_calls: int = Field(default=5_000, ge=1, le=1_000_000)
    model_job_budget_rmb: float = Field(default=50.0, ge=0.01, le=1_000_000)
    model_daily_budget_rmb: float = Field(default=500.0, ge=0.01, le=10_000_000)
    model_reserved_cost_per_call_rmb: float = Field(
        default=0.05, ge=0.0001, le=10_000
    )
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    glm_api_key: SecretStr | None = None
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-5.2"
    minimax_api_key: SecretStr | None = None
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-M3"
    qwen_api_key: SecretStr | None = None
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.8-max"
    custom_ai_api_key: SecretStr | None = None
    custom_ai_base_url: str | None = None
    custom_ai_model: str | None = None
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
            not self.model_provider_allowlist
            or not self.model_purpose_allowlist
            or not self.model_endpoint_allowlist
        ):
            issues.append(
                "model egress requires provider, purpose, and endpoint allowlists"
            )
        return tuple(issues)
