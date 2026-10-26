"""
tests/test_fx_deterministic_integration.py

Milestone 2C: FX Integration into Deterministic Analysis Pipeline
Kapsamlı Entegrasyon ve Doğrulama Testleri.

Doğrulanan 12 Temel Senaryo:
1. Aynı para birimli analiz sorgusuz çalışır (kimlik kuru 1.0, DB/sağlayıcı çağrısı yok).
2. USD teklifi -> TRY bütçesi (doğrudan kur çevrimi ve TCO doğrulaması).
3. TRY teklifi -> USD bütçesi (ters kur çevrimi: 1 / (USD/TRY)).
4. EUR ve USD tekliflerinin tek bir ortak bütçe para biriminde karşılaştırılması.
5. TRY referanslı çapraz kur hesabı (EUR/USD = (EUR/TRY) / (USD/TRY)).
6. Farklı para birimlerine sahip tekliflerin dönüştürülmüş TCO üzerinden adil kıyaslanması.
7. Bütçe uyumluluğunun (ComplianceChecker) dönüştürülmüş TCO üzerinden denetlenmesi.
8. Kur bulunamadığında fail-closed davranışı (asla sahte uyumluluk üretilemez).
9. Tarih, kaynak, kur türü ve hesaplama notlarının TCOResult üzerinde eksiksiz kalıcı kaydı.
10. Nullable FX alanlarının eski/miras analiz kayıtlarıyla tam geriye uyumluluğu.
11. Yuvarlama (ROUND_HALF_UP), sıfır/negatif kur reddi ve finansal kesinlik sınırları.
12. Farklı günlere ait çapraz kur bacaklarının ASLA sessizce birleştirilmemesi (katı tarih tutarlılığı).
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import select, delete

from app.db.session import AsyncSessionLocal
from app.models.analysis import Analysis, AnalysisStatus, ComplianceCheck, ComplianceResult, TCOResult
from app.models.exchange_rate import ExchangeRate
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.quote import Quote
from app.models.rfq import RFQ
from app.models.supplier import Supplier
from app.services.deterministic.compliance import ComplianceChecker
from app.services.deterministic.orchestrator import DeterministicEngine
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.tco import TCOCalculator
from app.services.fx.base import BaseExchangeRateProvider
from app.services.fx.exceptions import CurrencyConversionUnavailableException
from app.services.fx.schemas import ExchangeRateDTO
from app.services.fx.service import ExchangeRateService


class MockRedis:
    """Testler için bellek içi kontrollü Redis istemcisi."""
    def __init__(self):
        self.store = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, val: str, ex: int | None = None):
        self.store[key] = val


@pytest.fixture(autouse=True)
async def cleanup_database_and_rates():
    """Her test öncesi ve sonrası exchange_rates tablosunu temizler."""
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ExchangeRate))
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ExchangeRate))
        await session.commit()


CURRENT_TEST_DATE = datetime.now(timezone.utc).date()


class DeterministicMockFXProvider(BaseExchangeRateProvider):
    """
    Deterministik test sağlayıcısı.
    Belirli tarihler ve para birimleri için kontrollü kur bültenleri döner.
    """

    def __init__(self, seeded_rates: list[ExchangeRateDTO] | None = None):
        self.rates: list[ExchangeRateDTO] = seeded_rates or []
        self.fetch_calls: list[date | None] = []

    async def fetch_rates(self, target_date: date | None = None) -> list[ExchangeRateDTO]:
        self.fetch_calls.append(target_date)
        if target_date is None:
            return self.rates
        return [r for r in self.rates if r.rate_date == target_date]

    def add_rate(
        self,
        source: str,
        target: str = "TRY",
        rate: Decimal = Decimal("40.000000"),
        rate_date: date | None = None,
        rate_type: str = "ForexSelling",
    ):
        if rate_date is None:
            rate_date = CURRENT_TEST_DATE
        self.rates.append(
            ExchangeRateDTO(
                source_currency=source,
                target_currency=target,
                rate=rate,
                rate_type=rate_type,
                source="MOCK_TCMB",
                rate_date=rate_date,
                fetched_at=datetime.now(timezone.utc),
                unit=1,
                bulletin_no="TEST-001",
            )
        )


async def _create_test_rfq_context(session, quote_currencies: list[str], prices: list[Decimal]):
    """Test için izole Org, Supplier, RFQ ve Quote'lar oluşturur."""
    unique = uuid.uuid4().hex[:8]
    org = Organization(name=f"Org {unique}", slug=f"org-{unique}")
    session.add(org)
    await session.flush()

    suppliers = []
    for i in range(len(quote_currencies)):
        sup = Supplier(name=f"Supplier {i}_{unique}", organization_id=org.id)
        session.add(sup)
        suppliers.append(sup)
    await session.flush()

    rfq = RFQ(
        organization_id=org.id,
        title=f"Test RFQ {unique}",
        budget=Decimal("1000000.00"),
    )
    session.add(rfq)
    await session.flush()

    quotes = []
    for i, (curr, price) in enumerate(zip(quote_currencies, prices)):
        q = Quote(
            rfq_id=rfq.id,
            supplier_id=suppliers[i].id,
            currency=curr,
            subtotal=price,
            vat_rate=Decimal("0.20"),
            vat_amount=price * Decimal("0.20"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=price * Decimal("1.20"),
            warranty_months=24,
            delivery_days=10,
        )
        session.add(q)
        quotes.append(q)

    await session.commit()
    for q in quotes:
        await session.refresh(q)
    await session.refresh(rfq)
    return rfq, quotes


# ─── TEST 1: SAME-CURRENCY NO FX LOOKUPS ──────────────────────────────────────

@pytest.mark.asyncio
async def test_same_currency_analysis_no_fx_lookups():
    """1. Aynı para birimli teklifler için FX araması yapılmaz; kimlik kuru 1.0 atanır."""
    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["TRY", "TRY"],
            prices=[Decimal("10000.00"), Decimal("15000.00")],
        )

        mock_provider = DeterministicMockFXProvider()
        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())
        engine = DeterministicEngine(db=session, fx_service=fx_service)

        rules = PolicyRules(max_tco_budget=50000.00, budget_currency="TRY")
        analysis = await engine.run_analysis(rfq.id, rules)

        assert len(analysis.tco_results) == 2
        for tco in analysis.tco_results:
            assert tco.converted_total_tco == tco.total_tco
            assert tco.target_currency == "TRY"
            assert tco.exchange_rate == Decimal("1.000000")
            assert tco.exchange_rate_source == "IDENTITY"
            assert "Aynı Para Birimi" in tco.calculation_notes

        # Dış sağlayıcı çağrılmamalıdır
        assert len(mock_provider.fetch_calls) == 0


# ─── TEST 2: USD QUOTE -> TRY BUDGET ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_usd_quote_to_try_budget_conversion():
    """2. USD teklifi TCMB kuru üzerinden TRY bütçesine doğru çevrilir."""
    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["USD", "USD"],
            prices=[Decimal("10000.00"), Decimal("12000.00")],
        )

        target_date = CURRENT_TEST_DATE
        mock_provider = DeterministicMockFXProvider()
        mock_provider.add_rate("USD", "TRY", rate=Decimal("40.000000"), rate_date=target_date)

        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())
        engine = DeterministicEngine(db=session, fx_service=fx_service)

        rules = PolicyRules(max_tco_budget=600000.00, budget_currency="TRY")
        analysis = await engine.run_analysis(rfq.id, rules)

        # Quote 1: subtotal 10,000 + 20% VAT = 12,000 USD
        # 12,000 USD * 40.000000 = 480,000 TRY
        tco1 = next(t for t in analysis.tco_results if t.quote_id == quotes[0].id)
        assert tco1.currency == "USD"
        assert tco1.total_tco == Decimal("12000.0000")
        assert tco1.converted_total_tco == Decimal("480000.0000")
        assert tco1.target_currency == "TRY"
        assert tco1.exchange_rate == Decimal("40.000000")
        assert tco1.exchange_rate_source == "MOCK_TCMB"
        assert tco1.exchange_rate_date == target_date
        assert "Doğrudan Kur: USD/TRY = 40.000000" in tco1.calculation_notes


# ─── TEST 3: TRY QUOTE -> USD BUDGET (INVERSE RATE) ───────────────────────────

@pytest.mark.asyncio
async def test_try_quote_to_usd_budget_inverse_conversion():
    """3. TRY teklifi USD bütçesine ters kur (1 / (USD/TRY)) ile çevrilir."""
    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["TRY", "TRY"],
            prices=[Decimal("400000.00"), Decimal("800000.00")],
        )

        # USD/TRY = 40.000000 -> Ters Kur: 1 / 40 = 0.025000
        target_date = CURRENT_TEST_DATE
        mock_provider = DeterministicMockFXProvider()
        mock_provider.add_rate("USD", "TRY", rate=Decimal("40.000000"), rate_date=target_date)

        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())
        engine = DeterministicEngine(db=session, fx_service=fx_service)

        # Bütçe 15,000 USD
        rules = PolicyRules(max_tco_budget=15000.00, budget_currency="USD")
        analysis = await engine.run_analysis(rfq.id, rules)

        # Quote 1: 400,000 + 20% = 480,000 TRY -> 480,000 * 0.025000 = 12,000 USD <= 15,000 USD (PASS)
        # Quote 2: 800,000 + 20% = 960,000 TRY -> 960,000 * 0.025000 = 24,000 USD > 15,000 USD (FAIL)
        tco1 = next(t for t in analysis.tco_results if t.quote_id == quotes[0].id)
        tco2 = next(t for t in analysis.tco_results if t.quote_id == quotes[1].id)

        assert tco1.converted_total_tco == Decimal("12000.0000")
        assert tco1.exchange_rate == Decimal("0.025000")
        assert "Ters Kur: 1 ÷ USD/TRY" in tco1.calculation_notes

        q1_check = next(c for c in analysis.compliance_checks if c.quote_id == quotes[0].id and c.rule_name == "max_tco_budget")
        q2_check = next(c for c in analysis.compliance_checks if c.quote_id == quotes[1].id and c.rule_name == "max_tco_budget")

        assert q1_check.result == ComplianceResult.PASS
        assert q2_check.result == ComplianceResult.FAIL
        assert "Bütçeyi aşıyor" in q2_check.notes


# ─── TEST 4: MIXED EUR & USD COMPARED UNDER TRY BUDGET ────────────────────────

@pytest.mark.asyncio
async def test_mixed_eur_and_usd_quotes_compared_under_try_budget():
    """4. Biri EUR diğeri USD olan iki teklif tek bir TRY bütçesinde doğru karşılaştırılır."""
    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["EUR", "USD"],
            prices=[Decimal("10000.00"), Decimal("10000.00")],
        )

        target_date = CURRENT_TEST_DATE
        mock_provider = DeterministicMockFXProvider()
        mock_provider.add_rate("EUR", "TRY", rate=Decimal("44.000000"), rate_date=target_date)
        mock_provider.add_rate("USD", "TRY", rate=Decimal("40.000000"), rate_date=target_date)

        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())
        engine = DeterministicEngine(db=session, fx_service=fx_service)

        rules = PolicyRules(max_tco_budget=500000.00, budget_currency="TRY")
        analysis = await engine.run_analysis(rfq.id, rules)

        # EUR Quote: 12,000 EUR * 44 = 528,000 TRY (Bütçeyi aşıyor -> FAIL)
        # USD Quote: 12,000 USD * 40 = 480,000 TRY (Bütçeye uygun -> PASS)
        tco_eur = next(t for t in analysis.tco_results if t.quote_id == quotes[0].id)
        tco_usd = next(t for t in analysis.tco_results if t.quote_id == quotes[1].id)

        assert tco_eur.converted_total_tco == Decimal("528000.0000")
        assert tco_usd.converted_total_tco == Decimal("480000.0000")

        eur_check = next(c for c in analysis.compliance_checks if c.quote_id == quotes[0].id and c.rule_name == "max_tco_budget")
        usd_check = next(c for c in analysis.compliance_checks if c.quote_id == quotes[1].id and c.rule_name == "max_tco_budget")

        assert eur_check.result == ComplianceResult.FAIL
        assert usd_check.result == ComplianceResult.PASS


# ─── TEST 5: CROSS-RATE CALCULATION (EUR -> USD via TRY) ──────────────────────

@pytest.mark.asyncio
async def test_cross_rate_calculation_using_try_reference():
    """5. Çapraz kur (EUR -> USD) TRY referansıyla: (EUR/TRY) / (USD/TRY) = 44 / 40 = 1.100000."""
    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["EUR", "USD"],
            prices=[Decimal("10000.00"), Decimal("10000.00")],
        )

        target_date = CURRENT_TEST_DATE
        mock_provider = DeterministicMockFXProvider()
        mock_provider.add_rate("EUR", "TRY", rate=Decimal("44.000000"), rate_date=target_date)
        mock_provider.add_rate("USD", "TRY", rate=Decimal("40.000000"), rate_date=target_date)

        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())
        engine = DeterministicEngine(db=session, fx_service=fx_service)

        # Hedef bütçe USD cinsinden:
        rules = PolicyRules(max_tco_budget=15000.00, budget_currency="USD")
        analysis = await engine.run_analysis(rfq.id, rules)

        # EUR teklifi USD'ye çevrilmeli: 12,000 EUR * 1.100000 = 13,200 USD
        tco_eur = next(t for t in analysis.tco_results if t.quote_id == quotes[0].id)
        assert tco_eur.currency == "EUR"
        assert tco_eur.target_currency == "USD"
        assert tco_eur.exchange_rate == Decimal("1.100000")
        assert tco_eur.converted_total_tco == Decimal("13200.0000")
        assert "Çapraz Kur: EUR/TRY (44.000000) ÷ USD/TRY (40.000000) = 1.100000" in tco_eur.calculation_notes

        # USD teklifi USD'ye kimlik kuruyla çevrilmeli: 12,000 USD * 1.0 = 12,000 USD
        tco_usd = next(t for t in analysis.tco_results if t.quote_id == quotes[1].id)
        assert tco_usd.exchange_rate == Decimal("1.000000")
        assert tco_usd.converted_total_tco == Decimal("12000.0000")


# ─── TEST 6: COMPARABLE TCO RANKING WITH DIFFERENT CURRENCIES ─────────────────

@pytest.mark.asyncio
async def test_comparable_tco_ranking_with_different_quote_currencies():
    """6. Farklı para birimlerine sahip teklifler dönüştürülmüş TCO ile doğru sıralanabilir."""
    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["USD", "TRY"],
            # Quote 1: 100 USD (TCO = 120 USD = 4,800 TRY)
            # Quote 2: 5,000 TRY (TCO = 6,000 TRY)
            prices=[Decimal("100.00"), Decimal("5000.00")],
        )

        mock_provider = DeterministicMockFXProvider()
        mock_provider.add_rate("USD", "TRY", rate=Decimal("40.000000"), rate_date=CURRENT_TEST_DATE)

        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())
        engine = DeterministicEngine(db=session, fx_service=fx_service)

        rules = PolicyRules(max_tco_budget=10000.00, budget_currency="TRY")
        analysis = await engine.run_analysis(rfq.id, rules)

        tcos = sorted(analysis.tco_results, key=lambda x: x.converted_total_tco)
        # 4,800 TRY < 6,000 TRY
        assert tcos[0].quote_id == quotes[0].id
        assert tcos[0].converted_total_tco == Decimal("4800.0000")
        assert tcos[1].quote_id == quotes[1].id
        assert tcos[1].converted_total_tco == Decimal("6000.0000")


# ─── TEST 7: BUDGET COMPLIANCE EVALUATES CONVERTED TCO ────────────────────────

def test_budget_compliance_evaluates_converted_tco():
    """7. ComplianceChecker bütçe kuralını doğrudan dönüştürülmüş TCO üzerinden değerlendirir."""
    analysis_id = uuid.uuid4()
    quote = Quote(
        id=uuid.uuid4(),
        rfq_id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        subtotal=Decimal("100.00"),
        total_price=Decimal("120.00"),
        currency="USD",
        delivery_days=5,
        warranty_months=24,
    )

    # 120 USD -> 4,800 TRY
    tco_under_budget = TCOResult(
        quote_id=quote.id,
        analysis_id=analysis_id,
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("20.00"),
        shipping_cost=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        other_costs=Decimal("0.00"),
        total_tco=Decimal("120.00"),
        currency="USD",
        converted_total_tco=Decimal("4800.0000"),
        target_currency="TRY",
        exchange_rate=Decimal("40.000000"),
    )

    rules = PolicyRules(max_tco_budget=5000.00, budget_currency="TRY")
    checks = ComplianceChecker.check_quote(quote, tco_under_budget, rules, analysis_id)
    budget_check = next(c for c in checks if c.rule_name == "max_tco_budget")
    assert budget_check.result == ComplianceResult.PASS
    assert float(budget_check.actual_value) == 4800.0

    # 120 USD -> 5,500 TRY (Bütçeyi aşıyor)
    tco_over_budget = TCOResult(
        quote_id=quote.id,
        analysis_id=analysis_id,
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("20.00"),
        shipping_cost=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        other_costs=Decimal("0.00"),
        total_tco=Decimal("120.00"),
        currency="USD",
        converted_total_tco=Decimal("5500.0000"),
        target_currency="TRY",
        exchange_rate=Decimal("45.833333"),
    )
    checks2 = ComplianceChecker.check_quote(quote, tco_over_budget, rules, analysis_id)
    budget_check2 = next(c for c in checks2 if c.rule_name == "max_tco_budget")
    assert budget_check2.result == ComplianceResult.FAIL
    assert "Bütçeyi aşıyor" in budget_check2.notes


# ─── TEST 8: MISSING FX RATES FAIL CLOSED ─────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_fx_rates_fail_closed_prevents_false_compliance():
    """8. Kur bulunamadığında analiz fail-closed olarak reddedilir; sahte uyumluluk üretilmez."""
    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["EUR", "USD"],
            prices=[Decimal("1000.00"), Decimal("1000.00")],
        )

        # Boş mock sağlayıcı (hiç kur yok)
        empty_provider = DeterministicMockFXProvider(seeded_rates=[])
        fx_service = ExchangeRateService(db=session, provider=empty_provider, redis_client=MockRedis())
        engine = DeterministicEngine(db=session, fx_service=fx_service)

        rules = PolicyRules(max_tco_budget=100000.00, budget_currency="TRY")
        with pytest.raises(ValueError) as exc_info:
            await engine.run_analysis(rfq.id, rules)

        assert "Doğrulanmış döviz kuru olmadan doğrudan sayısal karşılaştırmaya izin verilmez" in str(exc_info.value)


# ─── TEST 9: AUDIT FIELDS PERSISTED ON TCO_RESULT ─────────────────────────────

@pytest.mark.asyncio
async def test_historical_audit_fields_persisted_on_tco_result():
    """9. TCOResult üzerindeki tüm FX alanları (oran, tarih, kaynak, tür, not) veritabanına yazılır."""
    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["USD", "USD"],
            prices=[Decimal("5000.00"), Decimal("6000.00")],
        )

        test_date = CURRENT_TEST_DATE
        mock_provider = DeterministicMockFXProvider()
        mock_provider.add_rate("USD", "TRY", rate=Decimal("40.123456"), rate_date=test_date)

        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())
        engine = DeterministicEngine(db=session, fx_service=fx_service)

        rules = PolicyRules(max_tco_budget=500000.00, budget_currency="TRY")
        analysis = await engine.run_analysis(rfq.id, rules)

        # Doğrudan veritabanından taze kayıt çekip doğrula
        stmt = select(TCOResult).where(TCOResult.analysis_id == analysis.id)
        rows = (await session.execute(stmt)).scalars().all()
        assert len(rows) == 2
        for r in rows:
            assert r.target_currency == "TRY"
            assert r.exchange_rate == Decimal("40.123456")
            assert r.exchange_rate_date == test_date
            assert r.exchange_rate_source == "MOCK_TCMB"
            assert r.exchange_rate_type == "ForexSelling"
            assert r.calculation_notes is not None
            assert "USD/TRY = 40.123456" in r.calculation_notes


# ─── TEST 10: NULLABLE FX FIELDS DO NOT BREAK LEGACY ANALYSES ─────────────────

@pytest.mark.asyncio
async def test_existing_nullable_fx_fields_do_not_break_legacy_records():
    """10. FX alanları NULL olan eski analiz kayıtları hatasız okunabilir."""
    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["TRY", "TRY"],
            prices=[Decimal("1000.00"), Decimal("2000.00")],
        )

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED)
        session.add(analysis)
        await session.flush()

        # Legacy TCOResult (FX alanları None)
        legacy_tco = TCOResult(
            analysis_id=analysis.id,
            quote_id=quotes[0].id,
            subtotal=Decimal("1000.00"),
            vat_amount=Decimal("200.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_tco=Decimal("1200.00"),
            currency="TRY",
            converted_total_tco=None,
            target_currency=None,
            exchange_rate=None,
            exchange_rate_date=None,
            exchange_rate_source=None,
            exchange_rate_type=None,
            calculation_notes="Eski analiz kaydı",
        )
        session.add(legacy_tco)
        await session.commit()

        # Veritabanından geri oku
        stmt = select(TCOResult).where(TCOResult.id == legacy_tco.id)
        row = (await session.execute(stmt)).scalar_one()
        assert row.converted_total_tco is None
        assert row.exchange_rate is None
        assert row.total_tco == Decimal("1200.0000")


# ─── TEST 11: ROUNDING & ZERO/NEGATIVE RATE REJECTION ─────────────────────────

@pytest.mark.asyncio
async def test_zero_and_negative_rate_rejection():
    """11A. Sıfır veya negatif kurlar reddedilir (fail-closed)."""
    async with AsyncSessionLocal() as session:
        mock_provider = DeterministicMockFXProvider()
        # Sıfır kur
        mock_provider.add_rate("USD", "TRY", rate=Decimal("0.000000"), rate_date=date(2026, 10, 20))
        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())

        with pytest.raises(CurrencyConversionUnavailableException) as exc_info:
            await fx_service.get_rate("USD", "TRY", rate_date=date(2026, 10, 20))
        assert "pozitif olmalıdır" in str(exc_info.value).lower() or "sıfır veya negatif" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_monetary_rounding_and_decimal_precision():
    """11B. ROUND_HALF_UP ve Decimal finansal kesinliği kuruş/santim bazında tam korunur."""
    async with AsyncSessionLocal() as session:
        mock_provider_precise = DeterministicMockFXProvider()
        mock_provider_precise.add_rate("USD", "TRY", rate=Decimal("33.333333"), rate_date=date(2026, 10, 20))
        fx_service = ExchangeRateService(db=session, provider=mock_provider_precise, redis_client=MockRedis())

        converted, dto = await fx_service.convert_amount(
            amount=Decimal("100.1250"),
            source_currency="USD",
            target_currency="TRY",
            rate_date=date(2026, 10, 20),
            quantize_places="0.0001",
        )
        expected = (Decimal("100.1250") * Decimal("33.333333")).quantize(Decimal("0.0001"))
        assert converted == expected
        assert converted == Decimal("3337.5000")


# ─── TEST 12: CROSS-RATE STRICT DATE CONSISTENCY (NO MIXED DATES) ─────────────

@pytest.mark.asyncio
async def test_cross_rate_rejects_inconsistent_leg_dates_and_advances_lookback():
    """
    12. Farklı günlere ait çapraz kur bacakları ASLA birleştirilmez.
    Örn: Gün D'de EUR/TRY var ancak USD/TRY yoksa, D günü reddedilir ve
    iki bacağın da mevcut olduğu bir önceki iş günü (D-1) kullanılır.
    """
    async with AsyncSessionLocal() as session:
        day_d = date(2026, 10, 20)
        day_d_minus_1 = date(2026, 10, 19)

        mock_provider = DeterministicMockFXProvider()
        # Gün D: Sadece EUR var, USD eksik
        mock_provider.add_rate("EUR", "TRY", rate=Decimal("45.000000"), rate_date=day_d)

        # Gün D-1: Hem EUR hem USD var
        mock_provider.add_rate("EUR", "TRY", rate=Decimal("44.000000"), rate_date=day_d_minus_1)
        mock_provider.add_rate("USD", "TRY", rate=Decimal("40.000000"), rate_date=day_d_minus_1)

        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())

        # ref_date=day_d isteniyor:
        cross_dto = await fx_service.get_rate(
            source_currency="EUR",
            target_currency="USD",
            rate_date=day_d,
            max_lookback_days=5,
        )

        # Asla Gün D'nin EUR'u (45) ile Gün D-1'in USD'si (40) birleştirilmemelidir!
        # İki bacak da Gün D-1'den çözümlenmelidir: 44 / 40 = 1.100000
        assert cross_dto.rate_date == day_d_minus_1
        assert cross_dto.rate == Decimal("1.100000")
        assert "Ortak Tarih: 2026-10-19" in cross_dto.calculation_notes


# ─── TEST 13: FX AUDIT EVIDENCE & API SCHEMA SERIALIZATION ───────────────────

@pytest.mark.asyncio
async def test_fx_audit_evidence_and_api_schema_serialization():
    """
    13. Milestone 2D: API şemaları (TCOResultResponse, EvidenceItemResponse) ve
    EvidenceItem modeli üzerinden FX denetim kanıtlarının doğrulanması.
    """
    from app.api.v1.analyses import EvidenceItemResponse, TCOResultResponse

    async with AsyncSessionLocal() as session:
        rfq, quotes = await _create_test_rfq_context(
            session,
            quote_currencies=["USD", "USD"],
            prices=[Decimal("10000.00"), Decimal("12000.00")],
        )

        target_date = CURRENT_TEST_DATE
        mock_provider = DeterministicMockFXProvider()
        mock_provider.add_rate("USD", "TRY", rate=Decimal("40.000000"), rate_date=target_date)

        fx_service = ExchangeRateService(db=session, provider=mock_provider, redis_client=MockRedis())
        engine = DeterministicEngine(db=session, fx_service=fx_service)

        rules = PolicyRules(max_tco_budget=600000.00, budget_currency="TRY")
        analysis = await engine.run_analysis(rfq.id, rules)

        # 1. EvidenceItem kaydı oluştuğunu doğrula
        fx_evidence_items = [ev for ev in analysis.evidence_items if ev.source_type == "fx_rate"]
        assert len(fx_evidence_items) == 2
        for ev in fx_evidence_items:
            assert "TCMB" in ev.source_reference
            assert "ForexSelling" in ev.source_reference
            assert target_date.isoformat() in ev.source_reference
            assert "Doğrudan Kur: USD/TRY = 40.000000" in ev.content

            # Pydantic EvidenceItemResponse şemasına serialize et
            ev_resp = EvidenceItemResponse.model_validate(ev)
            assert ev_resp.source_type == "fx_rate"
            assert ev_resp.content is not None
            assert "USD/TRY = 40.000000" in ev_resp.content

        # 2. TCOResultResponse Pydantic şemasını ve conversion_path özelliğini doğrula
        for tco in analysis.tco_results:
            assert tco.conversion_path == "DIRECT"
            tco_resp = TCOResultResponse.model_validate(tco)
            assert tco_resp.converted_total_tco == float(tco.converted_total_tco)
            assert tco_resp.target_currency == "TRY"
            assert tco_resp.exchange_rate == 40.0
            assert tco_resp.exchange_rate_date == target_date
            assert tco_resp.exchange_rate_source == "MOCK_TCMB"
            assert tco_resp.exchange_rate_type == "ForexSelling"
            assert tco_resp.conversion_path == "DIRECT"
            assert tco_resp.calculation_notes is not None
