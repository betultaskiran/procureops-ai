"""
app/services/fx/schemas.py

FX Engine tipli veri transfer nesneleri (DTO).
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
import json


@dataclass(frozen=True)
class ExchangeRateDTO:
    """
    Bir para birimi kuru için tipli DTO.
    
    ÖNEMLİ:
    - `rate`, 1 birim `source_currency` karşılığındaki `target_currency` tutarıdır (normalize edilmiştir).
    - `unit`, sağlayıcının yayımladığı ham birim bilgisidir (örn. JPY=100).
    - `rate_date`, bültenin resmi iş günü tarihidir.
    - `fetched_at`, sistemin kuru çektiği UTC anıdır.
    """
    source_currency: str
    target_currency: str
    rate: Decimal
    rate_type: str
    source: str
    rate_date: date
    fetched_at: datetime
    unit: int = 1
    bulletin_no: str | None = None
    conversion_path: str = "DIRECT"
    calculation_notes: str | None = None

    def to_dict(self) -> dict:
        """Sözlük formatına dönüştürür (Decimal ve date/datetime tiplerini string yapar)."""
        d = asdict(self)
        d["rate"] = str(self.rate)
        d["rate_date"] = self.rate_date.isoformat()
        d["fetched_at"] = self.fetched_at.isoformat()
        return d

    def to_json(self) -> str:
        """Redis veya mesaj kuyrukları için JSON string formatına serileştirir."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict) -> "ExchangeRateDTO":
        """Sözlükten tipli ExchangeRateDTO nesnesi üretir."""
        return cls(
            source_currency=data["source_currency"],
            target_currency=data["target_currency"],
            rate=Decimal(str(data["rate"])),
            rate_type=data["rate_type"],
            source=data["source"],
            rate_date=date.fromisoformat(data["rate_date"]),
            fetched_at=datetime.fromisoformat(data["fetched_at"]),
            unit=int(data.get("unit", 1)),
            bulletin_no=data.get("bulletin_no"),
            conversion_path=data.get("conversion_path", "DIRECT"),
            calculation_notes=data.get("calculation_notes"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ExchangeRateDTO":
        """JSON string'den tipli ExchangeRateDTO nesnesi çözer."""
        data = json.loads(json_str)
        return cls.from_dict(data)
