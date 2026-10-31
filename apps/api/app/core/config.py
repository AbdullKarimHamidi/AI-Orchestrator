"""Centralized, environment-driven configuration (validated by Pydantic)."""
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    mongodb_uri: str = "mongodb://127.0.0.1:27017/?replicaSet=rs0"
    mongodb_db: str = "orchestrator"

    # Fernet key(s) for encrypting provider credentials at rest. Comma-separated:
    # the first key encrypts, all keys decrypt (enables rotation).
    encryption_keys: str = Field(default="", description="Comma-separated Fernet keys")

    # NoDecode: accept a plain comma-separated env value instead of requiring JSON.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    session_cookie_name: str = "orch_session"
    csrf_cookie_name: str = "orch_csrf"
    session_ttl_hours: int = 24 * 7
    cookie_secure: bool = False  # MUST be true in production (enforced below)

    max_request_bytes: int = 1_000_000
    login_rate_limit_per_minute: int = 10
    register_rate_limit_per_minute: int = 10

    # Team onboarding. With registration disabled, only the very first account (bootstrap) and
    # people holding a valid invitation can sign up.
    allow_registration: bool = True
    # Public URL of the web app, used to build invitation links.
    public_url: str = "http://localhost:3000"
    invitation_ttl_days: int = 7

    # Execution
    worker_lease_seconds: int = 30
    worker_poll_interval_seconds: float = 0.5
    worker_concurrency: int = 4
    default_run_timeout_seconds: int = 120
    max_run_timeout_seconds: int = 1800

    # Tools. Private/loopback/link-local targets are blocked (SSRF protection) unless explicitly
    # allowed, e.g. for self-hosted installs whose tools call internal services.
    tools_allow_private_networks: bool = False
    tool_timeout_seconds: float = 30
    tool_max_response_bytes: int = 200_000

    # Knowledge
    max_upload_bytes: int = 25_000_000
    knowledge_chunk_chars: int = 2400
    knowledge_chunk_overlap: int = 300

    # Demo mode: when enabled, workspaces get a clearly labeled "Demo" provider that
    # returns deterministic synthetic output with zero cost. It never calls a real model.
    demo_mode: bool = True

    # Free AI APIs (see app/providers/presets.py). Each one that is set here is added to every
    # workspace as a ready-made provider. OLLAMA_BASE_URL enables a local Ollama server.
    groq_api_key: str = ""
    gemini_api_key: str = ""
    cerebras_api_key: str = ""
    openrouter_api_key: str = ""
    mistral_api_key: str = ""
    ollama_base_url: str = ""
    # New workspaces get a pack of ready-to-run agents on the best available free provider.
    seed_starter_agents: bool = True

    run_events_retention_days: int = 90
    audit_retention_days: int = 365

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str) and not v.startswith("["):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    def validate_for_runtime(self) -> None:
        if self.environment == "production":
            if not self.cookie_secure:
                raise RuntimeError("COOKIE_SECURE must be true in production")
            if not self.encryption_keys:
                raise RuntimeError("ENCRYPTION_KEYS is required in production")
            if not self.public_url.startswith("https://"):
                raise RuntimeError("PUBLIC_URL must be an https:// URL in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
