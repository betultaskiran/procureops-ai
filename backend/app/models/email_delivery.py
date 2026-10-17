"""
app/models/email_delivery.py

Persistent Outbox Model for reliable asynchronous email delivery, idempotency tracking,
and audit trail (Phase 9).
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    ForeignKey,
    DateTime,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class EmailDeliveryStatus(str, enum.Enum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class EmailMessageType(str, enum.Enum):
    RFQ_INVITATION = "rfq_invitation"
    PO_ISSUANCE = "po_issuance"
    SYSTEM_NOTIFICATION = "system_notification"


class EmailDelivery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Durable outbox record for all outbound emails.

    Guarantees:
      - Unique idempotency_key prevents duplicate email tasks across concurrent requests.
      - Explicit state transitions: queued -> sending -> sent (or failed) -> delivered.
      - Retries transient failures with bounded exponential backoff.
      - Never marks as 'delivered' solely because SMTP accepted the socket transmission.
    """
    __tablename__ = "email_deliveries"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    rfq_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfqs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    recipient_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    message_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=EmailMessageType.RFQ_INVITATION.value,
        index=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=EmailDeliveryStatus.QUEUED.value,
        index=True,
    )

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    organization: Mapped["Organization"] = relationship()
    rfq: Mapped["RFQ | None"] = relationship(back_populates="email_deliveries")
    supplier: Mapped["Supplier | None"] = relationship()
    purchase_order: Mapped["PurchaseOrder | None"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<EmailDelivery id={self.id} type={self.message_type!r} "
            f"to={self.recipient_email!r} status={self.status!r}>"
        )
