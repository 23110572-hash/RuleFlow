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

    # Database (production must set DATABASE_URL in the environment)
    database_url: str = "sqlite:///./ruleflow.db"

    # LLM (via LiteLLM). Model is swappable behind LiteLLM.
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    # Flash-Lite is the low-latency member of the 2.5 family and ~5x cheaper on
    # output than full 2.5 Flash. Extraction is "quote this clause", not deep
    # reasoning, and the citation kernel verifies every quote regardless of
    # model — so latency and price are the right things to optimise here.
    llm_model: str = "openrouter/google/gemini-2.5-flash-lite"
    llm_temperature: float = 0.0

    # An explicit output cap is REQUIRED for OpenRouter: with no max_tokens it
    # pre-authorises the model's full output ceiling (16k+ for gpt-4o-mini)
    # against the key's remaining budget and rejects the call with HTTP 402
    # ("requires more credits, or fewer max_tokens") even when credit remains.
    # Extraction responses are small JSON objects, so a tight cap is correct.
    # 2000 (not 1500) because the extraction call now also returns applicability.
    # This is the FLOOR: extraction raises it in proportion to clause length,
    # because one global ceiling cannot fit clauses spanning 74 to ~7,000
    # characters. A dense clause hit the cap mid-JSON, which cannot parse, and
    # the whole clause was then written off as unanalysable.
    llm_max_tokens: int = 2000
    # Upper bound for that scaling, and for the one retry issued when a reply
    # comes back with finish_reason == "length". Raising a ceiling is close to
    # free: billing is on tokens actually generated, not on the cap. The cap
    # exists to bound OpenRouter's pre-authorisation and to stop a runaway reply.
    llm_max_tokens_ceiling: int = 8000
    llm_timeout: int = 90
    llm_num_retries: int = 2

    # How many clause extractions may be in flight at once. Clauses are
    # independent, so this is the main lever on ingest wall-clock time: a
    # 500-clause circular is hundreds of round-trips, and running them serially
    # takes tens of minutes. Keep it modest — providers rate-limit per key
    # (HTTP 429), and on OpenRouter the allowance scales with account credit.
    # Raise it if ingest is slow and you see no 429s; lower it if you do.
    llm_concurrency: int = 6
    # Fall back to Groq when the primary (OpenRouter) call fails and a Groq key
    # is configured, so one provider being out of credit does not kill a run.
    llm_fallback_model: str = "groq/llama-3.3-70b-versatile"


    # Embeddings
    embedding_model: str = ""
    embedding_dim: int = 1024

    # Verification kernel
    citation_fidelity_threshold: float = 0.95

    # Auth
    secret_key: str = "development-only-change-me"
    token_expiry_minutes: int = 60 * 24 * 7  # 7 days

    # Email OTP. Render uses the HTTPS relay; direct SMTP remains available
    # for local/other environments where outbound SMTP is permitted.
    email_relay_url: str = ""
    email_relay_secret: str = ""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""

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
    def llm_fallback_enabled(self) -> bool:
        """True when a secondary provider is available for retry after a hard
        failure on the primary. Today that means: primary is OpenRouter and a
        Groq key is configured."""
        return bool(
            self.llm_fallback_model
            and self.llm_fallback_model != self.llm_model
            and self.is_openrouter
            and self.groq_api_key
        )

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
