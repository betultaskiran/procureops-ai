"""
app/services/email/__init__.py

Public interfaces for Phase 9 Reliable Email Integration.
"""

from app.services.email.base import EmailMessage, EmailSendResult, EmailProvider
from app.services.email.factory import get_email_provider, set_email_provider
from app.services.email.mock_provider import MockEmailProvider
from app.services.email.smtp_provider import SMTPEmailProvider
from app.services.email.console_provider import ConsoleEmailProvider
from app.services.email.renderer import (
    validate_email_address,
    EmailValidationError,
    render_rfq_invitation,
    render_po_notification,
)
from app.services.email.service import EmailDeliveryService
from app.services.email.worker import process_outbox_batch, run_worker_loop

__all__ = [
    "EmailMessage",
    "EmailSendResult",
    "EmailProvider",
    "get_email_provider",
    "set_email_provider",
    "SMTPEmailProvider",
    "MockEmailProvider",
    "ConsoleEmailProvider",
    "validate_email_address",
    "EmailValidationError",
    "render_rfq_invitation",
    "render_po_notification",
    "EmailDeliveryService",
    "process_outbox_batch",
    "run_worker_loop",
]
