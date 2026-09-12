"""Configuration for the private catalog MCP service."""

from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CatalogMcpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    database_mode: Literal["memory", "url", "cloud_sql"] = "url"
    database_url: SecretStr | None = SecretStr(
        "postgresql+asyncpg://advisor:advisor@127.0.0.1:5432/advisor"
    )
    instance_connection_name: str | None = None
    db_user: str | None = None
    db_name: str | None = None
    db_password: SecretStr | None = None
    cloud_sql_enable_iam_auth: bool = True
    cloud_sql_ip_type: Literal["PRIVATE", "PUBLIC", "PSC"] = "PRIVATE"
    db_pool_size: int = 3
    db_max_overflow: int = 1
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800
    toxicity_allowed_trust_tiers: str = "AUTHORITATIVE,EXPERT_REVIEWED"
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*"

    @field_validator("database_url", "db_password", mode="before")
    @classmethod
    def strip_secrets(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return SecretStr(value.get_secret_value().strip())
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_service_settings(self) -> "CatalogMcpSettings":
        if self.database_mode == "memory":
            raise ValueError("Catalog MCP requires PostgreSQL")
        if self.database_mode == "url" and (
            self.database_url is None
            or not self.database_url.get_secret_value().startswith("postgresql+asyncpg://")
        ):
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
            has_password = bool(self.db_password and self.db_password.get_secret_value())
            if self.cloud_sql_enable_iam_auth and has_password:
                raise ValueError("DB_PASSWORD must be unset when IAM database authentication is on")
            if not self.cloud_sql_enable_iam_auth and not has_password:
                raise ValueError("DB_PASSWORD is required when IAM database authentication is off")
        if self.app_env == "production" and self.database_mode != "cloud_sql":
            raise ValueError("Production Catalog MCP requires Cloud SQL")
        if self.db_pool_size < 1 or self.db_max_overflow < 0:
            raise ValueError("Database pool size must be positive and overflow cannot be negative")
        if self.db_pool_timeout_seconds < 1 or self.db_pool_recycle_seconds < 1:
            raise ValueError("Database pool timeout and recycle values must be positive")
        if not self.allowed_trust_tiers():
            raise ValueError("TOXICITY_ALLOWED_TRUST_TIERS cannot be empty")
        if self.app_env == "production" and not self.allowed_hosts():
            raise ValueError("MCP_ALLOWED_HOSTS is required in production")
        return self

    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]

    def allowed_trust_tiers(self) -> frozenset[str]:
        allowed = {"AUTHORITATIVE", "EXPERT_REVIEWED", "DEMO_UNVERIFIED"}
        configured = {
            value.strip().upper()
            for value in self.toxicity_allowed_trust_tiers.split(",")
            if value.strip()
        }
        if configured.difference(allowed):
            raise ValueError("TOXICITY_ALLOWED_TRUST_TIERS contains an unknown tier")
        if self.app_env == "production" and "DEMO_UNVERIFIED" in configured:
            raise ValueError("Production cannot use DEMO_UNVERIFIED toxicity records")
        return frozenset(configured)
