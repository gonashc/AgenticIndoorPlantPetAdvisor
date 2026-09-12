"""Configuration for the private plant-location MCP service."""

from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PlacesMcpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    google_places_api_key: SecretStr
    google_places_url: str = "https://places.googleapis.com/v1/places:searchText"
    google_places_timeout_seconds: float = 5.0
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*"

    @field_validator("google_places_api_key", mode="before")
    @classmethod
    def strip_api_key(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return SecretStr(value.get_secret_value().strip())
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_service_settings(self) -> "PlacesMcpSettings":
        if not self.google_places_api_key.get_secret_value():
            raise ValueError("GOOGLE_PLACES_API_KEY cannot be empty")
        if not self.google_places_url.startswith("https://"):
            raise ValueError("GOOGLE_PLACES_URL must use HTTPS")
        if self.google_places_timeout_seconds <= 0:
            raise ValueError("GOOGLE_PLACES_TIMEOUT_SECONDS must be positive")
        if self.app_env == "production" and not self.allowed_hosts():
            raise ValueError("MCP_ALLOWED_HOSTS is required in production")
        return self

    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]
