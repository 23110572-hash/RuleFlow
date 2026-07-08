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


    # Embeddings
    embedding_model: str = ""
    embedding_dim: int = 1024

    # Verification kernel
    citation_fidelity_threshold: float = 0.95

    # Auth
    secret_key: str = "dev-secret-change-in-production"
    token_expiry_minutes: int = 60 * 24 * 7  # 7 days

    # Storage
    storage_dir: str = "./storage"

    # Temporal
    temporal_address: str = ""
    temporal_namespace: str = "default"

    # CORS
    cors_origins: str = "https://rule-flow.vercel.app"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = []
        for o in self.cors_origins.split(","):
            o = o.strip().strip("'\"")
            if o:
                # Strip trailing slashes to prevent matching failures
                if o.endswith("/") and len(o) > 1:
                    o = o[:-1]
                origins.append(o)
                
        # Always whitelist the true production frontend just in case of environment variable typos
        prod_frontend = "https://rule-flow.vercel.app"
        if prod_frontend not in origins:
            origins.append(prod_frontend)
            
        # Also whitelist localhost for local dev if not present
        if "http://localhost:5173" not in origins:
            origins.append("http://localhost:5173")
            
        return origins

    @property
    def is_openrouter(self) -> bool:
        return self.llm_model.startswith("openrouter/")

    @property
    def llm_enabled(self) -> bool:
        """True when the active LLM provider is configured. An LLM is REQUIRED
        for the agent layer — there is no rule-based extraction fallback. If
        this is False, agent endpoints fail loudly. (The Verification Kernel is
        deterministic by design and does not depend on the LLM.)"""
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
