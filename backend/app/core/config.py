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

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration is defined here as typed fields.
    pydantic-settings will raise a clear error at startup if a required
    variable is missing — much better than a cryptic KeyError later.
    """

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "ProcureOps AI"
    APP_VERSION: str = "0.1.0"
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
    GEMINI_MODEL: str = "gemini-3.8-flash"

    # ── File Storage ─────────────────────────────────────────────────────────
    # Relative to the working directory (/app inside Docker).
    # Maps to backend/uploads/ on the host via volume mount.
    # Phase 13 will replace this with S3/GCS.
    UPLOAD_DIR: str = "uploads"

    # Maximum upload size in megabytes. Enforce at API level.
    MAX_UPLOAD_SIZE_MB: int = 50

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
