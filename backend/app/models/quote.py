"""
app/models/quote.py

Structured extraction sonucu — tedarikçi teklifinin normalleştirilmiş hali.

NEDEN QUOTE AYRI BİR TABLODA?
  Ham belge (QuoteDocument): "DEF_Teklif.pdf"
  Structured quote (Quote): {supplier: "DEF", vat: 27000, delivery_days: 7, ...}

  Bu ayrım kritik çünkü:
  1. Aynı PDF'den farklı extraction denemeleri yapılabilir (hata düzeltme)
  2. Quote verisi SQL ile sorgulanır, PDF içeriği sorgulanamaz
  3. Deterministic TCO hesabı Quote alanlarını kullanır

DECIMAL NEDEN ZORUNLU?
  float 0.1 + 0.2 = 0.30000000000000004 üretir.
  Tedarik finansallarında bu kabul edilemez.
  PostgreSQL NUMERIC(14, 4) → Python Decimal → tam aritmetik.

QUOTE ITEM (Kalem Bazlı):
  Bir teklif birden fazla ürün içerebilir:
    - 50 adet laptop  @ 3.500 TRY = 175.000 TRY
    - 50 adet çanta   @   250 TRY =  12.500 TRY
    - Toplam: 187.500 TRY
"""

import uuid
from decimal import Decimal

from sqlalchemy import (
    String, ForeignKey, Integer, Numeric, Text, Boolean, Date, UUID
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Quote(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "quotes"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfqs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        # RESTRICT: Quote varken tedarikçi silinemez. Veri bütünlüğü önemli.
        nullable=False,
        index=True,
    )

    # Hangi ham belgeden extraction yapıldı?
    quote_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quote_documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Finansal Alanlar ──────────────────────────────────────────────────────
    # Tümü Numeric(14, 4): 14 toplam basamak, 4 ondalık.
    # Neden 4 ondalık? Bazı döviz kurları ve vergi hesapları 4+ basamak gerektirir.

    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 4217

    # Ara toplam: KDV ve indirim öncesi
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    # KDV oranı: 0.2000 = %20
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    shipping_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=Decimal("0"))

    # Kurulum, bakım vb. ek maliyetler
    other_costs: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=Decimal("0"))

    # GENEL TOPLAM: subtotal + vat + shipping + other - discount
    # Bu alan deterministic backend tarafından hesaplanır, LLM tarafından değil.
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    # ── Ticari Koşullar ───────────────────────────────────────────────────────
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(200), nullable=True)   # "net-30", "peşin"
    warranty_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_until: Mapped[str | None] = mapped_column(Date, nullable=True)  # Teklifin son geçerlilik tarihi

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Extraction Metadata ───────────────────────────────────────────────────
    extracted_supplier_name: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # LLM'in extraction'a ne kadar güvendiği. 0.0–1.0 arası.
    # Düşük confidence → insan incelemesi gerektirebilir.
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)

    # Verification layer tarafından doldurulur (Phase 10)
    is_compliant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship(back_populates="quotes")
    supplier: Mapped["Supplier"] = relationship(back_populates="quotes")
    items: Mapped[list["QuoteItem"]] = relationship(
        back_populates="quote",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Quote id={self.id} supplier_id={self.supplier_id} "
            f"total={self.total_price} {self.currency}>"
        )


class QuoteItem(Base, UUIDPrimaryKeyMixin):
    """
    Teklif içindeki her bir kalem (satır).

    Örnekler:
      line 1: 50 × Laptop HP Pavilion @ 4.500 TRY = 225.000 TRY
      line 2: 50 × Çanta             @   300 TRY =  15.000 TRY

    Kalem bazlı karşılaştırma Phase 4'te TCO hesabına dahil edilecek.
    TimestampMixin yok — bir Quote'a bağlı, bağımsız yaşam döngüsü yok.
    """
    __tablename__ = "quote_items"

    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)

    # Numeric(12, 4): ondalık miktarlar için (2.5 kg, 0.5 m² gibi)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "adet", "kg", "m²"

    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    quote: Mapped["Quote"] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return (
            f"<QuoteItem quote_id={self.quote_id} "
            f"line={self.line_number} desc={self.description[:30]!r}>"
        )
