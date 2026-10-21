"""
app/services/email/smtp_provider.py

Standard SMTP email provider using Python's standard library (smtplib, ssl, email)
executed asynchronously via thread pool.
"""

import asyncio
import email.utils
import logging
import smtplib
import socket
import ssl
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.services.email.base import EmailMessage, EmailProvider, EmailSendResult

logger = logging.getLogger("app.email.smtp")


class SMTPEmailProvider(EmailProvider):
    """
    Standard SMTP Provider supporting STARTTLS, direct SSL, authentication,
    and timeout handling.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        use_tls: bool | None = None,
        use_ssl: bool | None = None,
        timeout: int | None = None,
    ):
        self.host = host if host is not None else settings.SMTP_HOST
        self.port = port if port is not None else settings.SMTP_PORT
        self.username = username if username is not None else settings.SMTP_USER
        self.password = password if password is not None else settings.SMTP_PASSWORD
        self.from_email = from_email if from_email is not None else settings.SMTP_FROM_EMAIL
        self.from_name = from_name if from_name is not None else settings.SMTP_FROM_NAME
        self.use_tls = use_tls if use_tls is not None else settings.SMTP_USE_TLS
        self.use_ssl = use_ssl if use_ssl is not None else settings.SMTP_USE_SSL
        self.timeout = timeout if timeout is not None else settings.SMTP_TIMEOUT

    async def send_email(self, message: EmailMessage) -> EmailSendResult:
        """Asynchronously dispatches message to SMTP server in a worker thread."""
        return await asyncio.to_thread(self._sync_send, message)

    def _sync_send(self, message: EmailMessage) -> EmailSendResult:
        """Synchronous SMTP transmission with comprehensive error classification."""
        # Validate configuration
        if not self.host or not str(self.host).strip():
            err = "SMTP configuration error: Host is missing or not configured."
            logger.error(f"[SMTP] {err}")
            return EmailSendResult(success=False, is_transient=False, error_message=err)

        if not self.port or not isinstance(self.port, int) or self.port <= 0 or self.port > 65535:
            err = f"SMTP configuration error: Invalid port '{self.port}'."
            logger.error(f"[SMTP] {err}")
            return EmailSendResult(success=False, is_transient=False, error_message=err)

        client = None
        message_id = f"<{uuid.uuid4()}@{socket.getfqdn()}>"

        try:
            # 1. Build MIME Message
            mime_msg = MIMEMultipart("alternative")
            mime_msg["Message-ID"] = message_id
            mime_msg["Date"] = email.utils.formatdate(localtime=True)
            mime_msg["Subject"] = message.subject
            
            # Format From header with name if present
            if self.from_name:
                mime_msg["From"] = f"{self.from_name} <{self.from_email}>"
            else:
                mime_msg["From"] = self.from_email

            # Format To header
            if message.recipient_name:
                mime_msg["To"] = f"{message.recipient_name} <{message.recipient_email}>"
            else:
                mime_msg["To"] = message.recipient_email

            if message.reply_to:
                mime_msg["Reply-To"] = message.reply_to

            # Extra custom headers
            for header_key, header_val in message.headers.items():
                mime_msg[header_key] = header_val

            # Attach plain text
            mime_msg.attach(MIMEText(message.text_body, "plain", "utf-8"))

            # Attach HTML if provided
            if message.html_body:
                mime_msg.attach(MIMEText(message.html_body, "html", "utf-8"))

            # 2. Connect to SMTP server
            if self.use_ssl:
                context = ssl.create_default_context()
                client = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
            else:
                client = smtplib.SMTP(self.host, self.port, timeout=self.timeout)

            # EHLO / HELO
            client.ehlo()

            # STARTTLS
            if self.use_tls and not self.use_ssl:
                context = ssl.create_default_context()
                client.starttls(context=context)
                client.ehlo()

            # Authenticate if credentials provided
            if self.username and self.password:
                client.login(self.username, self.password)

            # Send mail
            client.send_message(mime_msg)
            
            logger.info(
                f"[SMTP] Email accepted by server: msg_id={message_id} recipient={message.recipient_email}"
            )
            return EmailSendResult(
                success=True,
                provider_message_id=message_id,
                is_transient=False,
                error_message=None,
            )

        except (
            smtplib.SMTPServerDisconnected,
            smtplib.SMTPConnectError,
            socket.timeout,
            TimeoutError,
            ConnectionRefusedError,
            ConnectionResetError,
            OSError,
        ) as exc:
            err = self._sanitize_error(f"Network/connection failure: {type(exc).__name__} - {exc}")
            logger.warning(f"[SMTP] Transient failure for {message.recipient_email}: {err}")
            return EmailSendResult(
                success=False,
                is_transient=True,
                error_message=err,
            )

        except smtplib.SMTPResponseException as exc:
            code = exc.smtp_code
            err = self._sanitize_error(f"SMTP error {code}: {exc.smtp_error.decode('utf-8', 'ignore') if isinstance(exc.smtp_error, bytes) else exc.smtp_error}")
            # 4xx are transient, 5xx are permanent
            is_transient = (400 <= code < 500)
            logger.warning(f"[SMTP] Server response {code} (transient={is_transient}): {err}")
            return EmailSendResult(
                success=False,
                is_transient=is_transient,
                error_message=err,
            )

        except smtplib.SMTPAuthenticationError as exc:
            err = "SMTP Authentication failed. Verify server credentials."
            logger.error(f"[SMTP] Authentication failure: {err}")
            return EmailSendResult(
                success=False,
                is_transient=False,
                error_message=err,
            )

        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
            err = self._sanitize_error(f"Recipient/Sender rejected: {exc}")
            logger.error(f"[SMTP] Permanent refusal: {err}")
            return EmailSendResult(
                success=False,
                is_transient=False,
                error_message=err,
            )

        except Exception as exc:
            err = self._sanitize_error(f"Unexpected transmission error: {type(exc).__name__} - {exc}")
            logger.error(f"[SMTP] Error: {err}")
            return EmailSendResult(
                success=False,
                is_transient=False,
                error_message=err,
            )

        finally:
            if client is not None:
                try:
                    client.quit()
                except Exception:
                    pass

    def _sanitize_error(self, raw_error: str) -> str:
        """Sanitizes error string to prevent password or secret leaks."""
        sanitized = raw_error
        if self.password and len(self.password) > 3:
            sanitized = sanitized.replace(self.password, "[REDACTED]")
        if self.username:
            sanitized = sanitized.replace(self.username, "[REDACTED_USER]")
        return sanitized
