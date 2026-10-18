import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Boolean, Text, Date, Numeric, Integer, UniqueConstraint
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


class POApprovalStepStatus(str, enum.Enum):
    """
    Satın alma siparişi onay adımı durumları:
    - PENDING: Yetkili rolün onayını bekliyor
    - APPROVED: Onaylandı
    - REJECTED: Reddedildi
    """
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


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
    quality_issues: Mapped[list["POQualityIssue"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="POQualityIssue.created_at.desc()",
    )
    approval_steps: Mapped[list["POApprovalStep"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="POApprovalStep.created_at.asc()",
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder {self.po_number} status={self.status}>"


class POApprovalStep(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Satın alma siparişi çok aşamalı onay adımı (Multi-Tier Approval Step).
    Özellikle 250.000 TRY üzerindeki siparişler için Satın Alma Direktörü
    (purchasing_director) ve CFO (cfo) bağımsız onay süreçlerini yönetir.
    """
    __tablename__ = "po_approval_steps"
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "role", name="uq_po_approval_step_po_role"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=POApprovalStepStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="approval_steps")
    approver: Mapped["User | None"] = relationship(lazy="selectin")
    organization: Mapped["Organization"] = relationship()

    def __repr__(self) -> str:
        return f"<POApprovalStep po_id={self.purchase_order_id} role={self.role} status={self.status}>"


class IssueType(str, enum.Enum):
    DEFECT = "defect"
    LATE_DELIVERY = "late_delivery"
    MISSING_ITEMS = "missing_items"
    DOCUMENTATION = "documentation"
    DAMAGED = "damaged"
    OTHER = "other"


class IssueSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    CRITICAL = "critical"


class QualityIssueStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class POQualityIssue(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Satın alma siparişi (PO) kapsamında teslimatta veya incelemede tespit edilen
    kusur, eksik ürün, hasar veya fire/iade kayıtları.
    """
    __tablename__ = "po_quality_issues"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default=IssueSeverity.MEDIUM.value, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=QualityIssueStatus.OPEN.value, nullable=False, index=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="quality_issues")
    supplier: Mapped["Supplier"] = relationship()
    reported_by: Mapped["User | None"] = relationship()
    organization: Mapped["Organization"] = relationship()

    def __repr__(self) -> str:
        return f"<POQualityIssue po_id={self.purchase_order_id} type={self.issue_type} status={self.status} rejections={self.rejection_count}>"
