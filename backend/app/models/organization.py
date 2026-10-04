"""
app/models/organization.py

Organization = Şirket/Kuruluş. Çok kiracılı (multi-tenant) bir sistemde
her kullanıcı, tedarikçi, RFQ ve politika belgesi bir organization'a aittir.

Phase 12'de authentication eklendiğinde, "bu kullanıcı bu organization'a
erişebilir mi?" sorusunu buradaki ilişki üzerinden cevaplayacağız.
"""

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"

    # VARCHAR — Pydantic validator'ı bunu 3-200 karakter arasında kısıtlayacak
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Slug: URL-safe isim. Örn: "acme-corp". Benzersiz olmalı.
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    # back_populates: her iki taraf da birbirini bilir (bidirectional)
    # lazy="selectin": async SQLAlchemy'de lazy loading çalışmaz.
    # selectin loading → SQLAlchemy ayrı bir SELECT ile ilişkili kayıtları
    # otomatik yükler. Bu Phase 3+'ta açıklanacak.
    users: Mapped[list["User"]] = relationship(
        back_populates="organization", lazy="selectin"
    )
    suppliers: Mapped[list["Supplier"]] = relationship(
        back_populates="organization", lazy="selectin"
    )
    rfqs: Mapped[list["RFQ"]] = relationship(
        back_populates="organization", lazy="selectin"
    )
    policy_documents: Mapped[list["PolicyDocument"]] = relationship(
        back_populates="organization", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id} name={self.name!r}>"
