"""Configuration for the regulations MCP service."""

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RegulationsMcpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    regulations_provider: Literal["disabled"] = "disabled"
    regulations_allowed_source_hosts: str = ""
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*"

    @model_validator(mode="after")
    def validate_service_settings(self) -> "RegulationsMcpSettings":
        if self.app_env == "production" and not self.allowed_hosts():
            raise ValueError("MCP_ALLOWED_HOSTS is required in production")
        return self

    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]

    def allowed_source_hosts(self) -> frozenset[str]:
        return frozenset(
            value.strip().lower()
            for value in self.regulations_allowed_source_hosts.split(",")
            if value.strip()
        )
