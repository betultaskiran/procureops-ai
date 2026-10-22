"""
app/services/deterministic/compliance.py

Hard Rule (Kesin Kural) denetleyicisi.
Tedarikçi teklifleri, LLM'e gitmeden önce bu kurallardan geçer.
Böylece halüsinasyon riski engellenir.
"""

import uuid
import json
from decimal import Decimal
from typing import List

from app.models.quote import Quote
from app.models.analysis import ComplianceCheck, ComplianceResult
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.tco import TCOCalculator, TCOResult


class ComplianceChecker:
    """Teklifleri kurallara göre doğrulayıp ComplianceCheck sonuçları üretir."""

    @classmethod
    def check_quote(
        cls, 
        quote: Quote, 
        tco_result: TCOResult, 
        rules: PolicyRules, 
        analysis_id: uuid.UUID,
        locale: str = "tr",
    ) -> List[ComplianceCheck]:
        """
        Her bir kural için bir ComplianceCheck objesi döndürür.
        """
        checks = []

        # 1. Teslimat Süresi Kuralı
        if rules.max_delivery_days is not None:
            rule_name = "max_delivery_days"
            desc = "Maximum delivery time check" if locale == "en" else "Maksimum teslimat süresi kontrolü"
            if quote.delivery_days is None:
                note = "Delivery time not specified." if locale == "en" else "Teslimat süresi belirtilmemiş."
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL, 
                        "None", str(rules.max_delivery_days), note
                    )
                )
            elif quote.delivery_days > rules.max_delivery_days:
                note = "Delivery time exceeds limit." if locale == "en" else "Teslimat süresi sınırı aşıyor."
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        str(quote.delivery_days), str(rules.max_delivery_days), note
                    )
                )
            else:
                note = "Compliant." if locale == "en" else "Uygun."
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.PASS,
                        str(quote.delivery_days), str(rules.max_delivery_days), note
                    )
                )

        # 2. Garanti Süresi Kuralı
        if rules.min_warranty_months is not None:
            rule_name = "min_warranty_months"
            desc = "Minimum warranty period check" if locale == "en" else "Minimum garanti süresi kontrolü"
            if quote.warranty_months is None:
                note = "Warranty period not specified." if locale == "en" else "Garanti süresi belirtilmemiş."
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        "None", str(rules.min_warranty_months), note
                    )
                )
            elif quote.warranty_months < rules.min_warranty_months:
                note = "Warranty period insufficient." if locale == "en" else "Garanti süresi yetersiz."
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        str(quote.warranty_months), str(rules.min_warranty_months), note
                    )
                )
            else:
                note = "Compliant." if locale == "en" else "Uygun."
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.PASS,
                        str(quote.warranty_months), str(rules.min_warranty_months), note
                    )
                )

        # 3. Bütçe Kuralı (TCO bazlı)
        if rules.max_tco_budget is not None:
            rule_name = "max_tco_budget"
            desc = "Maximum budget check" if locale == "en" else "Maksimum bütçe kontrolü"

            quote_curr = (tco_result.currency or quote.currency or "").strip().upper()
            budget_curr = (rules.budget_currency or "TRY").strip().upper()

            if not quote_curr or not budget_curr:
                note = "Currency not specified: Cannot compare." if locale == "en" else "Para birimi belirtilmemiş: Karşılaştırma yapılamıyor."
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        str(tco_result.total_tco), str(rules.max_tco_budget),
                        note,
                    )
                )
            elif quote_curr == budget_curr:
                try:
                    total_decimal = Decimal(str(tco_result.total_tco))
                    budget_decimal = Decimal(str(rules.max_tco_budget))
                except Exception:
                    total_decimal = Decimal(float(tco_result.total_tco))
                    budget_decimal = Decimal(float(rules.max_tco_budget))

                if total_decimal > budget_decimal:
                    note = "Exceeds budget." if locale == "en" else "Bütçeyi aşıyor."
                    checks.append(
                        cls._create_check(
                            analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                            str(tco_result.total_tco), str(rules.max_tco_budget), note
                        )
                    )
                else:
                    note = "Compliant." if locale == "en" else "Uygun."
                    checks.append(
                        cls._create_check(
                            analysis_id, quote.id, rule_name, desc, ComplianceResult.PASS,
                            str(tco_result.total_tco), str(rules.max_tco_budget), note
                        )
                    )
            else:
                # quote_curr != budget_curr
                if tco_result.converted_total_tco is not None:
                    try:
                        conv_decimal = Decimal(str(tco_result.converted_total_tco))
                        budget_decimal = Decimal(str(rules.max_tco_budget))
                    except Exception:
                        conv_decimal = Decimal(float(tco_result.converted_total_tco))
                        budget_decimal = Decimal(float(rules.max_tco_budget))

                    if conv_decimal > budget_decimal:
                        note = (
                            f"Exceeds budget (Converted TCO: {tco_result.converted_total_tco} {budget_curr}, Original: {tco_result.total_tco} {quote_curr})."
                            if locale == "en"
                            else f"Bütçeyi aşıyor (Dönüştürülmüş TCO: {tco_result.converted_total_tco} {budget_curr}, Orijinal: {tco_result.total_tco} {quote_curr})."
                        )
                        checks.append(
                            cls._create_check(
                                analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                                str(tco_result.converted_total_tco), str(rules.max_tco_budget),
                                note,
                            )
                        )
                    else:
                        note = "Compliant." if locale == "en" else "Uygun."
                        checks.append(
                            cls._create_check(
                                analysis_id, quote.id, rule_name, desc, ComplianceResult.PASS,
                                str(tco_result.converted_total_tco), str(rules.max_tco_budget), note,
                            )
                        )
                else:
                    note = (
                        f"Currency mismatch: Quote currency ({quote_curr}) does not match budget currency ({budget_curr}). Direct comparison not permitted."
                        if locale == "en"
                        else f"Para birimi uyuşmazlığı: Teklif para birimi ({quote_curr}) ile bütçe para birimi ({budget_curr}) eşleşmiyor. Doğrudan karşılaştırılamaz."
                    )
                    checks.append(
                        cls._create_check(
                            analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                            str(tco_result.total_tco), str(rules.max_tco_budget),
                            note,
                        )
                    )

        # 4. Ödeme Koşulları (Payment Terms) Kuralı
        if rules.require_payment_terms is not None and len(rules.require_payment_terms) > 0:
            rule_name = "require_payment_terms"
            desc = "Required payment terms check" if locale == "en" else "Zorunlu ödeme koşulu kontrolü"
            allowed_terms = rules.require_payment_terms
            
            if quote.payment_terms is None:
                note = "Payment terms not specified." if locale == "en" else "Ödeme koşulu belirtilmemiş."
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        "None", json.dumps(allowed_terms), note
                    )
                )
            else:
                # Basit string eşleştirme (Gerçekte daha esnek yapılabilir)
                if quote.payment_terms.strip().lower() in [term.lower() for term in allowed_terms]:
                    note = "Compliant." if locale == "en" else "Uygun."
                    checks.append(
                        cls._create_check(
                            analysis_id, quote.id, rule_name, desc, ComplianceResult.PASS,
                            quote.payment_terms, json.dumps(allowed_terms), note
                        )
                    )
                else:
                    note = "Unacceptable payment terms." if locale == "en" else "Kabul edilemez ödeme koşulu."
                    checks.append(
                        cls._create_check(
                            analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                            quote.payment_terms, json.dumps(allowed_terms), note
                        )
                    )

        # 5. Maliyet Verisi Eksiksizlik Kontrolü (Cost Completeness)
        missing_fields = TCOCalculator.get_missing_financial_fields(quote)
        desc_cost = "Cost completeness check" if locale == "en" else "Maliyet verisi eksiksizlik kontrolü"
        if missing_fields:
            missing_str = (
                f"Missing: {', '.join(missing_fields)}"
                if locale == "en"
                else f"Eksik: {', '.join(missing_fields)}"
            )
            if "subtotal" in missing_fields:
                note = (
                    f"Base price data missing ({', '.join(missing_fields)}). Price validation failed."
                    if locale == "en"
                    else f"Temel fiyat verisi eksik ({', '.join(missing_fields)}). Fiyat doğrulaması yapılamadı."
                )
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, "cost_completeness",
                        desc_cost,
                        ComplianceResult.FAIL,
                        missing_str,
                        "subtotal, vat, shipping",
                        note
                    )
                )
            else:
                note = (
                    f"Missing cost items detected: {', '.join(missing_fields)}. Human review recommended."
                    if locale == "en"
                    else f"Eksik maliyet kalemleri mevcut: {', '.join(missing_fields)}. İnsan incelemesi önerilir."
                )
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, "cost_completeness",
                        desc_cost,
                        ComplianceResult.WARNING,
                        missing_str,
                        "subtotal, vat, shipping",
                        note
                    )
                )
        else:
            actual_str = "Complete" if locale == "en" else "Eksiksiz"
            note = "Cost items complete." if locale == "en" else "Maliyet kalemleri eksiksiz."
            checks.append(
                cls._create_check(
                    analysis_id, quote.id, "cost_completeness",
                    desc_cost,
                    ComplianceResult.PASS,
                    actual_str,
                    "subtotal, vat, shipping",
                    note
                )
            )

        # 6. Doküman Veri Çıkarma Güven Skoru Kontrolü (Extraction Confidence)
        if quote.extraction_confidence is not None:
            desc_conf = "Document extraction confidence score check" if locale == "en" else "Doküman veri çıkarma güven skoru kontrolü"
            if quote.extraction_confidence < Decimal("0.70"):
                note = (
                    f"Low confidence score ({quote.extraction_confidence:.2f}). Manual inspection of quote document required."
                    if locale == "en"
                    else f"Düşük güven skoru ({quote.extraction_confidence:.2f}). Teklif belgesinin manuel kontrolü gereklidir."
                )
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, "extraction_confidence",
                        desc_conf,
                        ComplianceResult.WARNING,
                        str(quote.extraction_confidence),
                        ">= 0.70",
                        note
                    )
                )
            else:
                note = "Confidence score sufficient." if locale == "en" else "Güven skoru yeterli."
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, "extraction_confidence",
                        desc_conf,
                        ComplianceResult.PASS,
                        str(quote.extraction_confidence),
                        ">= 0.70",
                        note
                    )
                )

        return checks

    @staticmethod
    def _create_check(
        analysis_id: uuid.UUID, 
        quote_id: uuid.UUID, 
        rule_name: str,
        rule_description: str,
        result: ComplianceResult, 
        actual_value: str,
        required_value: str,
        notes: str
    ) -> ComplianceCheck:
        return ComplianceCheck(
            analysis_id=analysis_id,
            quote_id=quote_id,
            rule_name=rule_name,
            rule_description=rule_description,
            result=result,
            actual_value=actual_value,
            required_value=required_value,
            notes=notes,
        )
