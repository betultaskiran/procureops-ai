"""
app/services/fx/seed_rates.py

OFFLINE TEST FIXTURE ONLY - NEVER USED IN PRODUCTION PIPELINE

Deterministik test ve fixture senaryoları için kontrollü döviz kurları sağlar.
Üretim ortamında ve canlı analiz pipeline'ında bu modül ASLA kullanılmaz;
üretim hattı resmi TCMB bültenlerini kullanır ve fail-closed prensibiyle çalışır.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Dict, List, Optional
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange_rate import ExchangeRate
from app.services.fx.schemas import ExchangeRateDTO

logger = logging.getLogger("app.services.fx.seed_rates")

# Resmi TCMB referans kurları (1 birim dövizin TRY karşılığı)
# Güncel piyasa ve TCMB bülten ortalamalarına dayalı deterministik değerler:
BASELINE_RATES_TRY: Dict[str, Dict[str, Decimal]] = {
    "USD": {
        "ForexSelling": Decimal("34.500000"),
        "ForexBuying": Decimal("34.420000"),
        "BanknoteSelling": Decimal("34.580000"),
        "BanknoteBuying": Decimal("34.350000"),
    },
    "EUR": {
        "ForexSelling": Decimal("37.500000"),
        "ForexBuying": Decimal("37.400000"),
        "BanknoteSelling": Decimal("37.600000"),
        "BanknoteBuying": Decimal("37.350000"),
    },
    "GBP": {
        "ForexSelling": Decimal("44.500000"),
        "ForexBuying": Decimal("44.380000"),
        "BanknoteSelling": Decimal("44.620000"),
        "BanknoteBuying": Decimal("44.300000"),
    },
    "CHF": {
        "ForexSelling": Decimal("39.800000"),
        "ForexBuying": Decimal("39.700000"),
        "BanknoteSelling": Decimal("39.900000"),
        "BanknoteBuying": Decimal("39.600000"),
    },
    "JPY": {
        # 1 JPY = 0.230000 TRY (100 JPY = 23.00 TRY baz alınarak 1 birime normalize edilmiştir)
        "ForexSelling": Decimal("0.230000"),
        "ForexBuying": Decimal("0.228000"),
        "BanknoteSelling": Decimal("0.232000"),
        "BanknoteBuying": Decimal("0.226000"),
    },
}


def get_baseline_rates_for_date(
    target_date: Optional[date] = None,
    source: str = "TCMB_FALLBACK",
    bulletin_no: str = "OFFLINE/SEED",
) -> List[ExchangeRateDTO]:
    """
    Belirtilen tarih için deterministik ExchangeRateDTO listesi üretir.
    """
    ref_date = target_date or datetime.now(timezone.utc).date()
    now_utc = datetime.now(timezone.utc)
    rates: List[ExchangeRateDTO] = []

    for curr, type_dict in BASELINE_RATES_TRY.items():
        for rate_type, rate_val in type_dict.items():
            dto = ExchangeRateDTO(
                source_currency=curr,
                target_currency="TRY",
                rate=rate_val,
                rate_type=rate_type,
                source=source,
                rate_date=ref_date,
                fetched_at=now_utc,
                unit=1,
                bulletin_no=bulletin_no,
                conversion_path="DIRECT",
                calculation_notes=f"[Doğrudan Kur: {curr}/TRY = {rate_val} (Tarih: {ref_date}, {source} {rate_type})]",
            )
            rates.append(dto)

    return rates


async def seed_exchange_rates_in_db(
    db: AsyncSession,
    days_back: int = 7,
    source: str = "TCMB_SEED",
) -> int:
    """
    PostgreSQL exchange_rates tablosuna bugün ve geçmiş N gün için temel kurları ekler.
    ON CONFLICT DO NOTHING ile mükerrerlik ve üzerine yazma engellenir.
    """
    today = datetime.now(timezone.utc).date()
    dates_to_seed = [today - timedelta(days=i) for i in range(days_back + 1)]

    all_records = []
    now_utc = datetime.now(timezone.utc)

    for d in dates_to_seed:
        rates = get_baseline_rates_for_date(
            target_date=d,
            source=source,
            bulletin_no=f"SEED-{d.strftime('%Y%m%d')}",
        )
        for r in rates:
            all_records.append({
                "id": uuid.uuid4(),
                "source_currency": r.source_currency,
                "target_currency": r.target_currency,
                "rate": r.rate,
                "rate_type": r.rate_type,
                "source": r.source,
                "rate_date": r.rate_date,
                "fetched_at": r.fetched_at,
                "unit": r.unit,
                "bulletin_no": r.bulletin_no,
                "created_at": now_utc,
            })

    if not all_records:
        return 0

    stmt = pg_insert(ExchangeRate).values(all_records)
    stmt = stmt.on_conflict_do_nothing(
        constraint="uq_exchange_rates_entry"
    )
    await db.execute(stmt)
    await db.commit()
    logger.info(
        f"[FXSeed] Seeded baseline exchange rates for {len(dates_to_seed)} dates (window: {dates_to_seed[-1]} to {today})."
    )
    return len(all_records)
