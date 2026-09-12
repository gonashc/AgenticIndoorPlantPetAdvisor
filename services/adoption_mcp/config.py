"""Configuration for the private adoption MCP service."""

from typing import Literal
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdoptionMcpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    rescuegroups_api_key: SecretStr
    rescuegroups_base_url: str = "https://api.rescuegroups.org/v5"
    rescuegroups_timeout_seconds: float = 8.0
    rescuegroups_radius_miles: int = 100
    adoption_allowed_link_hosts: str = "rescuegroups.org"
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*"

    @field_validator("rescuegroups_api_key", mode="before")
    @classmethod
    def strip_api_key(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return SecretStr(value.get_secret_value().strip())
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_service_settings(self) -> "AdoptionMcpSettings":
        if not self.rescuegroups_api_key.get_secret_value():
            raise ValueError("RESCUEGROUPS_API_KEY cannot be empty")
        parsed = urlparse(self.rescuegroups_base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("RESCUEGROUPS_BASE_URL must be an HTTPS origin")
        if self.app_env == "production" and parsed.hostname != "api.rescuegroups.org":
            raise ValueError("Production must use the RescueGroups production API")
        if self.rescuegroups_timeout_seconds <= 0:
            raise ValueError("RESCUEGROUPS_TIMEOUT_SECONDS must be positive")
        if not 1 <= self.rescuegroups_radius_miles <= 500:
            raise ValueError("RESCUEGROUPS_RADIUS_MILES must be between 1 and 500")
        if not self.allowed_link_hosts():
            raise ValueError("ADOPTION_ALLOWED_LINK_HOSTS cannot be empty")
        if self.app_env == "production" and not self.allowed_hosts():
            raise ValueError("MCP_ALLOWED_HOSTS is required in production")
        return self

    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]

    def allowed_link_hosts(self) -> frozenset[str]:
        return frozenset(
            value.strip().lower()
            for value in self.adoption_allowed_link_hosts.split(",")
            if value.strip()
        )
