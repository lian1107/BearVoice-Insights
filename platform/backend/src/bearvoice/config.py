from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration with private-by-default model access."""

    model_config = SettingsConfigDict(
        env_prefix="BEARVOICE_",
        env_file=".env",
        extra="ignore",
    )

    model_egress_enabled: bool = False
