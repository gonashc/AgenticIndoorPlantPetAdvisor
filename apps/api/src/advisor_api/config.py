"""Non-secret application settings for the skeleton."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Minimal settings; provider configuration belongs behind integration ports."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "Indoor Plant and Pet Advisor API"
    api_version: Literal["v1"] = "v1"
    log_level: str = "INFO"
