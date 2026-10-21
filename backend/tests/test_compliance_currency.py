"""
tests/test_compliance_currency.py

Unit tests for RFQ budget compliance checks and cross-currency protection.
Validates:
1. Matching currency under budget -> PASS
2. Matching currency over budget -> FAIL
3. Mismatched currency (quote USD vs budget TRY) -> FAIL regardless of nominal value
4. Missing or empty currency handling -> FAIL
5. Case-insensitive and whitespace-tolerant matching ('try' vs '  TRY  ')
"""

import uuid
import pytest
from decimal import Decimal

from app.models.analysis import ComplianceResult
from app.models.quote import Quote
from app.services.deterministic.compliance import ComplianceChecker
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.tco import TCOResult


def _make_dummy_quote(currency: str | None = "TRY", total_price: Decimal = Decimal("100000.00")) -> Quote:
    return Quote(
        id=uuid.uuid4(),
        rfq_id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        subtotal=total_price,
        total_price=total_price,
        currency=currency,
        delivery_days=10,
        warranty_months=24,
        payment_terms="net-30",
    )


def test_matching_currency_under_budget_passes():
    """1. Quote with matching currency and TCO under budget must PASS."""
    analysis_id = uuid.uuid4()
    quote = _make_dummy_quote(currency="TRY", total_price=Decimal("400000.00"))
    tco_res = TCOResult(quote_id=quote.id, total_tco=400000.00, currency="TRY")
    rules = PolicyRules(max_tco_budget=500000.00, budget_currency="TRY")

    checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id)
    budget_check = next(c for c in checks if c.rule_name == "max_tco_budget")

    assert budget_check.result == ComplianceResult.PASS
    assert budget_check.notes == "Uygun."
    assert float(budget_check.actual_value) == 400000.00
    assert float(budget_check.required_value) == 500000.00


def test_matching_currency_over_budget_fails():
    """2. Quote with matching currency and TCO exceeding budget must FAIL."""
    analysis_id = uuid.uuid4()
    quote = _make_dummy_quote(currency="TRY", total_price=Decimal("600000.00"))
    tco_res = TCOResult(quote_id=quote.id, total_tco=600000.00, currency="TRY")
    rules = PolicyRules(max_tco_budget=500000.00, budget_currency="TRY")

    checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id)
    budget_check = next(c for c in checks if c.rule_name == "max_tco_budget")

    assert budget_check.result == ComplianceResult.FAIL
    assert "Bütçeyi aşıyor" in budget_check.notes
    assert float(budget_check.actual_value) == 600000.00


def test_mismatched_currency_fails_regardless_of_nominal_value():
    """
    3. Quote with mismatched currency (e.g. 100 USD vs 500,000 TRY budget)
    must strictly FAIL closed with explicit currency mismatch note, even though
    nominal 100 is far lower than 500,000.
    """
    analysis_id = uuid.uuid4()
    quote = _make_dummy_quote(currency="USD", total_price=Decimal("100.00"))
    tco_res = TCOResult(quote_id=quote.id, total_tco=100.00, currency="USD")
    rules = PolicyRules(max_tco_budget=500000.00, budget_currency="TRY")

    checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id)
    budget_check = next(c for c in checks if c.rule_name == "max_tco_budget")

    assert budget_check.result == ComplianceResult.FAIL
    assert "Para birimi uyuşmazlığı" in budget_check.notes
    assert "USD" in budget_check.notes
    assert "TRY" in budget_check.notes


def test_missing_or_empty_currency_fails():
    """4. Quote with missing, None, or blank currency must FAIL closed."""
    analysis_id = uuid.uuid4()

    for blank_curr in [None, "", "   "]:
        quote = _make_dummy_quote(currency=blank_curr, total_price=Decimal("50000.00"))
        tco_res = TCOResult(quote_id=quote.id, total_tco=50000.00, currency=blank_curr)
        rules = PolicyRules(max_tco_budget=100000.00, budget_currency="TRY")

        checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id)
        budget_check = next(c for c in checks if c.rule_name == "max_tco_budget")

        assert budget_check.result == ComplianceResult.FAIL
        assert "Para birimi belirtilmemiş" in budget_check.notes


def test_case_insensitive_and_whitespace_currency_matching():
    """5. Currency comparison must be case-insensitive and ignore leading/trailing whitespace."""
    analysis_id = uuid.uuid4()

    quote = _make_dummy_quote(currency="  try  ", total_price=Decimal("45000.00"))
    tco_res = TCOResult(quote_id=quote.id, total_tco=45000.00, currency=" try ")
    rules = PolicyRules(max_tco_budget=50000.00, budget_currency="TRY")

    checks = ComplianceChecker.check_quote(quote, tco_res, rules, analysis_id)
    budget_check = next(c for c in checks if c.rule_name == "max_tco_budget")

    assert budget_check.result == ComplianceResult.PASS
    assert budget_check.notes == "Uygun."
