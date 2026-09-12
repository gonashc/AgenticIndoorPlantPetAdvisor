"""Non-secret application settings."""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings; provider configuration belongs behind integration ports."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "Indoor Plant and Pet Advisor API"
    api_version: Literal["v1"] = "v1"
    log_level: str = "INFO"
    openapi_enabled: bool = True
    auth_mode: Literal["disabled", "google_iap"] = "disabled"
    iap_audience: str | None = None
    enabled_categories: str = "PLANT,DOG"
    web_dist_dir: Path = Path("/app/web")
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
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "advisor-local"
    langsmith_workspace_id: str | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_hide_inputs: bool = True
    langsmith_hide_outputs: bool = True
    retrieval_mode: Literal["disabled", "pinecone"] = "disabled"
    pinecone_api_key: SecretStr | None = None
    pinecone_index_host: str | None = None
    pinecone_index_dimension: int = 512
    pinecone_index_metric: Literal["dotproduct"] = "dotproduct"
    pinecone_namespace: str = "knowledge-candidate-v1"
    pinecone_dense_model: str = "llama-text-embed-v2"
    pinecone_sparse_model: str = "pinecone-sparse-english-v0"
    pinecone_rerank_model: str = "bge-reranker-v2-m3"
    pinecone_hybrid_alpha: float = 0.65
    pinecone_timeout_seconds: float = 10.0
    explanation_mode: Literal["deterministic", "openai"] = "deterministic"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_timeout_seconds: float = 20.0
    openai_max_retries: int = 2
    mcp_mode: Literal["disabled", "remote"] = "disabled"
    mcp_places_url: str | None = None
    mcp_adoption_url: str | None = None
    mcp_timeout_seconds: float = 8.0

    @field_validator(
        "db_password",
        "langsmith_api_key",
        "pinecone_api_key",
        "openai_api_key",
        mode="before",
    )
    @classmethod
    def secret_values_have_no_surrounding_whitespace(cls, value: object) -> object:
        """Normalize environment/secret-manager line endings before provider use."""

        if isinstance(value, SecretStr):
            return SecretStr(value.get_secret_value().strip())
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def database_configuration_is_complete(self) -> "Settings":
        if self.database_mode == "url":
            if self.database_url is None:
                raise ValueError("DATABASE_URL is required when DATABASE_MODE=url")
            if not self.database_url.get_secret_value().startswith("postgresql+asyncpg://"):
                raise ValueError("DATABASE_URL must use the postgresql+asyncpg dialect")
        if self.database_mode == "cloud_sql":
            has_database_password = bool(
                self.db_password and self.db_password.get_secret_value().strip()
            )
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
            if not self.cloud_sql_enable_iam_auth and not has_database_password:
                raise ValueError("DB_PASSWORD is required when IAM database authentication is off")
            if self.cloud_sql_enable_iam_auth and has_database_password:
                raise ValueError("DB_PASSWORD must be unset when IAM database authentication is on")
        if self.app_env == "production" and self.database_mode == "memory":
            raise ValueError("Production cannot use the in-memory persistence adapters")
        if self.app_env == "production" and self.auth_mode != "google_iap":
            raise ValueError("Production requires AUTH_MODE=google_iap")
        if self.auth_mode == "google_iap" and (
            not self.iap_audience or not self.iap_audience.startswith("/projects/")
        ):
            raise ValueError("IAP_AUDIENCE must be a Google Cloud IAP resource audience")
        categories = {
            value.strip() for value in self.enabled_categories.split(",") if value.strip()
        }
        if not categories or categories.difference({"PLANT", "DOG", "CAT"}):
            raise ValueError("ENABLED_CATEGORIES must contain PLANT, DOG, or CAT")
        if self.db_pool_size < 1 or self.db_max_overflow < 0:
            raise ValueError("Database pool size must be positive and overflow cannot be negative")
        if self.db_pool_timeout_seconds < 1 or self.db_pool_recycle_seconds < 1:
            raise ValueError("Database pool timeout and recycle values must be positive")
        if self.langsmith_tracing:
            if self.langsmith_api_key is None:
                raise ValueError("LANGSMITH_API_KEY is required when LANGSMITH_TRACING=true")
            if not self.langsmith_api_key.get_secret_value().strip():
                raise ValueError("LANGSMITH_API_KEY cannot be empty when tracing is enabled")
            if not self.langsmith_project.strip():
                raise ValueError("LANGSMITH_PROJECT cannot be empty when tracing is enabled")
            if not self.langsmith_endpoint.startswith(("https://", "http://")):
                raise ValueError("LANGSMITH_ENDPOINT must be an HTTP(S) URL")
        if not 0 <= self.pinecone_hybrid_alpha <= 1:
            raise ValueError("PINECONE_HYBRID_ALPHA must be between 0 and 1")
        if self.pinecone_index_dimension < 1:
            raise ValueError("PINECONE_INDEX_DIMENSION must be positive")
        if self.pinecone_timeout_seconds <= 0:
            raise ValueError("PINECONE_TIMEOUT_SECONDS must be positive")
        if self.retrieval_mode == "pinecone":
            if self.pinecone_api_key is None or not self.pinecone_api_key.get_secret_value():
                raise ValueError("PINECONE_API_KEY is required when RETRIEVAL_MODE=pinecone")
            if not self.pinecone_index_host:
                raise ValueError("PINECONE_INDEX_HOST is required when RETRIEVAL_MODE=pinecone")
            if not self.pinecone_namespace.strip():
                raise ValueError("PINECONE_NAMESPACE cannot be empty")
        if self.openai_timeout_seconds <= 0 or self.openai_max_retries < 0:
            raise ValueError("OpenAI timeout must be positive and retries cannot be negative")
        if self.explanation_mode == "openai":
            if self.retrieval_mode != "pinecone":
                raise ValueError("OpenAI explanations require approved Pinecone retrieval")
            if self.openai_api_key is None or not self.openai_api_key.get_secret_value():
                raise ValueError("OPENAI_API_KEY is required when EXPLANATION_MODE=openai")
            if not self.openai_model or not self.openai_model.strip():
                raise ValueError("OPENAI_MODEL is required when EXPLANATION_MODE=openai")
        if self.mcp_timeout_seconds <= 0:
            raise ValueError("MCP_TIMEOUT_SECONDS must be positive")
        if self.mcp_mode == "remote":
            urls = (self.mcp_places_url, self.mcp_adoption_url)
            if not all(url and url.startswith("https://") for url in urls):
                raise ValueError("Remote MCP endpoints must both use HTTPS")
        return self

    def enabled_category_values(self) -> frozenset[str]:
        return frozenset(
            value.strip() for value in self.enabled_categories.split(",") if value.strip()
        )
