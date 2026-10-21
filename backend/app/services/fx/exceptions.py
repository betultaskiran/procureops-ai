"""
app/services/fx/exceptions.py

FX Engine hata hiyerarşisi.
Tüm sağlayıcı, veri doğrulama, tarih çözümleme ve fail-closed hataları burada tanımlanır.
"""


class FXEngineError(Exception):
    """FX Engine genel temel istisna sınıfı."""
    pass


class FXProviderError(FXEngineError):
    """Sağlayıcı iletişim, ağ veya HTTP hataları."""
    pass


class FXRateNotFoundError(FXEngineError):
    """Belirtilen para birimi veya tarih için kur bulunamadı."""
    pass


class FXInvalidDataError(FXEngineError):
    """Bozuk XML, negatif/sıfır kur veya geçersiz veri formatı."""
    pass


class FXLookbackLimitExceededError(FXEngineError):
    """İzin verilen geriye dönük arama sınırı (örn. 5 veya 7 gün) aşıldı."""
    pass


class FXFutureDateError(FXEngineError):
    """Geleceğe ait bir tarih için kur talep edildi."""
    pass


class CurrencyConversionUnavailableException(FXEngineError):
    """
    Kur bulunamadığında, sağlayıcıya erişilemediğinde veya geriye dönük
    arama penceresi tükendiğinde fırlatılan fail-closed güvenlik istisnası.
    """
    pass
