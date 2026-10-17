"""
app/services/email/factory.py

Factory for resolving the active EmailProvider based on settings or test overrides.
"""

from app.core.config import settings
from app.services.email.base import EmailProvider
from app.services.email.console_provider import ConsoleEmailProvider
from app.services.email.mock_provider import MockEmailProvider
from app.services.email.smtp_provider import SMTPEmailProvider

_active_provider: EmailProvider | None = None


def get_email_provider() -> EmailProvider:
    """
    Returns the configured EmailProvider singleton or a test override.
    """
    global _active_provider
    if _active_provider is not None:
        return _active_provider

    backend = settings.EMAIL_BACKEND.lower().strip()
    if backend == "mock":
        _active_provider = MockEmailProvider()
    elif backend == "console":
        _active_provider = ConsoleEmailProvider()
    elif backend == "smtp":
        _active_provider = SMTPEmailProvider()
    else:
        # Fallback to SMTP
        _active_provider = SMTPEmailProvider()

    return _active_provider


def set_email_provider(provider: EmailProvider | None) -> None:
    """
    Sets a global email provider override (used by test suites).
    Pass None to reset back to configuration-based initialization.
    """
    global _active_provider
    _active_provider = provider
