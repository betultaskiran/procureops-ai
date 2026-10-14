"""
app/models/supplier.py

Tedarikçi ve tedarikçi geçmiş kayıtları.

İki model aynı dosyada çünkü SupplierHistory, Supplier'dan bağımsız
anlam taşımaz — tightly coupled.

TASARIM NOTU:
  Tedarikçi geçmişi SQL'de tutulur, vektör veritabanında değil.
  Neden? "Bu tedarikçinin son 12 aydaki ortalama gecikme süresi nedir?"
  sorusu tam olarak bir SQL aggregation sorusudur:
    SELECT AVG(delay_days) FROM supplier_history
    WHERE supplier_id = ? AND order_date > now() - interval '12 months'
  RAG bunu yapamaz. SQL bunu mükemmel yapar.
"""

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import String, Boolean, ForeignKey, Integer, Numeric, Date, Text, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Supplier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "suppliers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(300), nullable=False)

    # Opsiyonel iletişim bilgileri
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    organization: Mapped["Organization"] = relationship(back_populates="suppliers")

    history: Mapped[list["SupplierHistory"]] = relationship(
        back_populates="supplier",
        lazy="selectin",
        cascade="all, delete-orphan",  # Tedarikçi silinirse geçmişi de silinir
    )
    quotes: Mapped[list["Quote"]] = relationship(back_populates="supplier")

    def __repr__(self) -> str:
        return f"<Supplier id={self.id} name={self.name!r}>"


class SupplierHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Bir tedarikçinin geçmiş siparişlerinden her biri bir satır.

    Bu tablo Phase 8'de detaylı sorgulanacak. Şimdilik sadece yapıyı tanımlıyoruz.

    Önemli alanlar:
      delay_days: negatif = erken teslimat, pozitif = geç teslimat, 0 = tam zamanında
      quality_issues: teslimatta tespit edilen kalite sorunları sayısı
      rejection_count: tamamen reddedilen ürün/sipariş sayısı
    """
    __tablename__ = "supplier_history"

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # İsteğe bağlı dahili PO bağlantısı (platform üzerinden oluşturulan siparişler için)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Sipariş referansı: PO numarası, sözleşme numarası vb.
    order_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    promised_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivered_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Numeric(12, 2): 12 toplam basamak, 2 ondalık.
    # Neden Numeric ve float değil? Monetary değerlerde float kullanmak
    # yuvarlama hatalarına yol açar. PostgreSQL NUMERIC tam aritmetik yapar.
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 4217: TRY, USD, EUR

    quantity_ordered: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Teslimat gecikmesi (gün). None = henüz teslim edilmedi.
    delay_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    quality_issues: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejection_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    supplier: Mapped["Supplier"] = relationship(back_populates="history")
    purchase_order: Mapped["PurchaseOrder | None"] = relationship(
        back_populates="supplier_history_entry",
    )

    def __repr__(self) -> str:
        return (
            f"<SupplierHistory supplier_id={self.supplier_id} "
            f"order_ref={self.order_reference!r} delay={self.delay_days}>"
        )
