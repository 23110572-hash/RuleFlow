"""Application configuration, loaded from environment / .env.

Nothing here is category-specific. Every knob is data, not hardcoded behaviour.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    database_url: str = "postgresql+psycopg://neondb_owner:npg_RZLn0roq7JTF@ep-green-hat-adnobjle-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

    # LLM (via LiteLLM). Model is swappable behind LiteLLM.
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    llm_model: str = "groq/llama-3.3-70b-versatile"
    llm_temperature: float = 0.0

    # AWS Bedrock (used when llm_model starts with "bedrock/").
    # Either a Bedrock API key (bearer token, starts with "ABSK...") OR a
    # classic IAM access-key/secret pair. The bearer token takes precedence.
    aws_bearer_token_bedrock: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""
    aws_region_name: str = "us-east-1"

    # Embeddings
    embedding_model: str = ""
    embedding_dim: int = 1024

    # Verification kernel
    citation_fidelity_threshold: float = 0.95

    # Auth
    secret_key: str = "dev-secret-change-in-production"
    token_expiry_minutes: int = 60 * 24 * 7  # 7 days

    # Storage
    storage_backend: str = "local"
    storage_dir: str = "./storage"
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # Temporal
    temporal_address: str = ""
    temporal_namespace: str = "default"

    # CORS
    cors_origins: str = "https://rule-flow.vercel.app"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_bedrock(self) -> bool:
        return self.llm_model.startswith("bedrock/")

    @property
    def is_openrouter(self) -> bool:
        return self.llm_model.startswith("openrouter/")

    @property
    def llm_enabled(self) -> bool:
        """True when the active LLM provider is configured. An LLM is REQUIRED
        for the agent layer — there is no rule-based extraction fallback. If
        this is False, agent endpoints fail loudly. (The Verification Kernel is
        deterministic by design and does not depend on the LLM.)"""
        if self.is_bedrock:
            return bool(
                self.aws_bearer_token_bedrock
                or (self.aws_access_key_id and self.aws_secret_access_key)
            )
        if self.is_openrouter:
            return bool(self.openrouter_api_key)
        return bool(self.groq_api_key)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
