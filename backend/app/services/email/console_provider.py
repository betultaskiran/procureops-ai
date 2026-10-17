"""
app/services/email/console_provider.py

Console email provider that logs sanitized email notifications to stdout.
"""

import logging
import uuid
from app.services.email.base import EmailMessage, EmailProvider, EmailSendResult

logger = logging.getLogger("app.email.console")


class ConsoleEmailProvider(EmailProvider):
    """Outputs sanitized email metadata to logs without external network requests."""

    async def send_email(self, message: EmailMessage) -> EmailSendResult:
        msg_id = f"<console-{uuid.uuid4().hex[:12]}@procureops.local>"
        logger.info(
            f"[CONSOLE EMAIL] To: {message.recipient_email} | Subject: {message.subject} | ID: {msg_id}"
        )
        return EmailSendResult(
            success=True,
            provider_message_id=msg_id,
            is_transient=False,
            error_message=None,
        )
