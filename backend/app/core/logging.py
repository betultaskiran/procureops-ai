"""
app/core/logging.py

Centralized structured logging and observability configuration for ProcureOps AI:
- Correlation ID propagation via contextvars.
- JSON structured log formatter for production log aggregators (ELK, Datadog, CloudWatch).
- Human-readable colored console formatter for local development.
- Sentry integration hook with graceful degradation.
"""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any

from app.core.config import settings

# Context variable to track Correlation ID across async task contexts
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Retrieve the current request's correlation ID."""
    return correlation_id_ctx.get()


def set_correlation_id(corr_id: str | None) -> None:
    """Set the correlation ID for the active request context."""
    correlation_id_ctx.set(corr_id)


class StructuredJSONFormatter(logging.Formatter):
    """
    Format logs as JSON objects for production observability.
    Redacts or excludes sensitive fields (passwords, tokens).
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": settings.ENVIRONMENT,
        }

        # Inject correlation ID if available
        corr_id = get_correlation_id() or getattr(record, "correlation_id", None)
        if corr_id:
            log_entry["correlation_id"] = corr_id

        # Inject contextual request metadata if present
        for attr in ("method", "path", "status_code", "duration_ms", "user_id", "org_id"):
            val = getattr(record, attr, None)
            if val is not None:
                log_entry[attr] = val

        # Handle exceptions safely
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Clean, human-readable log formatter for development."""

    def format(self, record: logging.LogRecord) -> str:
        corr_id = get_correlation_id()
        prefix = f"[{corr_id[:8]}] " if corr_id else ""
        record.msg = f"{prefix}{record.msg}"
        return super().format(record)


def setup_logging() -> None:
    """
    Initialize root logging configuration based on application settings.
    Configures formatters, log level, and optional error tracking services.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)

    if settings.LOG_FORMAT.lower() == "json":
        stream_handler.setFormatter(StructuredJSONFormatter())
    else:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        stream_handler.setFormatter(ConsoleFormatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    root_logger.addHandler(stream_handler)

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Initialize Sentry if configured
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                environment=settings.ENVIRONMENT,
                traces_sample_rate=0.1 if settings.ENVIRONMENT == "production" else 1.0,
                integrations=[FastApiIntegration()],
            )
            logging.getLogger("app.core.logging").info("Sentry monitoring initialized successfully")
        except ImportError:
            logging.getLogger("app.core.logging").warning(
                "SENTRY_DSN was provided but 'sentry-sdk' is not installed. "
                "Error tracking will remain disabled."
            )
