"""Configuration for the private climate MCP service."""

from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClimateMcpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    nws_base_url: str = "https://api.weather.gov"
    nws_user_agent: str = (
        "AgenticIndoorPlantPetAdvisor/1.0 (https://github.com/gonashc/AgenticIndoorPlantPetAdvisor)"
    )
    nws_timeout_seconds: float = 8.0
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*"

    @field_validator("nws_user_agent")
    @classmethod
    def normalize_user_agent(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_service_settings(self) -> "ClimateMcpSettings":
        parsed = urlparse(self.nws_base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("NWS_BASE_URL must be an HTTPS origin")
        if self.app_env == "production" and parsed.hostname != "api.weather.gov":
            raise ValueError("Production must use the official National Weather Service API")
        if not self.nws_user_agent or len(self.nws_user_agent) > 300:
            raise ValueError("NWS_USER_AGENT must identify the application")
        if self.nws_timeout_seconds <= 0:
            raise ValueError("NWS_TIMEOUT_SECONDS must be positive")
        if self.app_env == "production" and not self.allowed_hosts():
            raise ValueError("MCP_ALLOWED_HOSTS is required in production")
        return self

    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]
