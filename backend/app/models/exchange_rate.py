"""
app/models/exchange_rate.py

Kurumsal döviz kuru ve bülten verisi modeli.

TCMB ve diğer harici kur sağlayıcılarından çekilen resmi kurları,
bülten tarihini, kur türünü ve normalize edilmiş birim oranını saklar.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base, UUIDPrimaryKeyMixin


class ExchangeRate(Base, UUIDPrimaryKeyMixin):
    """
    Döviz kuru kayıtları.

    ÖNEMLİ KURALLAR:
    - `rate`, 1 birim `source_currency` karşılığındaki `target_currency` tutarıdır (NUMERIC(18, 6)).
    - `unit`, sağlayıcının yayımladığı orijinal birimdir (örn. JPY için 100).
    - `rate` her zaman birim başına normalize edilmiş değerdir: (yayımlanan kur / unit).
    - `rate_date`, kur bülteninin ait olduğu resmi iş günü tarihidir.
    - `fetched_at`, sistemin bu veriyi sağlayıcıdan aldığı UTC zaman damgasıdır.
    """
    __tablename__ = "exchange_rates"

    source_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        index=True,
    )
    target_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        index=True,
    )
    rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
    )
    rate_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ForexSelling",
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="TCMB",
    )
    rate_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    unit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    bulletin_no: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "source_currency",
            "target_currency",
            "rate_type",
            "rate_date",
            "source",
            name="uq_exchange_rates_entry",
        ),
        Index(
            "ix_exchange_rates_lookup",
            "source_currency",
            "target_currency",
            "rate_date",
        ),
    )

    @validates("source_currency", "target_currency")
    def validate_currency(self, key: str, value: str) -> str:
        if not value or not str(value).strip():
            raise ValueError(f"{key} cannot be empty.")
        clean = str(value).strip().upper()
        if len(clean) != 3:
            raise ValueError(f"{key} must be a 3-letter ISO code (got: {value!r}).")
        return clean

    @validates("rate")
    def validate_rate(self, key: str, value: Decimal | float | str) -> Decimal:
        dec_val = Decimal(str(value))
        if dec_val <= Decimal("0"):
            raise ValueError(f"Exchange rate must be positive and non-zero (got: {value}).")
        return dec_val

    @validates("unit")
    def validate_unit(self, key: str, value: int) -> int:
        if value <= 0:
            raise ValueError(f"Unit must be a positive integer (got: {value}).")
        return value

    def __repr__(self) -> str:
        return (
            f"<ExchangeRate {self.source_currency}/{self.target_currency} "
            f"rate={self.rate} type={self.rate_type} date={self.rate_date} source={self.source}>"
        )
