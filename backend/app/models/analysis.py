"""
app/models/analysis.py

AI analiz süreci ve çıktıları.

Bu dosyadaki modeller Phase 9 (Agent) ve Phase 10 (Verification)'da
aktif olarak kullanılacak. Şimdi sadece şemayı tanımlıyoruz.

MODEL HİYERARŞİSİ:
  Analysis              ← Ana analiz kaydı (durum takibi)
    ├── TCOResult       ← Her teklif için deterministic maliyet hesabı
    ├── ComplianceCheck ← Her teklif için kural doğrulaması
    ├── EvidenceItem    ← Her öneriyi destekleyen kaynak atıfı
    ├── Recommendation  ← LLM öneri + doğrulama durumu
    └── Approval        ← İnsan onayı

TASARIM PRENSİBİ:
  Bir RFQ birden fazla Analysis'e sahip olabilir.
  Neden? Yeni bir teklif geldiğinde veya politika değiştiğinde
  yeniden analiz yapılabilir. Önceki analizler silinmez — audit trail korunur.
"""

import enum
import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import String, ForeignKey, Integer, Numeric, Text, Boolean, DateTime, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ComplianceResult(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


class EvidenceSourceType(str, enum.Enum):
    QUOTE = "quote"                      # Teklif belgesinden alınan veri
    POLICY = "policy"                    # Politika dokümanından alınan madde
    SUPPLIER_HISTORY = "supplier_history"  # SQL'den gelen geçmiş veri
    CALCULATION = "calculation"          # Deterministic hesap sonucu


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"        # Deterministik kontroller geçti
    OVERRIDDEN = "overridden"    # LLM öneri kurallarla çakıştı, override edildi
    FAILED = "failed"            # Kritik kural ihlali


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    EXCEPTION_REQUESTED = "exception_requested"
    EXCEPTION_APPROVED = "exception_approved"


class Analysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Bir RFQ için yapılan AI analizi.

    Agent bu kaydı oluşturduktan sonra araçları çağırır
    ve sonuçları ilgili alt tablolara yazar.
    """
    __tablename__ = "analyses"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfqs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AnalysisStatus.PENDING,
        index=True,
    )

    # Hata durumunda mesaj
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship(back_populates="analyses")

    tco_results: Mapped[list["TCOResult"]] = relationship(
        back_populates="analysis",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    compliance_checks: Mapped[list["ComplianceCheck"]] = relationship(
        back_populates="analysis",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="analysis",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    recommendation: Mapped["Recommendation | None"] = relationship(
        back_populates="analysis",
        uselist=False,  # Bir analizin tek bir öneri kaydı var
        cascade="all, delete-orphan",
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="analysis",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Analysis id={self.id} rfq_id={self.rfq_id} status={self.status!r}>"


class TCOResult(Base, UUIDPrimaryKeyMixin):
    """
    Bir teklif için deterministic Toplam Sahip Olma Maliyeti hesabı.

    ÖNEMLI: Bu değerler Python backend kodu tarafından hesaplanır.
    LLM bu sayıları üretmez. LLM sonuçları açıklar.

    TimestampMixin yok — Analysis'in bir parçası, bağımsız yaşam döngüsü yok.
    """
    __tablename__ = "tco_results"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Hesap bileşenleri (tümü Decimal — float değil)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    other_costs: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    total_tco: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # Hesap adımlarının insan-okunabilir açıklaması (audit için)
    calculation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    analysis: Mapped["Analysis"] = relationship(back_populates="tco_results")
    quote: Mapped["Quote"] = relationship()

    def __repr__(self) -> str:
        return f"<TCOResult quote_id={self.quote_id} total_tco={self.total_tco} {self.currency}>"


class ComplianceCheck(Base, UUIDPrimaryKeyMixin):
    """
    Bir teklif için tek bir iş kuralı doğrulaması.

    Örnek satırlar:
      rule_name="minimum_warranty"  result="fail"   actual="12" required="24"
      rule_name="delivery_deadline" result="pass"   actual="7"  required="30"
      rule_name="minimum_quotes"    result="pass"   actual="3"  required="3"

    Bu tablo deterministic — LLM yazmaz.
    """
    __tablename__ = "compliance_checks"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=True,  # Bazı kurallar teklif bazlı değil, RFQ bazlıdır
    )

    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_description: Mapped[str] = mapped_column(String(500), nullable=False)

    result: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )  # "pass" | "fail" | "warning"

    # Bulunan değer vs istenen değer
    actual_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    required_value: Mapped[str | None] = mapped_column(String(200), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    analysis: Mapped["Analysis"] = relationship(back_populates="compliance_checks")

    def __repr__(self) -> str:
        return (
            f"<ComplianceCheck rule={self.rule_name!r} "
            f"result={self.result!r} actual={self.actual_value!r}>"
        )


class EvidenceItem(Base, UUIDPrimaryKeyMixin):
    """
    Öneriyi destekleyen her bir kaynak atıfı.

    ÖNEMLI: Bu tablo hiç uydurulmuş veri içermez.
    Her kayıt gerçek bir kaynağa işaret eder:
      - Bir teklif sayfasındaki değer
      - Bir politika belgesindeki madde
      - SQL'den çekilen geçmiş veri
      - Deterministik bir hesap sonucu

    Bu tablo, "LLM bunu nereden söylüyor?" sorusunun cevabıdır.
    """
    __tablename__ = "evidence_items"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Örnek: "DEF_Teklif.pdf, sayfa 2" veya "Satın Alma Politikası, Madde 3.1"
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)

    # Bu kanıt ne iddiayı destekliyor?
    claim: Mapped[str] = mapped_column(Text, nullable=False)

    # Gerçek içerik/değer
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    analysis: Mapped["Analysis"] = relationship(back_populates="evidence_items")

    def __repr__(self) -> str:
        return (
            f"<EvidenceItem type={self.source_type!r} "
            f"ref={self.source_reference[:50]!r}>"
        )


class Recommendation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    LLM'in ürettiği öneri + deterministik doğrulama sonucu.

    Analysis başına tek bir Recommendation olur (uselist=False).

    verification_status alanı kritik:
      VERIFIED   → Deterministik kurallar LLM önerisini onayladı
      OVERRIDDEN → LLM "uyumlu" dedi ama kural motoru "uyumsuz" buldu
                   → Sistem LLM'i override eder, kural motorunun kararı geçerli
    """
    __tablename__ = "recommendations"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # Analysis başına tek recommendation
    )

    # Önerilen teklif (None = hiçbir teklif uygun değil)
    recommended_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # LLM tarafından üretilen metin
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternative_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Doğrulama katmanı tarafından doldurulur
    verification_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=VerificationStatus.PENDING,
    )
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    analysis: Mapped["Analysis"] = relationship(back_populates="recommendation")
    recommended_quote: Mapped["Quote | None"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<Recommendation analysis_id={self.analysis_id} "
            f"verification={self.verification_status!r}>"
        )


class Approval(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    İnsan onay kaydı. Human-in-the-loop mimarisinin veritabanı yansıması.

    Bir Analysis birden fazla Approval kaydına sahip olabilir:
      1. Çalışan inceledi → revision_requested
      2. Düzeltme yapıldı
      3. Yönetici inceledi → approved

    reviewed_at: None ise henüz incelenmedi (karar verilmedi).
    """
    __tablename__ = "approvals"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=ApprovalStatus.PENDING,
        index=True,
    )

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # İnisiyatif (Exception) kullanımı durumunda seçilen özel teklif
    selected_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Politikaya aykırı olduğunu bilerek onaylama bayrağı
    acknowledged_policy_violation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Karar verilen zaman (None = henüz karar verilmedi)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    analysis: Mapped["Analysis"] = relationship(back_populates="approvals")
    reviewer: Mapped["User"] = relationship(back_populates="approvals")

    def __repr__(self) -> str:
        return (
            f"<Approval analysis_id={self.analysis_id} "
            f"status={self.status!r} reviewer_id={self.reviewer_id}>"
        )
