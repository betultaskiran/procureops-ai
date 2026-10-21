"""
tests/test_fx_service.py

Milestone 2B: ExchangeRateService Kapsamlı Test Paketi.
Test Edilen Senaryolar:
1. Para birimi eşitliği (source == target) -> sorgusuz 1.0 kimlik kuru.
2. Gelecek tarih engeli (FXFutureDateError).
3. Cache Miss -> DB Miss -> Provider Fetch -> DB ve Redis kalıcı kayıt doğrulaması.
4. Cache Hit -> İkinci çağrıda doğrudan Redis'ten döner, DB/Provider çağrılmaz.
5. PostgreSQL Arşivinden Okuma -> Cache miss durumunda yerel DB'den döner, Redis'i ısıtır.
6. DB Toplu Kayıt Atomikliği (`ON CONFLICT DO NOTHING`) -> Mükerrer kayıt hatasız atlanır.
7. Hafta Sonu / Tatil Geriye Dönük Lookback Fallback -> Pazar günü istendiğinde Cuma kurunu bulur.
8. Redis Kesintisi Graceful Fallback -> Redis çöktüğünde sessizce DB arşivinden çalışmaya devam eder.
9. Fail-Closed Güvenliği -> Lookback penceresinde kur bulunamazsa CurrencyConversionUnavailableException fırlatır.
10. Tutar Dönüşümü ve `ROUND_HALF_UP` finansal kesinlik doğrulaması.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest

from sqlalchemy import select, delete

from app.db.session import AsyncSessionLocal
from app.models.exchange_rate import ExchangeRate
from app.services.fx.exceptions import (
    CurrencyConversionUnavailableException,
    FXFutureDateError,
    FXRateNotFoundError,
)
from app.services.fx.mock_provider import MockExchangeRateProvider
from app.services.fx.schemas import ExchangeRateDTO
from app.services.fx.service import ExchangeRateService


class MockRedis:
    """Testler için bellek içi kontrollü Redis istemcisi."""
    def __init__(self):
        self.store = {}
        self.get_count = 0
        self.set_count = 0
        self.should_fail = False

    async def get(self, key: str):
        self.get_count += 1
        if self.should_fail:
            raise ConnectionError("Simulated Redis connection drop")
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.set_count += 1
        if self.should_fail:
            raise ConnectionError("Simulated Redis connection drop")
        self.store[key] = value

    async def aclose(self):
        pass


@pytest.fixture
async def cleanup_test_exchange_rates():
    """Her test öncesi ve sonrası test para birimi kayıtlarını temizler."""
    test_currencies = ["TST", "TS2", "TS3", "USD", "EUR", "GBP", "JPY", "CHF"]
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(ExchangeRate).where(ExchangeRate.source_currency.in_(test_currencies))
        )
        await session.commit()
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0")
        keys = await r.keys("fx:rate:TS*")
        if keys:
            await r.delete(*keys)
        await r.aclose()
    except Exception:
        pass
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(ExchangeRate).where(ExchangeRate.source_currency.in_(test_currencies))
        )
        await session.commit()
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0")
        keys = await r.keys("fx:rate:TS*")
        if keys:
            await r.delete(*keys)
        await r.aclose()
    except Exception:
        pass


# ── Test 1: Same Currency Identity Rate ───────────────────────────────────────

@pytest.mark.asyncio
async def test_same_currency_returns_identity_rate_without_queries():
    """1. Aynı para birimleri (TRY->TRY, USD->usd) sorgusuz anında 1.0 döner."""
    async with AsyncSessionLocal() as db:
        mock_provider = MockExchangeRateProvider()
        mock_redis = MockRedis()
        service = ExchangeRateService(db=db, provider=mock_provider, redis_client=mock_redis)

        dto = await service.get_rate("TRY", "TRY")
        assert dto.rate == Decimal("1.0")
        assert dto.source == "IDENTITY"
        assert dto.source_currency == "TRY"
        assert dto.target_currency == "TRY"

        # Hiçbir dış ya da cache çağrısı yapılmamalıdır
        assert mock_provider.call_count == 0
        assert mock_redis.get_count == 0

        # Case-insensitive doğrulama
        dto2 = await service.get_rate("usd", "USD")
        assert dto2.rate == Decimal("1.0")


# ── Test 2: Future Date Rejection ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_future_date_rejected():
    """2. Geleceğe ait bir tarih istendiğinde FXFutureDateError fırlatır."""
    async with AsyncSessionLocal() as db:
        service = ExchangeRateService(db=db)
        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)

        with pytest.raises(FXFutureDateError, match="cannot be in the future"):
            await service.get_rate("USD", "TRY", rate_date=tomorrow)


# ── Test 3 & 4: Cache Miss -> Provider Fetch -> DB Persistence -> Cache Hit ──

@pytest.mark.asyncio
async def test_cache_miss_then_hit_flow(cleanup_test_exchange_rates):
    """
    3 & 4. İlk çağrıda cache miss olur, provider'dan çeker, PostgreSQL'e ve Redis'e kaydeder.
    İkinci çağrıda doğrudan Redis'ten döner (Cache Hit).
    """
    ref_date = date(2026, 10, 20)
    mock_provider = MockExchangeRateProvider()
    mock_provider.add_rate("TST", "TRY", rate=Decimal("35.500000"), rate_date=ref_date)
    mock_redis = MockRedis()

    async with AsyncSessionLocal() as db:
        service = ExchangeRateService(db=db, provider=mock_provider, redis_client=mock_redis)

        # 1. İlk çağrı (Cache Miss -> DB Miss -> Provider Fetch)
        dto1 = await service.get_rate("TST", "TRY", rate_date=ref_date)
        assert dto1.rate == Decimal("35.500000")
        assert dto1.source_currency == "TST"
        assert mock_provider.call_count == 1
        assert mock_redis.get_count == 1
        assert mock_redis.set_count == 1

        # Veritabanında fiziksel kaydın oluştuğunu doğrula
        db_record = await db.execute(
            select(ExchangeRate).where(
                ExchangeRate.source_currency == "TST",
                ExchangeRate.target_currency == "TRY",
                ExchangeRate.rate_date == ref_date,
            )
        )
        row = db_record.scalar_one_or_none()
        assert row is not None
        assert row.rate == Decimal("35.500000")

        # 2. İkinci çağrı (Cache Hit)
        dto2 = await service.get_rate("TST", "TRY", rate_date=ref_date)
        assert dto2.rate == Decimal("35.500000")
        # Provider tekrar çağrılmamalıdır
        assert mock_provider.call_count == 1
        assert mock_redis.get_count == 2


# ── Test 5: PostgreSQL Archive Read & Cache Warming ──────────────────────────

@pytest.mark.asyncio
async def test_db_archive_read_and_cache_warming(cleanup_test_exchange_rates):
    """5. Redis boşken PostgreSQL arşivinde kayıt varsa oradan okur ve Redis'i ısıtır."""
    ref_date = date(2026, 10, 19)
    async with AsyncSessionLocal() as db:
        # Doğrudan DB'ye kayıt atalım
        db.add(
            ExchangeRate(
                source_currency="TST",
                target_currency="TRY",
                rate=Decimal("36.120000"),
                rate_type="ForexSelling",
                source="TCMB",
                rate_date=ref_date,
                fetched_at=datetime.now(timezone.utc),
                unit=1,
                bulletin_no="TEST/ARCHIVE",
            )
        )
        await db.commit()

        mock_provider = MockExchangeRateProvider()
        mock_redis = MockRedis()
        service = ExchangeRateService(db=db, provider=mock_provider, redis_client=mock_redis)

        dto = await service.get_rate("TST", "TRY", rate_date=ref_date)
        assert dto.rate == Decimal("36.120000")
        assert dto.bulletin_no == "TEST/ARCHIVE"

        # Provider hiç çağrılmamalı
        assert mock_provider.call_count == 0
        # Redis ısıtılmış olmalı
        assert mock_redis.set_count == 1


# ── Test 6: Bulk Fetch & ON CONFLICT DO NOTHING Idempotency ───────────────────

@pytest.mark.asyncio
async def test_bulk_fetch_on_conflict_do_nothing(cleanup_test_exchange_rates):
    """6. Aynı kurlar tekrar çekildiğinde ON CONFLICT DO NOTHING ile hatasız atlanır."""
    ref_date = date(2026, 10, 20)
    mock_provider = MockExchangeRateProvider()
    mock_provider.add_rate("TST", "TRY", rate=Decimal("35.000000"), rate_date=ref_date)

    async with AsyncSessionLocal() as db:
        service = ExchangeRateService(db=db, provider=mock_provider)

        # İlk kayıt
        rates1 = await service.bulk_fetch_and_store(ref_date)
        assert len(rates1) == 1

        # İkinci çalıştırma (aynı kayıt) -> Hata üretmemeli
        rates2 = await service.bulk_fetch_and_store(ref_date)
        assert len(rates2) == 1

        # DB'de tek bir kayıt kalmalıdır
        count_res = await db.execute(
            select(ExchangeRate).where(
                ExchangeRate.source_currency == "TST",
                ExchangeRate.rate_date == ref_date,
            )
        )
        rows = count_res.scalars().all()
        assert len(rows) == 1


# ── Test 7: Weekend / Holiday Lookback Fallback ───────────────────────────────

@pytest.mark.asyncio
async def test_weekend_holiday_lookback_fallback(cleanup_test_exchange_rates):
    """
    7. Pazar günü (2026-10-18) kur istendiğinde:
    Pazar ve Cumartesi bülten yoktur; geriye dönük Cuma (2026-10-16) bültenini bulup döner.
    """
    friday = date(2026, 10, 16)
    sunday = date(2026, 10, 18)

    mock_provider = MockExchangeRateProvider()
    # Yalnızca Cuma gününe ait resmi bülten var
    mock_provider.add_rate("TST", "TRY", rate=Decimal("34.800000"), rate_date=friday, bulletin_no="BULTEN/FRIDAY")
    mock_redis = MockRedis()

    async with AsyncSessionLocal() as db:
        service = ExchangeRateService(db=db, provider=mock_provider, redis_client=mock_redis)

        dto = await service.get_rate("TST", "TRY", rate_date=sunday, max_lookback_days=5)
        assert dto.rate == Decimal("34.800000")
        assert dto.rate_date == friday
        assert dto.bulletin_no == "BULTEN/FRIDAY"


# ── Test 8: Redis Outage Graceful Fallback ────────────────────────────────────

@pytest.mark.asyncio
async def test_redis_outage_graceful_fallback(cleanup_test_exchange_rates):
    """8. Redis bağlantısı çöktüğünde sistem ana akışı kırmaz, PostgreSQL arşivinden döner."""
    ref_date = date(2026, 10, 20)
    async with AsyncSessionLocal() as db:
        db.add(
            ExchangeRate(
                source_currency="TST",
                target_currency="TRY",
                rate=Decimal("35.750000"),
                rate_type="ForexSelling",
                source="TCMB",
                rate_date=ref_date,
                fetched_at=datetime.now(timezone.utc),
                unit=1,
            )
        )
        await db.commit()

        # Bozulan Redis
        failing_redis = MockRedis()
        failing_redis.should_fail = True

        service = ExchangeRateService(db=db, redis_client=failing_redis)

        # Redis hatasına rağmen DB'den başarıyla dönmeli
        dto = await service.get_rate("TST", "TRY", rate_date=ref_date)
        assert dto.rate == Decimal("35.750000")


# ── Test 9: Fail-Closed When Rate Unavailable ─────────────────────────────────

@pytest.mark.asyncio
async def test_fail_closed_when_rate_unavailable():
    """9. Lookback penceresi içinde hiçbir resmi kur bulunamazsa CurrencyConversionUnavailableException fırlatır."""
    async with AsyncSessionLocal() as db:
        empty_provider = MockExchangeRateProvider()
        service = ExchangeRateService(db=db, provider=empty_provider)

        # Desteklenmeyen veya bülteni olmayan para birimi
        with pytest.raises(CurrencyConversionUnavailableException, match="Döviz kuru temin edilemedi"):
            await service.get_rate("ZZZ", "TRY", rate_date=date(2026, 10, 20), max_lookback_days=3)


# ── Test 10: Convert Amount & ROUND_HALF_UP Precision ─────────────────────────

@pytest.mark.asyncio
async def test_convert_amount_with_half_up_precision(cleanup_test_exchange_rates):
    """10. convert_amount hesaplaması Decimal hassasiyeti ve ROUND_HALF_UP ile 4 hane döner."""
    ref_date = date(2026, 10, 20)
    mock_provider = MockExchangeRateProvider()
    mock_provider.add_rate("TST", "TRY", rate=Decimal("34.123456"), rate_date=ref_date)
    mock_redis = MockRedis()

    async with AsyncSessionLocal() as db:
        service = ExchangeRateService(db=db, provider=mock_provider, redis_client=mock_redis)

        # 1000 * 34.123456 = 34123.4560
        amount = Decimal("1000.00")
        converted, dto = await service.convert_amount(
            amount=amount,
            source_currency="TST",
            target_currency="TRY",
            rate_date=ref_date,
        )

        assert converted == Decimal("34123.4560")
        assert dto.rate == Decimal("34.123456")
        assert isinstance(converted, Decimal)
