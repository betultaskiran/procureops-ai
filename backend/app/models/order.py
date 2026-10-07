import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin

class PurchaseOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Onaylanmış bir tekliften (Quote) doğan Satın Alma Siparişi (PO).
    """
    __tablename__ = "purchase_orders"

    po_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="RESTRICT"),
        nullable=False,
    )

    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approvals.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    
    # E-mail simülasyonu için flag
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    quote: Mapped["Quote"] = relationship()
    approval: Mapped["Approval"] = relationship()

    def __repr__(self) -> str:
        return f"<PurchaseOrder {self.po_number} status={self.status}>"
