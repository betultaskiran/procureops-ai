"""
app/services/fx/service.py

ExchangeRateService:
PostgreSQL kur arşivi, Redis Cache-Aside katmanı ve TCMB sağlayıcı orkestrasyonunu yöneten ana servis.

MİMARİ PRENSİPLER:
1. Tek Doğruluk Kaynağı: PostgreSQL (`exchange_rates` tablosu) ana ve kalıcı kur arşivimizdir.
2. Redis Cache-Aside: Yalnızca veritabanı ve harici sağlayıcı yükünü azaltan bir önbellektir.
   Redis çökse dahi sistem sessizce PostgreSQL arşivinden çalışmaya devam eder (graceful fallback).
3. Çözümleme Sırası:
   - source == target ise anında 1.0 DTO (sorgusuz)
   - Adım 1: Redis Cache kontrolü
   - Adım 2: PostgreSQL Arşiv kontrolü
   - Adım 3: Harici Sağlayıcı (TCMB) çekimi ve PostgreSQL'e kalıcı INSERT (ON CONFLICT DO NOTHING)
   - Adım 4: Hafta sonu / Tatil durumunda geriye dönük N gün (varsayılan: 5 gün) lookback fallback
   - Adım 5: Fail-Closed: Hiçbir kur bulunamazsa CurrencyConversionUnavailableException fırlatılır.
4. Finansal Kesinlik: Tüm işlemler Decimal ve ROUND_HALF_UP ile yapılır. Float kesinlikle yasaktır.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
import uuid
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.exchange_rate import ExchangeRate
from app.services.fx.base import BaseExchangeRateProvider
from app.services.fx.exceptions import (
    CurrencyConversionUnavailableException,
    FXFutureDateError,
    FXProviderError,
    FXRateNotFoundError,
)
from app.services.fx.policy import (
    resolve_candidate_dates,
    validate_currency_code,
)
from app.services.fx.schemas import ExchangeRateDTO
from app.services.fx.tcmb_provider import TCMBExchangeRateProvider


logger = logging.getLogger("app.services.fx.service")


class ExchangeRateService:
    """
    Döviz kuru arşivi, önbellekleme ve çevrim servisi.
    """

    def __init__(
        self,
        db: AsyncSession,
        provider: BaseExchangeRateProvider | None = None,
        redis_client=None,
    ):
        self.db = db
        self.provider = provider or TCMBExchangeRateProvider()
        self.redis_client = redis_client
        self._redis_initialized = redis_client is not None

    async def _get_redis(self):
        """Redis istemcisini temin eder; hata durumunda None dönerek graceful fallback sağlar."""
        if self._redis_initialized:
            return self.redis_client

        try:
            import redis.asyncio as aioredis
            self.redis_client = aioredis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                decode_responses=True,
            )
            self._redis_initialized = True
            return self.redis_client
        except Exception as exc:
            logger.warning(f"[FXService] Redis initialization failed: {exc}. Proceeding without cache.")
            self._redis_initialized = False
            return None

    def _cache_key(
        self,
        source_currency: str,
        target_currency: str,
        rate_date: date,
        rate_type: str,
    ) -> str:
        """Belirtilen kur için standart Redis anahtarını üretir."""
        return f"fx:rate:{source_currency.upper()}:{target_currency.upper()}:{rate_date.isoformat()}:{rate_type}"

    async def _cache_get(self, key: str) -> ExchangeRateDTO | None:
        """Redis'ten kur DTO'sunu sorgular. Hata durumunda loglar ve None döner."""
        try:
            r = await self._get_redis()
            if not r:
                return None
            val = await r.get(key)
            if val:
                return ExchangeRateDTO.from_json(val)
        except Exception as exc:
            logger.warning(f"[FXService] Redis GET error on key '{key}': {exc}. Gracefully falling back.")
        return None

    async def _cache_set(self, key: str, dto: ExchangeRateDTO) -> None:
        """Redis'e kur DTO'sunu yazar. Güncel gün için 1 saat (3600s), geçmiş kesinleşmiş günler için 24 saat (86400s) TTL."""
        try:
            r = await self._get_redis()
            if not r:
                return
            today = datetime.now(timezone.utc).date()
            ttl = 3600 if dto.rate_date >= today else 86400
            await r.set(key, dto.to_json(), ex=ttl)
        except Exception as exc:
            logger.warning(f"[FXService] Redis SET error on key '{key}': {exc}.")

    async def _db_get(
        self,
        source_currency: str,
        target_currency: str,
        rate_date: date,
        rate_type: str,
    ) -> ExchangeRateDTO | None:
        """PostgreSQL `exchange_rates` tablosundan tek bir kur sorgular."""
        stmt = (
            select(ExchangeRate)
            .where(
                ExchangeRate.source_currency == source_currency,
                ExchangeRate.target_currency == target_currency,
                ExchangeRate.rate_type == rate_type,
                ExchangeRate.rate_date == rate_date,
            )
            .limit(1)
        )
        res = await self.db.execute(stmt)
        row = res.scalar_one_or_none()
        if row:
            return ExchangeRateDTO(
                source_currency=row.source_currency,
                target_currency=row.target_currency,
                rate=row.rate,
                rate_type=row.rate_type,
                source=row.source,
                rate_date=row.rate_date,
                fetched_at=row.fetched_at,
                unit=row.unit,
                bulletin_no=row.bulletin_no,
            )
        return None

    async def _db_save_batch(self, rates: List[ExchangeRateDTO]) -> None:
        """
        Çekilen kurları PostgreSQL `exchange_rates` tablosuna atomik olarak kaydeder.
        `ON CONFLICT (source_currency, target_currency, rate_type, rate_date, source) DO NOTHING`
        kullanılarak mükerrer kayıtlar engellenir.
        """
        if not rates:
            return

        now_utc = datetime.now(timezone.utc)
        records = [
            {
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
            }
            for r in rates
        ]

        stmt = pg_insert(ExchangeRate).values(records)
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_exchange_rates_entry"
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def bulk_fetch_and_store(
        self,
        target_date: date | None = None,
    ) -> List[ExchangeRateDTO]:
        """
        Sağlayıcıdan (TCMB) belirtilen tarih için bülteni çeker, PostgreSQL arşivine
        yazar ve önbelleği ısıtır.
        """
        rates = await self.provider.fetch_rates(target_date)
        if rates:
            await self._db_save_batch(rates)
            # İlgili kurları Redis önbelleğine de yaz
            for r in rates:
                key = self._cache_key(r.source_currency, r.target_currency, r.rate_date, r.rate_type)
                await self._cache_set(key, r)
        return rates

    async def _resolve_direct_pair(
        self,
        source_currency: str,
        target_currency: str,
        cand_date: date,
        rate_type: str,
    ) -> ExchangeRateDTO | None:
        """
        Belirtilen doğrudan para birimi çiftini Redis -> PostgreSQL -> TCMB sırasıyla arar.
        """
        cache_key = self._cache_key(source_currency, target_currency, cand_date, rate_type)

        # 1. Redis Cache Kontrolü
        cached = await self._cache_get(cache_key)
        if cached:
            logger.debug(f"[FXService] Cache HIT for {source_currency}/{target_currency} on {cand_date}")
            return cached

        # 2. PostgreSQL Arşiv Kontrolü
        archived = await self._db_get(source_currency, target_currency, cand_date, rate_type)
        if archived:
            logger.debug(f"[FXService] DB Archive HIT for {source_currency}/{target_currency} on {cand_date}")
            await self._cache_set(cache_key, archived)
            return archived

        # 3. Sağlayıcıdan Çekim
        try:
            fetched_rates = await self.bulk_fetch_and_store(cand_date)
            matching = next(
                (
                    r
                    for r in fetched_rates
                    if r.source_currency == source_currency
                    and r.target_currency == target_currency
                    and r.rate_type == rate_type
                    and r.rate_date == cand_date
                ),
                None,
            )
            if matching:
                logger.info(f"[FXService] Provider fetch SUCCESS for {source_currency}/{target_currency} on {cand_date}")
                return matching
        except (FXRateNotFoundError, FXProviderError) as exc:
            logger.debug(f"[FXService] Provider fetch failed for {cand_date}: {exc}.")
        except Exception as exc:
            logger.warning(f"[FXService] Unexpected provider error for {cand_date}: {exc}.")

        return None

    async def get_rate(
        self,
        source_currency: str,
        target_currency: str = "TRY",
        rate_date: date | None = None,
        rate_type: str = "ForexSelling",
        max_lookback_days: int = 5,
    ) -> ExchangeRateDTO:
        """
        Döviz kurunu mimari çözümleme sırasına (Doğrudan -> Ters -> Çapraz, Lookback ve Fail-Closed)
        göre çözer ve normalize edilmiş ExchangeRateDTO döner.

        MİMARİ ÇÖZÜMLEME:
        1. source == target -> Kimlik (1.0)
        2. Doğrudan Kur (örn. USD -> TRY veya sağlayıcının doğrudan sunduğu çiftler)
        3. Ters Kur (TRY -> USD; TRY bazında 1 / (USD/TRY))
        4. Çapraz Kur (EUR -> USD; (EUR/TRY) ÷ (USD/TRY))
           - Çapraz kur bacakları KESİNLİKLE aynı resmi bülten tarihine (rate_date) ait olmalıdır.
        """
        src = validate_currency_code(source_currency, "source_currency")
        tgt = validate_currency_code(target_currency, "target_currency")

        today = datetime.now(timezone.utc).date()
        ref_date = rate_date or today

        # Adım 0: Para birimleri aynıysa doğrudan 1.0 kimlik kuru döner
        if src == tgt:
            return ExchangeRateDTO(
                source_currency=src,
                target_currency=tgt,
                rate=Decimal("1.0"),
                rate_type=rate_type,
                source="IDENTITY",
                rate_date=ref_date,
                fetched_at=datetime.now(timezone.utc),
                unit=1,
                bulletin_no="IDENTITY",
                conversion_path="IDENTITY",
                calculation_notes=f"[Aynı Para Birimi: {src} = {tgt} (Kur: 1.0)]",
            )

        # Gelecek tarih koruması
        if ref_date > today:
            raise FXFutureDateError(
                f"Requested rate date ({ref_date}) cannot be in the future (today is {today})."
            )

        # Aday tarih listesini oluştur (ref_date'den geriye doğru max_lookback_days gün)
        candidate_dates = resolve_candidate_dates(
            requested_date=ref_date,
            reference_today=today,
            max_lookback_days=max_lookback_days,
        )

        for cand_date in candidate_dates:
            # 1. Doğrudan çift kontrolü (örn. USD -> TRY veya mevcut önbellek kaydı)
            direct_dto = await self._resolve_direct_pair(src, tgt, cand_date, rate_type)
            if direct_dto:
                if direct_dto.rate <= Decimal("0"):
                    raise CurrencyConversionUnavailableException(
                        f"Geçersiz döviz kuru ({direct_dto.rate}): Kur değeri pozitif olmalıdır."
                    )
                calc_note = direct_dto.calculation_notes or (
                    f"[Doğrudan Kur: {src}/{tgt} = {direct_dto.rate} (Tarih: {cand_date}, {direct_dto.source} {rate_type})]"
                )
                return ExchangeRateDTO(
                    source_currency=direct_dto.source_currency,
                    target_currency=direct_dto.target_currency,
                    rate=direct_dto.rate,
                    rate_type=direct_dto.rate_type,
                    source=direct_dto.source,
                    rate_date=direct_dto.rate_date,
                    fetched_at=direct_dto.fetched_at,
                    unit=direct_dto.unit,
                    bulletin_no=direct_dto.bulletin_no,
                    conversion_path=direct_dto.conversion_path or "DIRECT",
                    calculation_notes=calc_note,
                )

            # 2. Ters Kur: TRY -> Yabancı Para (örn. TRY -> USD)
            if src == "TRY" and tgt != "TRY":
                tgt_try_dto = await self._resolve_direct_pair(tgt, "TRY", cand_date, rate_type)
                if tgt_try_dto:
                    if tgt_try_dto.rate <= Decimal("0"):
                        raise CurrencyConversionUnavailableException(
                            f"Geçersiz döviz kuru ({tgt_try_dto.rate}): Kur değeri sıfır veya negatif olamaz."
                        )
                    inv_rate = (Decimal("1") / tgt_try_dto.rate).quantize(
                        Decimal("0.000001"), rounding=ROUND_HALF_UP
                    )
                    inv_dto = ExchangeRateDTO(
                        source_currency=src,
                        target_currency=tgt,
                        rate=inv_rate,
                        rate_type=rate_type,
                        source=tgt_try_dto.source,
                        rate_date=cand_date,
                        fetched_at=tgt_try_dto.fetched_at,
                        unit=1,
                        bulletin_no=tgt_try_dto.bulletin_no,
                        conversion_path="INVERSE",
                        calculation_notes=f"[Ters Kur: 1 ÷ {tgt}/TRY ({tgt_try_dto.rate}) = {inv_rate} (Tarih: {cand_date}, {tgt_try_dto.source} {rate_type})]",
                    )
                    await self._cache_set(self._cache_key(src, tgt, cand_date, rate_type), inv_dto)
                    return inv_dto

            # 3. Çapraz Kur: Yabancı Para -> Yabancı Para (örn. EUR -> USD)
            if src != "TRY" and tgt != "TRY":
                src_try_dto = await self._resolve_direct_pair(src, "TRY", cand_date, rate_type)
                tgt_try_dto = await self._resolve_direct_pair(tgt, "TRY", cand_date, rate_type)

                # Katı Tarih Tutarlılığı: İki bacağın da AYNI resmi bülten gününde mevcut olması şarttır.
                if src_try_dto and tgt_try_dto:
                    if src_try_dto.rate_date != tgt_try_dto.rate_date or src_try_dto.rate_date != cand_date:
                        logger.warning(
                            f"[FXService] Date mismatch for cross rate legs on {cand_date}: "
                            f"{src}/TRY date={src_try_dto.rate_date}, {tgt}/TRY date={tgt_try_dto.rate_date}. Skipping candidate date."
                        )
                        continue

                    if src_try_dto.rate <= Decimal("0") or tgt_try_dto.rate <= Decimal("0"):
                        raise CurrencyConversionUnavailableException(
                            "Geçersiz döviz kuru: Çapraz kur bacaklarından biri sıfır veya negatif."
                        )

                    cross_rate = (src_try_dto.rate / tgt_try_dto.rate).quantize(
                        Decimal("0.000001"), rounding=ROUND_HALF_UP
                    )
                    cross_dto = ExchangeRateDTO(
                        source_currency=src,
                        target_currency=tgt,
                        rate=cross_rate,
                        rate_type=rate_type,
                        source=src_try_dto.source,
                        rate_date=cand_date,
                        fetched_at=max(src_try_dto.fetched_at, tgt_try_dto.fetched_at),
                        unit=1,
                        bulletin_no=src_try_dto.bulletin_no,
                        conversion_path="CROSS",
                        calculation_notes=(
                            f"[Çapraz Kur: {src}/TRY ({src_try_dto.rate}) ÷ {tgt}/TRY ({tgt_try_dto.rate}) = "
                            f"{cross_rate} (Ortak Tarih: {cand_date}, {src_try_dto.source} {rate_type})]"
                        ),
                    )
                    await self._cache_set(self._cache_key(src, tgt, cand_date, rate_type), cross_dto)
                    return cross_dto

        # Adım 5: Fail-Closed Güvenliği
        raise CurrencyConversionUnavailableException(
            f"Döviz kuru temin edilemedi: {src}/{tgt} için {ref_date} tarihinden geriye dönük "
            f"{max_lookback_days} gün boyunca geçerli bir resmi kur bulunamadı (fail-closed)."
        )

    async def convert_amount(
        self,
        amount: Decimal | str | int | float,
        source_currency: str,
        target_currency: str = "TRY",
        rate_date: date | None = None,
        rate_type: str = "ForexSelling",
        max_lookback_days: int = 5,
        quantize_places: str = "0.0001",
    ) -> Tuple[Decimal, ExchangeRateDTO]:
        """
        Belirtilen tutarı kur ile çarparak hedef para birimine dönüştürür.
        Tüm hesaplama Decimal ve ROUND_HALF_UP ile yapılır.
        Dönüş değeri: (dönüştürülmüş_tutar, kullanılan_kur_dto)
        """
        dto = await self.get_rate(
            source_currency=source_currency,
            target_currency=target_currency,
            rate_date=rate_date,
            rate_type=rate_type,
            max_lookback_days=max_lookback_days,
        )

        dec_amount = Decimal(str(amount))
        converted = (dec_amount * dto.rate).quantize(Decimal(quantize_places), rounding=ROUND_HALF_UP)
        return converted, dto
