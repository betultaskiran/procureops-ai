"""
app/models/base.py

SQLAlchemy 2.0 declarative base ve paylaşılan mixin'ler.

Buradaki iki sınıf tüm model dosyaları tarafından import edilir:
  - Base       → tüm model class'ları bunu extend eder
  - TimestampMixin → created_at / updated_at kolonlarını otomatik ekler
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, UUID, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    SQLAlchemy'nin modern (2.0+) declarative base sınıfı.

    Tüm model class'ları şunu yazar:
        class MyModel(Base):
            __tablename__ = "my_models"
            ...

    Bu sayede SQLAlchemy, Base.metadata'da tüm tabloları bilir.
    Alembic bu metadata'yı okuyarak migration'ları otomatik üretir.
    """
    pass


class TimestampMixin:
    """
    created_at ve updated_at kolonlarını her modele ekler.

    Mixin pattern: Kalıtım yerine "mix in" — birden fazla class'a
    aynı alanları/davranışları eklemek için kullanılan bir Python pattern'i.

    Kullanım:
        class RFQ(Base, TimestampMixin):
            ...
    Bu kadar — created_at ve updated_at otomatik eklenir.

    server_default=func.now():
        INSERT sırasında PostgreSQL sunucusu NOW() değerini atar.
        Python'dan değer göndermene gerek yok.

    onupdate=func.now():
        ORM üzerinden UPDATE yapıldığında SQLAlchemy, SET sorgusuna
        updated_at = now() ekler.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """
    UUID primary key ekler. Neden UUID?

    - Sequential integer ID'ler sızdırılabilir:
        /api/rfqs/1, /api/rfqs/2 → "toplam kaç RFQ var?" belli oluyor
    - UUID tahmin edilemez → daha güvenli URL'ler
    - Dağıtık sistemlerde çakışma riski neredeyse sıfır

    default=uuid.uuid4:
        Yeni kayıt oluşturulduğunda Python tarafında UUID üretilir.
        Veritabanı bu değeri alır (gen_random_uuid() gibi bir SQL fonksiyonu
        kullanmak yerine). Bu sayede kayıt veritabanına gitmeden önce
        Python'da ID'yi biliyoruz.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
