"""
app/models/user.py

Kullanıcı modeli ve rol tanımları.

ENUM KARARI (ADR-009):
  Python enum.Enum kullanıyoruz, PostgreSQL ENUM tipi değil.
  Neden? PostgreSQL ENUM'u değiştirmek zordur. Yeni değer eklemek bile
  migration gerektirir. VARCHAR + uygulama seviyesi validation çok daha
  esnektir ve Alembic ile daha iyi çalışır.

  str mixin'i: UserRole.ADMIN == "admin" → True
  Bu sayede JSON serializasyon, veritabanı storage ve karşılaştırmalar
  herhangi bir dönüşüm gerektirmez.
"""

import enum
import uuid

from sqlalchemy import String, Boolean, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    """
    Kullanıcı rolleri. str mixin'i sayesinde:
        UserRole.ADMIN         → "admin"
        str(UserRole.ADMIN)    → "admin"
        UserRole("admin")      → UserRole.ADMIN

    Veritabanında VARCHAR olarak saklanır: "admin", "manager", vb.
    Yeni bir rol eklenmesi sadece buraya yeni bir satır eklemek demek.
    """
    ADMIN = "admin"
    MANAGER = "manager"                  # Procurement Manager — onay yetkisi var
    EMPLOYEE = "employee"                # Procurement Employee — analiz yapabilir
    VIEWER = "viewer"                    # Sadece görüntüleme
    PURCHASING_DIRECTOR = "purchasing_director"  # Satın Alma Direktörü — 250k TL üzeri onay
    CFO = "cfo"                          # CFO — 250k TL üzeri onay


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Sık sorgulanan FK'lar index'lenmeli
    )

    email: Mapped[str] = mapped_column(
        String(320),  # RFC 5321 maksimum email uzunluğu
        unique=True,
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # hashed_password: Phase 12'de doldurulacak.
    # Şimdilik nullable — şifresiz kullanıcı oluşturulabilir (dev ortamı için).
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Rol: veritabanında "admin", "manager", "purchasing_director", "cfo" vb. string olarak saklanır.
    # Python'da UserRole enum'u olarak kullanılır.
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=UserRole.EMPLOYEE,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    organization: Mapped["Organization"] = relationship(back_populates="users")

    rfqs: Mapped[list["RFQ"]] = relationship(
        back_populates="created_by", foreign_keys="RFQ.created_by_id"
    )
    approvals: Mapped[list["Approval"]] = relationship(back_populates="reviewer")
    uploaded_documents: Mapped[list["QuoteDocument"]] = relationship(
        back_populates="uploaded_by"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
