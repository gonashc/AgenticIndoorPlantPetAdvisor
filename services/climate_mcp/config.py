"""Configuration for the private climate MCP service."""

from typing import Literal
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClimateMcpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    nws_base_url: str = "https://api.weather.gov"
    nws_user_agent: str = (
        "AgenticIndoorPlantPetAdvisor/1.0 (https://github.com/gonashc/AgenticIndoorPlantPetAdvisor)"
    )
    nws_timeout_seconds: float = 8.0
    zip_coordinate_provider: Literal["disabled", "google"] = "disabled"
    google_geocoding_api_key: SecretStr | None = None
    google_geocoding_url: str = "https://maps.googleapis.com/maps/api/geocode/json"
    google_geocoding_timeout_seconds: float = 5.0
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
        geocoding_url = urlparse(self.google_geocoding_url)
        if geocoding_url.scheme != "https" or not geocoding_url.hostname:
            raise ValueError("GOOGLE_GEOCODING_URL must be an HTTPS URL")
        if self.app_env == "production" and geocoding_url.hostname != "maps.googleapis.com":
            raise ValueError("Production must use the official Google Geocoding API")
        if self.google_geocoding_timeout_seconds <= 0:
            raise ValueError("GOOGLE_GEOCODING_TIMEOUT_SECONDS must be positive")
        if self.zip_coordinate_provider == "google" and (
            self.google_geocoding_api_key is None
            or not self.google_geocoding_api_key.get_secret_value().strip()
        ):
            raise ValueError("GOOGLE_GEOCODING_API_KEY is required for Google ZIP resolution")
        if self.app_env == "production" and self.zip_coordinate_provider != "google":
            raise ValueError("Production Climate MCP requires bounded ZIP resolution")
        if self.app_env == "production" and not self.allowed_hosts():
            raise ValueError("MCP_ALLOWED_HOSTS is required in production")
        return self

    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]
