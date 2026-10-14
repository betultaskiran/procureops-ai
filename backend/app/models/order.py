import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Boolean, Text, Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class PurchaseOrderStatus(str, enum.Enum):
    """
    Satın alma siparişi (PO) yaşam döngüsü durumları:
    - DRAFT: Taslak sipariş emri
    - ISSUED: Tedarikçiye iletilmiş / onaylanmış sipariş
    - DELIVERED: Mal/hizmet teslim alındı (fiilî teslim tarihi girildi)
    - COMPLETED: Teslimat doğrulandı, fatura/ödemesi kesinleşti
    - CANCELLED: İptal edildi
    """
    DRAFT = "draft"
    ISSUED = "issued"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


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

    status: Mapped[str] = mapped_column(String(20), default=PurchaseOrderStatus.DRAFT.value, nullable=False)
    
    # E-mail simülasyonu için flag
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # İptal alanları
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Phase 4A: Teslimat ve İcra Takip Alanları (Nullable / Backward-compatible) ──
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    delivery_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    quote: Mapped["Quote"] = relationship()
    approval: Mapped["Approval"] = relationship()
    supplier_history_entry: Mapped["SupplierHistory | None"] = relationship(
        back_populates="purchase_order",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder {self.po_number} status={self.status}>"
