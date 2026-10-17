"""
app/services/email/mock_provider.py

In-memory mock email provider for deterministic testing without external SMTP connections.
"""

import uuid
from app.services.email.base import EmailMessage, EmailProvider, EmailSendResult


class MockEmailProvider(EmailProvider):
    """
    Mock email provider for automated test suites and local testing.
    Records all dispatched emails and provides programmable failure hooks.
    """

    def __init__(self):
        self.sent_messages: list[EmailMessage] = []
        self.force_transient_failure: bool = False
        self.force_permanent_failure: bool = False
        self.fail_until_attempt: int = 0
        self.current_attempt: int = 0
        self.last_error_message: str | None = None

    async def send_email(self, message: EmailMessage) -> EmailSendResult:
        self.current_attempt += 1

        if self.force_permanent_failure:
            return EmailSendResult(
                success=False,
                is_transient=False,
                error_message=self.last_error_message or "Permanent delivery refusal simulated by mock.",
            )

        if self.force_transient_failure:
            return EmailSendResult(
                success=False,
                is_transient=True,
                error_message=self.last_error_message or "Transient network timeout simulated by mock.",
            )

        if self.current_attempt <= self.fail_until_attempt:
            return EmailSendResult(
                success=False,
                is_transient=True,
                error_message=f"Transient failure on attempt {self.current_attempt} (retries scheduled).",
            )

        # Successful transmission
        self.sent_messages.append(message)
        return EmailSendResult(
            success=True,
            provider_message_id=f"<mock-{uuid.uuid4().hex[:12]}@procureops.local>",
            is_transient=False,
            error_message=None,
        )

    def reset(self):
        """Reset all in-memory mock state."""
        self.sent_messages.clear()
        self.force_transient_failure = False
        self.force_permanent_failure = False
        self.fail_until_attempt = 0
        self.current_attempt = 0
        self.last_error_message = None
