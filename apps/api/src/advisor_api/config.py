"""Non-secret application settings."""

from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings; provider configuration belongs behind integration ports."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "Indoor Plant and Pet Advisor API"
    api_version: Literal["v1"] = "v1"
    log_level: str = "INFO"
    openapi_enabled: bool = True
    database_mode: Literal["memory", "url", "cloud_sql"] = "memory"
    database_url: SecretStr | None = None
    instance_connection_name: str | None = None
    db_user: str | None = None
    db_name: str | None = None
    db_password: SecretStr | None = None
    cloud_sql_enable_iam_auth: bool = True
    cloud_sql_ip_type: Literal["PRIVATE", "PUBLIC", "PSC"] = "PRIVATE"
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800

    @model_validator(mode="after")
    def database_configuration_is_complete(self) -> "Settings":
        if self.database_mode == "url":
            if self.database_url is None:
                raise ValueError("DATABASE_URL is required when DATABASE_MODE=url")
            if not self.database_url.get_secret_value().startswith("postgresql+asyncpg://"):
                raise ValueError("DATABASE_URL must use the postgresql+asyncpg dialect")
        if self.database_mode == "cloud_sql":
            missing = [
                name
                for name, value in {
                    "INSTANCE_CONNECTION_NAME": self.instance_connection_name,
                    "DB_USER": self.db_user,
                    "DB_NAME": self.db_name,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(f"Missing Cloud SQL settings: {', '.join(missing)}")
            if not self.cloud_sql_enable_iam_auth and self.db_password is None:
                raise ValueError("DB_PASSWORD is required when IAM database authentication is off")
            if self.cloud_sql_enable_iam_auth and self.db_password is not None:
                raise ValueError("DB_PASSWORD must be unset when IAM database authentication is on")
        if self.app_env == "production" and self.database_mode == "memory":
            raise ValueError("Production cannot use the in-memory persistence adapters")
        if self.db_pool_size < 1 or self.db_max_overflow < 0:
            raise ValueError("Database pool size must be positive and overflow cannot be negative")
        if self.db_pool_timeout_seconds < 1 or self.db_pool_recycle_seconds < 1:
            raise ValueError("Database pool timeout and recycle values must be positive")
        return self
