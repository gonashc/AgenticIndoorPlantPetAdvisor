"""Configuration for the private You.com guidance MCP."""

from typing import Literal
from urllib.parse import urlparse

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class YouMcpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    you_provider: Literal["disabled", "api"] = "disabled"
    you_api_key: SecretStr | None = None
    you_search_url: str = "https://ydc-index.io/v1/search"
    you_timeout_seconds: float = 8.0
    you_allowed_source_hosts: str = "cdc.gov,usda.gov,aspca.org"
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*"

    @model_validator(mode="after")
    def validate_service_settings(self) -> "YouMcpSettings":
        parsed = urlparse(self.you_search_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("YOU_SEARCH_URL must be an HTTPS URL")
        if self.app_env == "production" and parsed.hostname != "ydc-index.io":
            raise ValueError("Production must use the official You.com Search API")
        if self.you_timeout_seconds <= 0:
            raise ValueError("YOU_TIMEOUT_SECONDS must be positive")
        if self.you_provider == "api" and (
            self.you_api_key is None or not self.you_api_key.get_secret_value().strip()
        ):
            raise ValueError("YOU_API_KEY is required when YOU_PROVIDER=api")
        if self.app_env == "production" and self.you_provider != "api":
            raise ValueError("Production You MCP requires the API provider")
        if not self.allowed_source_hosts():
            raise ValueError("YOU_ALLOWED_SOURCE_HOSTS must not be empty")
        if self.app_env == "production" and not self.allowed_hosts():
            raise ValueError("MCP_ALLOWED_HOSTS is required in production")
        return self

    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]

    def allowed_source_hosts(self) -> frozenset[str]:
        return frozenset(
            value.strip().lower()
            for value in self.you_allowed_source_hosts.split(",")
            if value.strip()
        )
