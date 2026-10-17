"""
app/services/email/base.py

Abstract base contracts and data structures for outbound email integration (Phase 9).
"""

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class EmailMessage(BaseModel):
    """Normalized email payload sent to an EmailProvider."""
    recipient_email: str
    recipient_name: str | None = None
    subject: str
    text_body: str
    html_body: str | None = None
    reply_to: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class EmailSendResult(BaseModel):
    """
    Result returned by an EmailProvider.

    Important:
      - `success == True` means the provider/SMTP transport accepted the message
        (socket handshake + 250 OK). It does NOT imply the email was delivered to
        the user's inbox; delivery status is tracked separately via webhooks.
      - `is_transient == True` means the error is recoverable (network timeout,
        temporary server unavailability) and eligible for backoff retry.
    """
    success: bool
    provider_message_id: str | None = None
    is_transient: bool = False
    error_message: str | None = None


class EmailProvider(ABC):
    """Abstract interface for all email delivery backends."""

    @abstractmethod
    async def send_email(self, message: EmailMessage) -> EmailSendResult:
        """
        Deliver or transmit an email message.

        Must never raise unhandled network exceptions to callers; instead,
        wrap errors into `EmailSendResult(success=False, is_transient=..., error_message=...)`.
        Must never leak passwords or authentication tokens in `error_message`.
        """
        pass
