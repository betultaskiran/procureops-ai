"""
app/core/config.py

Central configuration for the ProcureOps backend.

How it works:
  1. pydantic-settings reads environment variables automatically.
  2. In development, those variables come from the .env file (via docker-compose
     env_file: .env or a local .env when running outside Docker).
  3. In production, they come from the real system environment (no .env file).

This means: we never hardcode secrets. The same code runs in dev and prod,
with different values injected at runtime through environment variables.

Usage anywhere in the codebase:
  from app.core.config import settings
  print(settings.POSTGRES_HOST)
"""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET: str = "dev-secret-change-in-production-only-procureops-jwt-secret-key-32chars"


class Settings(BaseSettings):
    """
    All configuration is defined here as typed fields.
    pydantic-settings will raise a clear error at startup if a required
    variable is missing — much better than a cryptic KeyError later.
    """

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "ProcureOps AI"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"  # development, staging, production
    DEBUG: bool = False

    # ── PostgreSQL ───────────────────────────────────────────────────────────
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "postgres"   # Default matches docker-compose service name
    POSTGRES_PORT: int = 5432

    # ── Qdrant ───────────────────────────────────────────────────────────────
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # ── Gemini (Google AI) ───────────────────────────────────────────────────
    # No default — startup fails fast if this is missing.
    # Get your key at: https://aistudio.google.com/app/apikey
    GEMINI_API_KEY: str

    # Which Gemini model to use for extraction tasks.
    # thinking_budget is controlled per-call, not here.
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # ── File Storage ─────────────────────────────────────────────────────────
    # Relative to the working directory (/app inside Docker).
    # Maps to backend/uploads/ on the host via volume mount.
    # Phase 13 will replace this with S3/GCS.
    UPLOAD_DIR: str = "uploads"

    # Maximum upload size in megabytes. Enforce at API level.
    MAX_UPLOAD_SIZE_MB: int = 50

    # ── JWT & Authentication (Phase 5) ───────────────────────────────────────
    JWT_SECRET_KEY: str = DEV_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # ── Observability & Production Hardening (Phase 7) ────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "console"  # 'console' or 'json'
    SENTRY_DSN: str | None = None

    # ── Email & SMTP Configuration (Phase 9) ──────────────────────────────────
    EMAIL_BACKEND: str = "smtp"  # "smtp", "console", "mock"
    SMTP_HOST: str = "smtp.provider.internal"
    SMTP_PORT: int = 1025
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str = "procurement@procureops.com"
    SMTP_FROM_NAME: str = "ProcureOps AI"
    SMTP_USE_TLS: bool = False
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT: int = 10  # seconds
    EMAIL_MAX_RETRIES: int = 3
    EMAIL_RETRY_BACKOFF_SECONDS: int = 30
    APP_BASE_URL: str = "http://localhost:3000"
    ENABLE_OUTBOX_WORKER: bool = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            if v.strip().startswith("[") and v.strip().endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return [str(origin).strip() for origin in v]
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """
        Enforce fail-closed security for JWT configuration, production invariants,
        and email provider settings:
        In production (when DEBUG is False or ENVIRONMENT is 'production'/'prod'),
        require non-default secrets, safe passwords, strict CORS, and valid SMTP setup.
        """
        is_production = (not self.DEBUG) or (self.ENVIRONMENT.lower() in ("production", "prod"))
        if is_production:
            if self.DEBUG and self.ENVIRONMENT.lower() in ("production", "prod"):
                raise ValueError(
                    "Production configuration error: DEBUG cannot be True when ENVIRONMENT is production."
                )
            if self.JWT_SECRET_KEY == DEV_JWT_SECRET:
                raise ValueError(
                    "Production configuration error: JWT_SECRET_KEY cannot use the default "
                    "development secret when DEBUG=False or ENVIRONMENT is production. "
                    "Configure a unique, high-entropy secret in your environment."
                )
            if len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    "Production configuration error: JWT_SECRET_KEY must be at least 32 "
                    "characters long in production."
                )
            if self.POSTGRES_PASSWORD == "change_me_in_production":
                raise ValueError(
                    "Production configuration error: POSTGRES_PASSWORD cannot use default "
                    "development placeholder 'change_me_in_production' in production."
                )
            if "*" in self.CORS_ORIGINS:
                raise ValueError(
                    "Production configuration error: Wildcard '*' in CORS_ORIGINS is prohibited "
                    "when credentialed authentication is enabled."
                )
            if self.EMAIL_BACKEND == "smtp":
                if self.SMTP_HOST in ("localhost", "127.0.0.1"):
                    raise ValueError(
                        "Production configuration error: SMTP_HOST cannot be localhost or 127.0.0.1 "
                        "in production when EMAIL_BACKEND is 'smtp'. Configure a valid SMTP provider."
                    )
                if self.SMTP_USER and not self.SMTP_PASSWORD:
                    raise ValueError(
                        "Production configuration error: SMTP_PASSWORD is required when SMTP_USER is configured."
                    )
                if self.SMTP_FROM_EMAIL.endswith("@procureops.local"):
                    raise ValueError(
                        "Production configuration error: SMTP_FROM_EMAIL cannot use development "
                        "domain '@procureops.local' in production."
                    )
        return self

    # ── pydantic-settings config ─────────────────────────────────────────────
    model_config = SettingsConfigDict(
        env_file=".env",          # Also read from .env if it exists
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",           # Ignore unknown env vars (e.g. system vars)
    )

    @property
    def postgres_url(self) -> str:
        """
        Constructs the PostgreSQL connection URL from individual parts.
        We keep them separate in .env because Docker also uses them
        to initialise the postgres container (POSTGRES_USER, etc.).
        """
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"


# Single instance used across the entire application.
# Import this, not the class.
settings = Settings()
