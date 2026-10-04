"""
app/models/policy_document.py

Şirket politika belgeleri — RAG sisteminin besleneceği kaynak.

Bu modeldeki belgeler Phase 5'te:
  1. Parse edilir (metin çıkarılır)
  2. Chunk'lara bölünür
  3. Embedding'e dönüştürülür
  4. Qdrant'a yüklenir

Bu tablo o sürecin durumunu takip eder:
  - Belge yüklendi mi? ✓
  - Chunk'lara bölündü mü? ✓ / chunk_count = 42
  - Qdrant'ta hangi collection'da? "procurement_policies"
"""

import enum
import uuid

from sqlalchemy import String, Boolean, ForeignKey, Integer, Text, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentType(str, enum.Enum):
    """RAG sistemine yüklenecek belge tipleri."""
    PROCUREMENT_POLICY = "procurement_policy"
    SLA = "sla"
    CODE_OF_CONDUCT = "code_of_conduct"
    FRAMEWORK_AGREEMENT = "framework_agreement"
    CONTRACT = "contract"
    LEGAL = "legal"
    OTHER = "other"


class PolicyDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "policy_documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,  # Kullanıcı silinirse belge orphan kalmasın
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    document_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DocumentType.OTHER,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── RAG Durumu ────────────────────────────────────────────────────────────
    # Bu alanlar Phase 5'te doldurulacak.

    # Belge Qdrant'a yüklendi mi?
    is_chunked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Kaç chunk üretildi? (Debug ve monitoring için yararlı)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Hangi Qdrant collection'ında? Her org kendi collection'ını kullanabilir.
    qdrant_collection: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Chunklama sırasında hata olduysa buraya yazılır
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    organization: Mapped["Organization"] = relationship(
        back_populates="policy_documents"
    )
    uploaded_by: Mapped["User"] = relationship(foreign_keys=[uploaded_by_id])

    def __repr__(self) -> str:
        return f"<PolicyDocument id={self.id} title={self.title!r} chunked={self.is_chunked}>"
