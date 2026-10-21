"""
app/services/fx/mock_provider.py

Deterministik birim ve entegrasyon testleri için Mock FX Provider.
Gerçek ağ çağrısı yapmaz; test senaryoları için önceden tanımlanmış kurları döndürür.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Tuple

from app.services.fx.base import BaseExchangeRateProvider
from app.services.fx.exceptions import FXRateNotFoundError
from app.services.fx.schemas import ExchangeRateDTO


class MockExchangeRateProvider(BaseExchangeRateProvider):
    """
    Testler için bellek içi (in-memory) döviz kuru sağlayıcısı.
    """

    def __init__(self):
        # Anahtar: (source_currency, target_currency, rate_type, rate_date) -> ExchangeRateDTO
        self._rates: Dict[Tuple[str, str, str, date], ExchangeRateDTO] = {}
        self._date_rates: Dict[date, List[ExchangeRateDTO]] = {}
        self.call_count = 0
        self.should_fail: Exception | None = None

    def clear(self) -> None:
        """Kayıtlı tüm kurları ve sayaçları temizler."""
        self._rates.clear()
        self._date_rates.clear()
        self.call_count = 0
        self.should_fail = None

    def add_rate(
        self,
        source_currency: str,
        target_currency: str = "TRY",
        rate: Decimal | str | float = Decimal("34.250000"),
        rate_date: date | None = None,
        rate_type: str = "ForexSelling",
        unit: int = 1,
        bulletin_no: str | None = "TEST/001",
    ) -> ExchangeRateDTO:
        """Test amaçlı bir kur kaydı ekler."""
        if rate_date is None:
            rate_date = datetime.now(timezone.utc).date()

        dec_rate = Decimal(str(rate))
        dto = ExchangeRateDTO(
            source_currency=source_currency.strip().upper(),
            target_currency=target_currency.strip().upper(),
            rate=dec_rate,
            rate_type=rate_type,
            source="MOCK",
            rate_date=rate_date,
            fetched_at=datetime.now(timezone.utc),
            unit=unit,
            bulletin_no=bulletin_no,
        )

        key = (dto.source_currency, dto.target_currency, dto.rate_type, dto.rate_date)
        self._rates[key] = dto

        if rate_date not in self._date_rates:
            self._date_rates[rate_date] = []
        self._date_rates[rate_date].append(dto)

        return dto

    async def fetch_rates(self, target_date: date | None = None) -> List[ExchangeRateDTO]:
        self.call_count += 1

        if self.should_fail:
            raise self.should_fail

        if target_date is None:
            # En güncel tarihi bul
            if not self._date_rates:
                raise FXRateNotFoundError("Mock provider has no registered rates.")
            latest_date = max(self._date_rates.keys())
            return list(self._date_rates[latest_date])

        if target_date not in self._date_rates:
            raise FXRateNotFoundError(f"Mock rates not found for date: {target_date}")

        return list(self._date_rates[target_date])
