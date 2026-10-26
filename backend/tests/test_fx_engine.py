"""
tests/test_fx_engine.py

FX Engine (Döviz Kuru Çevirisi) Milestone 2A Kapsamlı Test Paketi.
Ağ bağımlılığı olmadan, mock ve XML fixture'ları kullanarak tüm temel iş kurallarını doğrular:
  1. XML içinden USD ve EUR kur alanlarının ayrıştırılması.
  2. JPY gibi Unit > 1 durumunda doğru birim normalizasyonu.
  3. Desteklenmeyen para birimi veya eksik kur alanı.
  4. Bozuk XML ve HTTP/provider hataları.
  5. Geçersiz veya sıfır kur oranının reddedilmesi.
  6. Para birimi aynı olduğunda 1 oranlı dönüşüm davranışı.
  7. Decimal hassasiyetinin korunması (float kesinlikle kullanılmaz).
  8. Model metadata ve TCOResult nullable alanları tutarlılığı.
  9. Tarih fallback sınırı ve geleceğe ait bültenin reddedilmesi.
  10. Mock provider deterministik davranış testleri.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest

from app.models.exchange_rate import ExchangeRate
from app.models.analysis import TCOResult
from app.services.fx.exceptions import (
    FXFutureDateError,
    FXInvalidDataError,
    FXRateNotFoundError,
)
from app.services.fx.mock_provider import MockExchangeRateProvider
from app.services.fx.policy import (
    calculate_conversion,
    is_same_currency,
    resolve_candidate_dates,
    validate_currency_code,
)
from app.services.fx.tcmb_provider import parse_tcmb_xml


SAMPLE_TCMB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Tarih_Date Tarih="20.10.2026" Date="10/20/2026" Bulten_No="2026/198">
    <Currency CrossOrder="0" Kod="USD" CurrencyCode="USD">
        <Unit>1</Unit>
        <Isim>ABD DOLARI</Isim>
        <CurrencyName>US DOLLAR</CurrencyName>
        <ForexBuying>49.4889</ForexBuying>
        <ForexSelling>49.5780</ForexSelling>
        <BanknoteBuying>49.4542</BanknoteBuying>
        <BanknoteSelling>49.6524</BanknoteSelling>
    </Currency>
    <Currency CrossOrder="1" Kod="EUR" CurrencyCode="EUR">
        <Unit>1</Unit>
        <Isim>EURO</Isim>
        <CurrencyName>EURO</CurrencyName>
        <ForexBuying>53.9510</ForexBuying>
        <ForexSelling>54.0483</ForexSelling>
        <BanknoteBuying>53.9133</BanknoteBuying>
        <BanknoteSelling>54.1294</BanknoteSelling>
    </Currency>
    <Currency CrossOrder="2" Kod="JPY" CurrencyCode="JPY">
        <Unit>100</Unit>
        <Isim>JAPON YENI</Isim>
        <CurrencyName>JAPANESE YEN</CurrencyName>
        <ForexBuying>31.2185</ForexBuying>
        <ForexSelling>31.4269</ForexSelling>
        <BanknoteBuying>30.9063</BanknoteBuying>
        <BanknoteSelling>31.7412</BanknoteSelling>
    </Currency>
    <Currency CrossOrder="3" Kod="XAU" CurrencyCode="XAU">
        <Unit>1</Unit>
        <Isim>ALTIN</Isim>
        <CurrencyName>GOLD</CurrencyName>
        <ForexBuying></ForexBuying>
        <ForexSelling></ForexSelling>
    </Currency>
</Tarih_Date>
"""


# ── Test 1: USD and EUR XML Parsing ──────────────────────────────────────────

def test_parse_tcmb_xml_usd_and_eur():
    """1. Validates extraction of USD and EUR exchange rates from TCMB XML."""
    fetched_at = datetime(2026, 10, 21, 10, 0, 0, tzinfo=timezone.utc)
    rates = parse_tcmb_xml(SAMPLE_TCMB_XML, fetched_at=fetched_at)

    assert len(rates) > 0

    # Check USD ForexSelling
    usd_selling = next(
        r for r in rates if r.source_currency == "USD" and r.rate_type == "ForexSelling"
    )
    assert usd_selling.target_currency == "TRY"
    assert usd_selling.rate == Decimal("49.5780")
    assert usd_selling.rate_date == date(2026, 10, 20)
    assert usd_selling.bulletin_no == "2026/198"
    assert usd_selling.unit == 1
    assert usd_selling.source == "TCMB"
    assert usd_selling.fetched_at == fetched_at

    # Check EUR ForexSelling
    eur_selling = next(
        r for r in rates if r.source_currency == "EUR" and r.rate_type == "ForexSelling"
    )
    assert eur_selling.target_currency == "TRY"
    assert eur_selling.rate == Decimal("54.0483")
    assert eur_selling.rate_date == date(2026, 10, 20)


# ── Test 2: JPY Unit Normalization ────────────────────────────────────────────

def test_parse_tcmb_xml_jpy_unit_normalization():
    """2. Validates that Unit=100 (JPY) is normalized to rate per 1 unit."""
    rates = parse_tcmb_xml(SAMPLE_TCMB_XML)

    jpy_selling = next(
        r for r in rates if r.source_currency == "JPY" and r.rate_type == "ForexSelling"
    )
    assert jpy_selling.unit == 100
    # Published 31.4269 / 100 = 0.314269
    expected_rate = Decimal("31.4269") / Decimal("100")
    assert jpy_selling.rate == expected_rate
    assert jpy_selling.rate == Decimal("0.314269")


# ── Test 3: Unsupported Currency or Missing Fields ───────────────────────────

def test_parse_tcmb_xml_unsupported_or_empty_rates():
    """3. Validates that empty currency rate fields (like XAU above) are not hallucinated."""
    rates = parse_tcmb_xml(SAMPLE_TCMB_XML)
    xau_rates = [r for r in rates if r.source_currency == "XAU"]
    assert len(xau_rates) == 0  # Both ForexBuying and ForexSelling were empty


# ── Test 4: Corrupted XML & Provider Errors ───────────────────────────────────

def test_parse_tcmb_xml_corrupted_payload():
    """4. Validates that empty, non-XML, or missing 'Tarih' attributes raise FXInvalidDataError."""
    # Empty bytes
    with pytest.raises(FXInvalidDataError, match="empty"):
        parse_tcmb_xml(b"")

    # Malformed XML syntax
    with pytest.raises(FXInvalidDataError, match="Malformed"):
        parse_tcmb_xml(b"<Tarih_Date><unclosed>")

    # Missing Tarih attribute
    with pytest.raises(FXInvalidDataError, match="Tarih"):
        parse_tcmb_xml(b"<Tarih_Date Bulten_No='123'><Currency Kod='USD'/></Tarih_Date>")


# ── Test 5: Invalid or Zero/Negative Rate Rejection ───────────────────────────

def test_invalid_or_zero_negative_rate_rejection():
    """5. Validates rejection of non-positive or malformed rates in policy and model."""
    # Policy rejection
    with pytest.raises(FXInvalidDataError, match="strictly positive"):
        calculate_conversion(Decimal("100"), Decimal("0"))

    with pytest.raises(FXInvalidDataError, match="strictly positive"):
        calculate_conversion(Decimal("100"), Decimal("-5.25"))

    # Model validation rejection
    with pytest.raises(ValueError, match="positive and non-zero"):
        ExchangeRate(
            source_currency="USD",
            target_currency="TRY",
            rate=Decimal("-1.0"),
            rate_date=date(2026, 10, 20),
            fetched_at=datetime.now(timezone.utc),
        )


# ── Test 6: Same Currency Conversion ──────────────────────────────────────────

def test_same_currency_identity_conversion():
    """6. Validates that matching currencies (e.g. TRY to try) convert with 1.0 identity."""
    assert is_same_currency("TRY", "try") is True
    assert is_same_currency("USD", "usd") is True
    assert is_same_currency("USD", "TRY") is False

    converted = calculate_conversion(Decimal("500000.00"), Decimal("1"))
    assert converted == Decimal("500000.00")


# ── Test 7: Decimal Precision Preservation ────────────────────────────────────

def test_decimal_precision_preservation():
    """7. Validates high financial precision without IEEE 754 floating point drift."""
    amount = Decimal("1234567.89")
    rate = Decimal("34.123456")

    converted = calculate_conversion(amount, rate)
    expected = Decimal("42127723.07342784")
    assert converted == expected
    assert isinstance(converted, Decimal)


# ── Test 8: Model & Migration Consistency ────────────────────────────────────

def test_exchange_rate_model_and_tco_result_fields_consistency():
    """8. Validates model column definitions and metadata registration."""
    # ExchangeRate columns
    rate_cols = {c.name for c in ExchangeRate.__table__.columns}
    expected_rate_cols = {
        "id",
        "source_currency",
        "target_currency",
        "rate",
        "rate_type",
        "source",
        "rate_date",
        "fetched_at",
        "unit",
        "bulletin_no",
        "created_at",
    }
    assert expected_rate_cols.issubset(rate_cols)

    # TCOResult extended columns
    tco_cols = {c.name for c in TCOResult.__table__.columns}
    expected_tco_cols = {
        "converted_total_tco",
        "target_currency",
        "exchange_rate",
        "exchange_rate_date",
        "exchange_rate_source",
        "exchange_rate_type",
    }
    assert expected_tco_cols.issubset(tco_cols)

    # Unique constraint check
    uq_names = [c.name for c in ExchangeRate.__table__.constraints if hasattr(c, "columns")]
    assert "uq_exchange_rates_entry" in uq_names


# ── Test 9: Date Fallback Lookback & Future Date Rejection ─────────────────────

def test_date_lookback_policy_and_future_date_rejection():
    """9. Validates lookback candidate generation and strict future date rejection."""
    today = date(2026, 10, 21)

    # Future date rejected
    future_date = date(2026, 10, 25)
    with pytest.raises(FXFutureDateError, match="future"):
        resolve_candidate_dates(future_date, reference_today=today)

    # Sunday candidate list generates today down to 7 days prior
    sunday = date(2026, 10, 18)
    candidates = resolve_candidate_dates(sunday, reference_today=today, max_lookback_days=7)
    assert len(candidates) == 8  # requested + 7 offsets
    assert candidates[0] == sunday
    assert candidates[1] == date(2026, 10, 17)  # Saturday
    assert candidates[2] == date(2026, 10, 16)  # Friday (last active business day)
    assert candidates[-1] == date(2026, 10, 11)


# ── Test 10: Mock Provider Behavior ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_provider_behavior():
    """10. Validates MockExchangeRateProvider behavior for deterministic tests."""
    mock = MockExchangeRateProvider()

    # Empty mock raises FXRateNotFoundError
    with pytest.raises(FXRateNotFoundError):
        await mock.fetch_rates(date(2026, 10, 20))

    # Add USD and EUR rates
    mock.add_rate("USD", "TRY", rate=Decimal("34.250000"), rate_date=date(2026, 10, 20))
    mock.add_rate("EUR", "TRY", rate=Decimal("37.150000"), rate_date=date(2026, 10, 20))

    rates = await mock.fetch_rates(date(2026, 10, 20))
    assert len(rates) == 2
    assert mock.call_count == 2

    # Query latest (None)
    latest_rates = await mock.fetch_rates(None)
    assert len(latest_rates) == 2


# ── Test 11: Freshness Policy Verification (Weekends & Weekdays) ─────────────

def test_is_rate_fresh_policy():
    """11. Validates is_rate_fresh behavior across calendar and business day intervals."""
    from app.services.fx.policy import is_rate_fresh

    # Scenario A: Same calendar day is fresh
    assert is_rate_fresh(requested_date=date(2026, 10, 23), rate_date=date(2026, 10, 23)) is True

    # Scenario B: 1 calendar day lag on weekday (Thursday rate requested on Friday)
    assert is_rate_fresh(requested_date=date(2026, 10, 23), rate_date=date(2026, 10, 22)) is True

    # Scenario C: Friday rate requested on Monday (TCMB weekend publishing cycle)
    # 2026-10-23 is Friday, 2026-10-26 is Monday. Calendar diff: 3 days, business days lag: 1.
    assert is_rate_fresh(requested_date=date(2026, 10, 26), rate_date=date(2026, 10, 23)) is True

    # Scenario D: Friday rate requested over weekend (Saturday & Sunday)
    assert is_rate_fresh(requested_date=date(2026, 10, 24), rate_date=date(2026, 10, 23)) is True
    assert is_rate_fresh(requested_date=date(2026, 10, 25), rate_date=date(2026, 10, 23)) is True

    # Scenario E: Mid-week stale gap (Friday rate requested on Thursday next week, 4 business days elapsed)
    assert is_rate_fresh(requested_date=date(2026, 10, 29), rate_date=date(2026, 10, 23)) is False

    # Scenario F: Older than max_lookback_days (e.g. 7 calendar days)
    assert is_rate_fresh(requested_date=date(2026, 10, 30), rate_date=date(2026, 10, 23), max_lookback_days=5) is False

    # Scenario G: Future rate date is rejected
    assert is_rate_fresh(requested_date=date(2026, 10, 20), rate_date=date(2026, 10, 23)) is False


# ── Test 12: TCMB Provider Timeout Handling ──────────────────────────────────

@pytest.mark.asyncio
async def test_tcmb_provider_network_timeout(monkeypatch):
    """12. Validates that httpx.TimeoutException is caught and raised as FXProviderError."""
    import httpx
    from app.services.fx.tcmb_provider import TCMBExchangeRateProvider
    from app.services.fx.exceptions import FXProviderError

    async def mock_get(*args, **kwargs):
        raise httpx.ConnectTimeout("Connection handshake timed out")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    provider = TCMBExchangeRateProvider(max_retries=1)
    with pytest.raises(FXProviderError, match="TCMB network communication error"):
        await provider.fetch_rates(target_date=date(2026, 10, 23))


# ── Test 13: Malformed XML Response Handling ─────────────────────────────────

def test_tcmb_provider_malformed_xml():
    """13. Validates that corrupt/malformed XML raises FXInvalidDataError."""
    corrupt_xml = b"<?xml version='1.0'?><Tarih_Date Tarih='20.10.2026'><UnclosedTag>"
    with pytest.raises(FXInvalidDataError, match="Malformed TCMB XML response"):
        parse_tcmb_xml(corrupt_xml)

    empty_xml = b""
    with pytest.raises(FXInvalidDataError, match="empty"):
        parse_tcmb_xml(empty_xml)

    missing_date_xml = b"<?xml version='1.0'?><Tarih_Date Bulten_No='123'></Tarih_Date>"
    with pytest.raises(FXInvalidDataError, match="missing 'Tarih'"):
        parse_tcmb_xml(missing_date_xml)


# ── Test 14: Weekend Date Request Rejection ───────────────────────────────────

@pytest.mark.asyncio
async def test_tcmb_provider_weekend_date_rejection():
    """14. Validates that requesting a past weekend date directly raises FXRateNotFoundError without network calls."""
    from app.services.fx.tcmb_provider import TCMBExchangeRateProvider

    provider = TCMBExchangeRateProvider()
    # 2026-10-25 is Sunday
    with pytest.raises(FXRateNotFoundError, match="weekends"):
        await provider.fetch_rates(target_date=date(2026, 10, 25))


# ── Test 15: Strict TLS 1.2 Configuration Verification ───────────────────────

def test_tcmb_ssl_context_strict_verification():
    """15. Validates that create_tcmb_ssl_context enforces TLS 1.2 with strict certificate verification."""
    import ssl
    from app.services.fx.tcmb_provider import create_tcmb_ssl_context

    ctx = create_tcmb_ssl_context()
    assert ctx.maximum_version == ssl.TLSVersion.TLSv1_2
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True

