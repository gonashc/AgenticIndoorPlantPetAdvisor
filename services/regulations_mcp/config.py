"""Configuration for the regulations MCP service."""

from typing import Literal
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.you_search import validate_you_api_key


class RegulationsMcpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    regulations_provider: Literal["disabled", "you_discovery"] = "disabled"
    regulations_allowed_source_hosts: str = ""
    you_api_key: SecretStr | None = None
    you_search_url: str = "https://ydc-index.io/v1/search"
    you_timeout_seconds: float = 8.0
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*"

    @field_validator("you_api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            validate_you_api_key(value.get_secret_value())
        return value

    @model_validator(mode="after")
    def validate_service_settings(self) -> "RegulationsMcpSettings":
        if self.app_env == "production" and not self.allowed_hosts():
            raise ValueError("MCP_ALLOWED_HOSTS is required in production")
        parsed = urlparse(self.you_search_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("YOU_SEARCH_URL must be an HTTPS URL")
        if self.app_env == "production" and parsed.hostname != "ydc-index.io":
            raise ValueError("Production must use the official You.com Search API")
        if self.you_timeout_seconds <= 0:
            raise ValueError("YOU_TIMEOUT_SECONDS must be positive")
        if self.regulations_provider == "you_discovery" and (
            self.you_api_key is None or not self.you_api_key.get_secret_value().strip()
        ):
            raise ValueError("YOU_API_KEY is required for regulation source discovery")
        if self.app_env == "production" and self.regulations_provider != "you_discovery":
            raise ValueError("Production Regulations MCP requires source discovery")
        return self

    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]

    def allowed_source_hosts(self) -> frozenset[str]:
        return frozenset(
            value.strip().lower()
            for value in self.regulations_allowed_source_hosts.split(",")
            if value.strip()
        )
