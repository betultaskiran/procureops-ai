"""
app/services/fx/policy.py

FX Engine tarih ve kur dönüşüm politikası yardımcı fonksiyonları.

Kurallar:
- Gelecek tarihler kesinlikle reddedilir.
- Hafta sonu/tatil fallback'i en fazla max_lookback_days (varsayılan 7 gün) geriye gidebilir.
- Matematiksel dönüşümler Python Decimal ile yapılır; float kesinlikle kullanılmaz.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.services.fx.exceptions import (
    FXFutureDateError,
    FXInvalidDataError,
)


def validate_currency_code(code: str, field_name: str = "Currency") -> str:
    """Para birimi kodunu doğrular ve temizlenmiş ISO 3 harfli string döner."""
    if not code or not str(code).strip():
        raise FXInvalidDataError(f"{field_name} cannot be empty.")
    clean = str(code).strip().upper()
    if len(clean) != 3 or not clean.isalpha():
        raise FXInvalidDataError(f"{field_name} must be a 3-letter alphabetic ISO code (got: {code!r}).")
    return clean


def is_same_currency(source_currency: str, target_currency: str) -> bool:
    """İki para biriminin aynı olup olmadığını büyük/küçük harf toleransıyla kontrol eder."""
    return validate_currency_code(source_currency) == validate_currency_code(target_currency)


def resolve_candidate_dates(
    requested_date: date,
    reference_today: date | None = None,
    max_lookback_days: int = 7,
) -> list[date]:
    """
    İstenen tarih için geriye dönük aday iş günü bülten tarihlerini üretir.

    Kurallar:
    - requested_date > reference_today ise FXFutureDateError fırlatır.
    - [requested_date, requested_date - 1 gün, ..., requested_date - max_lookback_days]
      listesini sırayla döndürür.
    """
    if reference_today is None:
        reference_today = datetime.now(timezone.utc).date()

    if requested_date > reference_today:
        raise FXFutureDateError(
            f"Requested rate date ({requested_date}) cannot be in the future (today is {reference_today})."
        )

    if max_lookback_days < 0:
        raise FXInvalidDataError(f"max_lookback_days must be non-negative (got: {max_lookback_days}).")

    candidates = [
        requested_date - timedelta(days=offset)
        for offset in range(max_lookback_days + 1)
    ]
    return candidates


def count_business_days_between(start_date: date, end_date: date) -> int:
    """
    start_date (hariç) ile end_date (dahil) arasındaki resmi iş günü (Pazartesi-Cuma)
    sayısını hesaplar.
    """
    if start_date >= end_date:
        return 0
    business_days = 0
    cur = start_date + timedelta(days=1)
    while cur <= end_date:
        if cur.weekday() < 5:  # 0=Pazartesi, ..., 4=Cuma
            business_days += 1
        cur += timedelta(days=1)
    return business_days


def is_rate_fresh(
    requested_date: date,
    rate_date: date,
    max_lookback_days: int = 5,
    max_business_days_lag: int = 2,
) -> bool:
    """
    Döviz kuru tazelik politikasını doğrular.

    TCMB YAYIN DÖNGÜSÜ & KURALLAR:
    1. Gelecek Tarih Koruması: rate_date > requested_date kesinlikle kabul edilemez.
    2. Aynı Gün: calendar_days == 0 -> Tazedir.
    3. Takvim Farkı Sınırı: calendar_days > max_lookback_days (varsayılan: 5 gün) ise
       kur bayat kabul edilir (fail-closed).
    4. Hafta Sonu Uyumluluğu:
       - TCMB hafta sonları (Cumartesi, Pazar) bülten yayımlamaz.
       - Cuma günü yayımlanan bülten; Cumartesi, Pazar ve Pazartesi günü yeni bülten
         yayımlanana kadar resmi ve tazedir.
    5. İş Günü Gecikmesi Sınırı:
       - rate_date ile requested_date arasındaki iş günü gecikmesi en fazla
         max_business_days_lag (varsayılan: 2 iş günü) olabilir.
       - Örneğin, normal bir Çarşamba gününde önceki Cuma'nın kuru (arada Pazartesi ve Salı
         iş günleri bulunup 2 iş günü eşiği aşıldığında) bayat kabul edilir.
    """
    if rate_date > requested_date:
        return False

    calendar_days = (requested_date - rate_date).days
    if calendar_days == 0:
        return True

    if calendar_days > max_lookback_days:
        return False

    business_days_lag = count_business_days_between(rate_date, requested_date)
    return business_days_lag <= max_business_days_lag


def calculate_conversion(
    amount: Decimal | str | int | float,
    rate: Decimal | str | int | float,
) -> Decimal:
    """
    Miktarı kur ile çarparak hedef para birimi karşılığını döner.
    Float hassasiyet kaybını önlemek için Decimal kullanır.
    """
    try:
        dec_amount = Decimal(str(amount))
    except Exception as exc:
        raise FXInvalidDataError(f"Invalid amount for FX conversion: {amount!r}") from exc

    try:
        dec_rate = Decimal(str(rate))
    except Exception as exc:
        raise FXInvalidDataError(f"Invalid rate for FX conversion: {rate!r}") from exc

    if dec_rate <= Decimal("0"):
        raise FXInvalidDataError(f"Exchange rate must be strictly positive (got: {dec_rate}).")

    return dec_amount * dec_rate

