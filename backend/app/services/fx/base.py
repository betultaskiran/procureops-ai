"""
app/services/fx/base.py

Kur sağlayıcıları için soyut taban sınıfı (Abstract Base Class).
TCMB, serbest piyasa veya test mock provider'ları bu arayüzü uygular.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import List

from app.services.fx.schemas import ExchangeRateDTO


class BaseExchangeRateProvider(ABC):
    """
    Döviz kuru sağlayıcı arayüzü.
    """

    @abstractmethod
    async def fetch_rates(self, target_date: date | None = None) -> List[ExchangeRateDTO]:
        """
        Belirtilen resmi iş günü için (veya None ise en güncel)
        sağlayıcıdan tüm kurları çeker ve normalize edilmiş ExchangeRateDTO listesi döner.

        Hata durumlarında FXProviderError veya FXRateNotFoundError fırlatır.
        """
        pass
