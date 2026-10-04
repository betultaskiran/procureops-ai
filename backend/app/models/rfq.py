"""
app/models/rfq.py

RFQ (Request for Quotation) ve ham belge yükleme modelleri.

İki model aynı dosyada:
  - RFQ: Tedarik talebinin kendisi (ne istiyoruz, ne zaman)
  - QuoteDocument: RFQ'ya yüklenen ham dosyalar (PDF, Excel, resim)

RFQ → QuoteDocument → Quote (structured extraction) zinciri
Phase 3'te tam olarak işlenecek.

RFQ STATUS AKIŞI:
  draft → collecting_quotes → analyzing → pending_approval
                                              ↓         ↓
                                          approved   rejected
  (herhangi bir aşamada → cancelled)
"""

import enum
import uuid
from datetime import date

from sqlalchemy import String, Boolean, ForeignKey, Integer, Text, Date, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RFQStatus(str, enum.Enum):
    DRAFT = "draft"
    COLLECTING_QUOTES = "collecting_quotes"
    ANALYZING = "analyzing"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ParseStatus(str, enum.Enum):
    """Ham belge işlenme durumu."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileType(str, enum.Enum):
    PDF = "pdf"
    EXCEL = "excel"
    IMAGE = "image"
    EMAIL_TEXT = "email_text"
    OTHER = "other"


class RFQ(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Request for Quotation — Tedarik talebi.

    Bir RFQ: "50 adet dizüstü bilgisayar, 30 Kasım'a kadar teslim"
    Bu RFQ'ya birden fazla tedarikçinin teklifi (Quote) bağlanır.
    """
    __tablename__ = "rfqs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Kaç adet isteniyor?
    required_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Ne zamana kadar teslim edilmeli?
    required_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=RFQStatus.DRAFT,
        index=True,  # "Bekleyen RFQ'ları listele" gibi sorgular sık çalışır
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    organization: Mapped["Organization"] = relationship(back_populates="rfqs")

    created_by: Mapped["User"] = relationship(
        back_populates="rfqs",
        foreign_keys=[created_by_id],
    )

    # Ham yüklenen dosyalar
    quote_documents: Mapped[list["QuoteDocument"]] = relationship(
        back_populates="rfq",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # Structured extraction sonuçları
    quotes: Mapped[list["Quote"]] = relationship(
        back_populates="rfq",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # AI analizleri (birden fazla analiz olabilir: yeni teklif geldiğinde yeniden analiz)
    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="rfq",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<RFQ id={self.id} title={self.title!r} status={self.status!r}>"


class QuoteDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Tedarikçiden alınan ham dosya.

    Bu tablo yüklenen dosyanın metadata'sını tutar.
    Dosyanın içeriği (parse edilmiş metin, extracted quote) ayrı tablolarda.

    Örnek akış:
      PDF yüklendi → QuoteDocument oluştu (status=pending)
      Parsing başladı → status=processing
      LLM extraction tamamlandı → Quote kaydı oluştu, status=completed
    """
    __tablename__ = "quote_documents"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfqs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,  # Yükleme sırasında tedarikçi bilinmeyebilir
        index=True,
    )

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, default=FileType.PDF)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    parse_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ParseStatus.PENDING,
        index=True,
    )

    # Parsing veya extraction hatası olduysa burada saklı
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship(back_populates="quote_documents")
    uploaded_by: Mapped["User"] = relationship(back_populates="uploaded_documents")

    def __repr__(self) -> str:
        return (
            f"<QuoteDocument id={self.id} file={self.file_name!r} "
            f"status={self.parse_status!r}>"
        )
