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
