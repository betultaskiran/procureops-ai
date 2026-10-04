"""
app/models/audit.py

Sistem genelinde denetim izi (audit trail).

Bu tablo sistemde olan her şeyi kaydeder:
  - Belge yükleme
  - AI araç çağrıları
  - Migration başlatma
  - Onay/ret kararları
  - Ayar değişiklikleri

NEDEN AUDIT LOG ÖNEMLİ?
  Satın alma kararlarında hesap verebilirlik zorunludur:
  "Bu öneriyi kim oluşturdu? Hangi araçları kullandı?
   Hangi politika maddesine dayandı? Kim onayladı? Ne zaman?"

  Bu soruların cevabı AuditEvent tablosundadır.

PAYLOAD (JSONB):
  Her event'in ek detayları farklı. Örneğin:
    tool_called   → {"tool": "calculate_tco", "quote_id": "...", "result": {...}}
    approval_given → {"previous_status": "pending", "new_status": "approved"}
  
  JSONB: Binary JSON — PostgreSQL'de JSON'u index'leyip sorgulayabilirsin.
"""

import uuid

from sqlalchemy import String, ForeignKey, UUID, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class AuditEvent(Base, UUIDPrimaryKeyMixin):
    """
    Değişmez audit kaydı. Bir AuditEvent asla güncellenmez, sadece eklenir.

    TimestampMixin kullanmıyoruz (updated_at yoktur — audit kayıtları
    değiştirilemez). Sadece created_at mixin'den ayrı ekledik.

    Neden ayrı? created_at bu tabloda server_default=func.now() ile
    veritabanı tarafında atanır. Python'dan göndermeye gerek yok.
    """
    __tablename__ = "audit_events"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Hangi kullanıcı bu eventi tetikledi? (None = system action)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Event tipi — arama ve filtreleme için standart değerler kullanılmalı
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    # Örnekler: "document_uploaded", "analysis_started", "tool_called",
    #           "recommendation_generated", "approval_given", "settings_changed"

    # Hangi entity etkilendi?
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Ek detaylar — farklı event tipleri için farklı yapı
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # IP adresi — güvenlik auditı için (Phase 15)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max 45 karakter

    # created_at — veritabanı server_default ile atanır, değiştirilemez
    # TimestampMixin kullanmadık çünkü updated_at istemiyoruz
    from datetime import datetime
    from sqlalchemy import DateTime, func
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Composite Index ───────────────────────────────────────────────────────
    # "Bu RFQ'ya ait tüm audit eventlerini göster" sorgusu sık çalışır:
    #   WHERE entity_type = 'rfq' AND entity_id = '...'
    # Bu sorguyu hızlandırmak için composite index.
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    actor: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<AuditEvent type={self.event_type!r} "
            f"entity={self.entity_type}:{self.entity_id}>"
        )
