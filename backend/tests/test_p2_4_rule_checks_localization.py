"""
tests/test_p2_4_rule_checks_localization.py

P2.4 Deterministic Rule Checks Localization & Invariance Tests:
1. Validates all 6 hard rules generate English descriptions and notes when locale="en".
2. Validates all 6 hard rules generate Turkish descriptions and notes when locale="tr".
3. Asserts complete mathematical and logical invariance:
   - PASS/FAIL/WARNING outcomes are 100% identical regardless of locale.
   - actual_value and required_value numbers are 100% identical.
   - Quotations, terms, and currency codes remain intact.
"""

import uuid
from decimal import Decimal
import pytest

from app.models.analysis import ComplianceResult
from app.models.quote import Quote
from app.services.deterministic.compliance import ComplianceChecker
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.tco import TCOResult, TCOCalculator


def _create_sample_quote(
    delivery_days: int = 15,
    warranty_months: int = 24,
    total_price: Decimal = Decimal("120000.00"),
    currency: str = "TRY",
    payment_terms: str = "net-30",
    extraction_confidence: Decimal = Decimal("0.95"),
    subtotal: Decimal | None = Decimal("100000.00"),
    vat_rate: Decimal | None = Decimal("0.2000"),
    shipping_cost: Decimal | None = Decimal("0.0000"),
) -> Quote:
    return Quote(
        id=uuid.uuid4(),
        rfq_id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        subtotal=subtotal,
        vat_rate=vat_rate,
        vat_amount=Decimal("20000.00") if vat_rate is not None else None,
        shipping_cost=shipping_cost,
        discount_amount=Decimal("0.00"),
        other_costs=Decimal("0.00"),
        total_price=total_price,
        currency=currency,
        delivery_days=delivery_days,
        warranty_months=warranty_months,
        payment_terms=payment_terms,
        extraction_confidence=extraction_confidence,
    )


def test_all_rules_turkish_output():
    """Verify default (tr) outputs for all 6 deterministic rules."""
    analysis_id = uuid.uuid4()
    quote = _create_sample_quote()
    tco_res = TCOCalculator.calculate(quote, analysis_id)
    rules = PolicyRules(
        max_delivery_days=30,
        min_warranty_months=12,
        max_tco_budget=150000.00,
        budget_currency="TRY",
        require_payment_terms=["net-30"],
    )

    checks = ComplianceChecker.check_quote(
        quote=quote,
        tco_result=tco_res,
        rules=rules,
        analysis_id=analysis_id,
        locale="tr",
    )

    check_map = {c.rule_name: c for c in checks}

    # 1. max_delivery_days
    assert check_map["max_delivery_days"].rule_description == "Maksimum teslimat süresi kontrolü"
    assert check_map["max_delivery_days"].notes == "Uygun."
    assert check_map["max_delivery_days"].result == ComplianceResult.PASS

    # 2. min_warranty_months
    assert check_map["min_warranty_months"].rule_description == "Minimum garanti süresi kontrolü"
    assert check_map["min_warranty_months"].notes == "Uygun."
    assert check_map["min_warranty_months"].result == ComplianceResult.PASS

    # 3. max_tco_budget
    assert check_map["max_tco_budget"].rule_description == "Maksimum bütçe kontrolü"
    assert check_map["max_tco_budget"].notes == "Uygun."
    assert check_map["max_tco_budget"].result == ComplianceResult.PASS

    # 4. require_payment_terms
    assert check_map["require_payment_terms"].rule_description == "Zorunlu ödeme koşulu kontrolü"
    assert check_map["require_payment_terms"].notes == "Uygun."
    assert check_map["require_payment_terms"].result == ComplianceResult.PASS

    # 5. cost_completeness
    assert check_map["cost_completeness"].rule_description == "Maliyet verisi eksiksizlik kontrolü"
    assert check_map["cost_completeness"].notes == "Maliyet kalemleri eksiksiz."
    assert check_map["cost_completeness"].actual_value == "Eksiksiz"
    assert check_map["cost_completeness"].result == ComplianceResult.PASS

    # 6. extraction_confidence
    assert check_map["extraction_confidence"].rule_description == "Doküman veri çıkarma güven skoru kontrolü"
    assert check_map["extraction_confidence"].notes == "Güven skoru yeterli."
    assert check_map["extraction_confidence"].result == ComplianceResult.PASS


def test_all_rules_english_output():
    """Verify English (en) outputs for all 6 deterministic rules."""
    analysis_id = uuid.uuid4()
    quote = _create_sample_quote()
    tco_res = TCOCalculator.calculate(quote, analysis_id)
    rules = PolicyRules(
        max_delivery_days=30,
        min_warranty_months=12,
        max_tco_budget=150000.00,
        budget_currency="TRY",
        require_payment_terms=["net-30"],
    )

    checks = ComplianceChecker.check_quote(
        quote=quote,
        tco_result=tco_res,
        rules=rules,
        analysis_id=analysis_id,
        locale="en",
    )

    check_map = {c.rule_name: c for c in checks}

    # 1. max_delivery_days
    assert check_map["max_delivery_days"].rule_description == "Maximum delivery time check"
    assert check_map["max_delivery_days"].notes == "Compliant."
    assert check_map["max_delivery_days"].result == ComplianceResult.PASS

    # 2. min_warranty_months
    assert check_map["min_warranty_months"].rule_description == "Minimum warranty period check"
    assert check_map["min_warranty_months"].notes == "Compliant."
    assert check_map["min_warranty_months"].result == ComplianceResult.PASS

    # 3. max_tco_budget
    assert check_map["max_tco_budget"].rule_description == "Maximum budget check"
    assert check_map["max_tco_budget"].notes == "Compliant."
    assert check_map["max_tco_budget"].result == ComplianceResult.PASS

    # 4. require_payment_terms
    assert check_map["require_payment_terms"].rule_description == "Required payment terms check"
    assert check_map["require_payment_terms"].notes == "Compliant."
    assert check_map["require_payment_terms"].result == ComplianceResult.PASS

    # 5. cost_completeness
    assert check_map["cost_completeness"].rule_description == "Cost completeness check"
    assert check_map["cost_completeness"].notes == "Cost items complete."
    assert check_map["cost_completeness"].actual_value == "Complete"
    assert check_map["cost_completeness"].result == ComplianceResult.PASS

    # 6. extraction_confidence
    assert check_map["extraction_confidence"].rule_description == "Document extraction confidence score check"
    assert check_map["extraction_confidence"].notes == "Confidence score sufficient."
    assert check_map["extraction_confidence"].result == ComplianceResult.PASS


def test_rule_checks_logical_and_mathematical_invariance():
    """
    Assert complete invariance of PASS/FAIL/WARNING and numerical values
    across both Turkish and English evaluation runs.
    """
    analysis_id = uuid.uuid4()
    
    # Failing scenario across multiple rules
    failing_quote = _create_sample_quote(
        delivery_days=45,  # Exceeds max 30
        warranty_months=6,  # Below min 12
        total_price=Decimal("200000.00"),  # Exceeds budget 150000
        payment_terms="advance-100",  # Not in allowed ['net-30']
        extraction_confidence=Decimal("0.65"),  # Below 0.70 threshold -> WARNING
        subtotal=Decimal("200000.00"),
        vat_rate=None,  # Missing vat_rate -> WARNING
    )
    tco_res = TCOCalculator.calculate(failing_quote, analysis_id)
    rules = PolicyRules(
        max_delivery_days=30,
        min_warranty_months=12,
        max_tco_budget=150000.00,
        budget_currency="TRY",
        require_payment_terms=["net-30"],
    )

    tr_checks = ComplianceChecker.check_quote(
        quote=failing_quote,
        tco_result=tco_res,
        rules=rules,
        analysis_id=analysis_id,
        locale="tr",
    )
    en_checks = ComplianceChecker.check_quote(
        quote=failing_quote,
        tco_result=tco_res,
        rules=rules,
        analysis_id=analysis_id,
        locale="en",
    )

    assert len(tr_checks) == len(en_checks)

    tr_map = {c.rule_name: c for c in tr_checks}
    en_map = {c.rule_name: c for c in en_checks}

    for rule_name in tr_map:
        tr_c = tr_map[rule_name]
        en_c = en_map[rule_name]

        # 1. Result must be 100% invariant
        assert tr_c.result == en_c.result, f"Result mismatch on {rule_name}: {tr_c.result} vs {en_c.result}"

        # 2. Required values must be identical
        assert tr_c.required_value == en_c.required_value

        # 3. Numeric values must match
        if rule_name not in ("cost_completeness",):
            assert tr_c.actual_value == en_c.actual_value

    # Verify specific English failure notes
    assert en_map["max_delivery_days"].notes == "Delivery time exceeds limit."
    assert en_map["min_warranty_months"].notes == "Warranty period insufficient."
    assert en_map["max_tco_budget"].notes == "Exceeds budget."
    assert en_map["require_payment_terms"].notes == "Unacceptable payment terms."
    assert en_map["cost_completeness"].result == ComplianceResult.WARNING
    assert "Missing: vat_rate" in en_map["cost_completeness"].actual_value
    assert "Missing cost items detected" in en_map["cost_completeness"].notes
    assert en_map["extraction_confidence"].result == ComplianceResult.WARNING
    assert "Low confidence score" in en_map["extraction_confidence"].notes


def test_cross_currency_budget_exceed_notes_bilingual():
    """Verify converted TCO budget exceed notes in both locales."""
    analysis_id = uuid.uuid4()
    quote = _create_sample_quote(currency="USD", total_price=Decimal("10000.00"))
    tco_res = TCOResult(
        quote_id=quote.id,
        total_tco=10000.00,
        currency="USD",
        converted_total_tco=340000.00,
        target_currency="TRY",
    )
    rules = PolicyRules(max_tco_budget=300000.00, budget_currency="TRY")

    # Turkish
    tr_checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id, locale="tr")
    tr_budget = next(c for c in tr_checks if c.rule_name == "max_tco_budget")
    assert tr_budget.result == ComplianceResult.FAIL
    assert "Bütçeyi aşıyor (Dönüştürülmüş TCO: 340000.0 TRY, Orijinal: 10000.0 USD)." in tr_budget.notes

    # English
    en_checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id, locale="en")
    en_budget = next(c for c in en_checks if c.rule_name == "max_tco_budget")
    assert en_budget.result == ComplianceResult.FAIL
    assert "Exceeds budget (Converted TCO: 340000.0 TRY, Original: 10000.0 USD)." in en_budget.notes


def test_missing_subtotal_base_price_bilingual():
    """Verify base price missing failure messages in both locales."""
    analysis_id = uuid.uuid4()
    quote = _create_sample_quote(subtotal=None)
    quote.total_price = None  # Force subtotal to be detected as missing
    tco_res = TCOResult(quote_id=quote.id, total_tco=0.0, currency="TRY")
    rules = PolicyRules(max_tco_budget=100000.00, budget_currency="TRY")

    # Turkish
    tr_checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id, locale="tr")
    tr_cost = next(c for c in tr_checks if c.rule_name == "cost_completeness")
    assert tr_cost.result == ComplianceResult.FAIL
    assert "Temel fiyat verisi eksik" in tr_cost.notes
    assert "Fiyat doğrulaması yapılamadı." in tr_cost.notes
    assert "Eksik: subtotal" in tr_cost.actual_value

    # English
    en_checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id, locale="en")
    en_cost = next(c for c in en_checks if c.rule_name == "cost_completeness")
    assert en_cost.result == ComplianceResult.FAIL
    assert "Base price data missing" in en_cost.notes
    assert "Price validation failed." in en_cost.notes
    assert "Missing: subtotal" in en_cost.actual_value


def test_missing_terms_and_deadlines_bilingual():
    """Verify missing delivery time, warranty, and payment terms in both locales."""
    analysis_id = uuid.uuid4()
    quote = _create_sample_quote()
    quote.delivery_days = None
    quote.warranty_months = None
    quote.payment_terms = None

    tco_res = TCOResult(quote_id=quote.id, total_tco=100000.0, currency="TRY")
    rules = PolicyRules(
        max_delivery_days=30,
        min_warranty_months=12,
        max_tco_budget=150000.00,
        budget_currency="TRY",
        require_payment_terms=["net-30"],
    )

    # Turkish
    tr_checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id, locale="tr")
    tr_map = {c.rule_name: c for c in tr_checks}
    assert tr_map["max_delivery_days"].notes == "Teslimat süresi belirtilmemiş."
    assert tr_map["min_warranty_months"].notes == "Garanti süresi belirtilmemiş."
    assert tr_map["require_payment_terms"].notes == "Ödeme koşulu belirtilmemiş."

    # English
    en_checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id, locale="en")
    en_map = {c.rule_name: c for c in en_checks}
    assert en_map["max_delivery_days"].notes == "Delivery time not specified."
    assert en_map["min_warranty_months"].notes == "Warranty period not specified."
    assert en_map["require_payment_terms"].notes == "Payment terms not specified."

