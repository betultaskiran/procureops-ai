"""
app/services/deterministic/compliance.py

Hard Rule (Kesin Kural) denetleyicisi.
Tedarikçi teklifleri, LLM'e gitmeden önce bu kurallardan geçer.
Böylece halüsinasyon riski engellenir.
"""

import uuid
import json
from typing import List

from app.models.quote import Quote
from app.models.analysis import ComplianceCheck, ComplianceResult
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.tco import TCOResult


class ComplianceChecker:
    """Teklifleri kurallara göre doğrulayıp ComplianceCheck sonuçları üretir."""

    @classmethod
    def check_quote(
        cls, 
        quote: Quote, 
        tco_result: TCOResult, 
        rules: PolicyRules, 
        analysis_id: uuid.UUID
    ) -> List[ComplianceCheck]:
        """
        Her bir kural için bir ComplianceCheck objesi döndürür.
        """
        checks = []

        # 1. Teslimat Süresi Kuralı
        if rules.max_delivery_days is not None:
            rule_name = "max_delivery_days"
            desc = "Maksimum teslimat süresi kontrolü"
            if quote.delivery_days is None:
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL, 
                        "None", str(rules.max_delivery_days), "Teslimat süresi belirtilmemiş."
                    )
                )
            elif quote.delivery_days > rules.max_delivery_days:
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        str(quote.delivery_days), str(rules.max_delivery_days), "Teslimat süresi sınırı aşıyor."
                    )
                )
            else:
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.PASS,
                        str(quote.delivery_days), str(rules.max_delivery_days), "Uygun."
                    )
                )

        # 2. Garanti Süresi Kuralı
        if rules.min_warranty_months is not None:
            rule_name = "min_warranty_months"
            desc = "Minimum garanti süresi kontrolü"
            if quote.warranty_months is None:
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        "None", str(rules.min_warranty_months), "Garanti süresi belirtilmemiş."
                    )
                )
            elif quote.warranty_months < rules.min_warranty_months:
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        str(quote.warranty_months), str(rules.min_warranty_months), "Garanti süresi yetersiz."
                    )
                )
            else:
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.PASS,
                        str(quote.warranty_months), str(rules.min_warranty_months), "Uygun."
                    )
                )

        # 3. Bütçe Kuralı (TCO bazlı)
        if rules.max_tco_budget is not None:
            rule_name = "max_tco_budget"
            desc = "Maksimum bütçe kontrolü"
            if float(tco_result.total_tco) > rules.max_tco_budget:
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        str(tco_result.total_tco), str(rules.max_tco_budget), "Bütçeyi aşıyor."
                    )
                )
            else:
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.PASS,
                        str(tco_result.total_tco), str(rules.max_tco_budget), "Uygun."
                    )
                )

        # 4. Ödeme Koşulları (Payment Terms) Kuralı
        if rules.require_payment_terms is not None and len(rules.require_payment_terms) > 0:
            rule_name = "require_payment_terms"
            desc = "Zorunlu ödeme koşulu kontrolü"
            allowed_terms = rules.require_payment_terms
            
            if quote.payment_terms is None:
                checks.append(
                    cls._create_check(
                        analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                        "None", json.dumps(allowed_terms), "Ödeme koşulu belirtilmemiş."
                    )
                )
            else:
                # Basit string eşleştirme (Gerçekte daha esnek yapılabilir)
                if quote.payment_terms.strip().lower() in [term.lower() for term in allowed_terms]:
                    checks.append(
                        cls._create_check(
                            analysis_id, quote.id, rule_name, desc, ComplianceResult.PASS,
                            quote.payment_terms, json.dumps(allowed_terms), "Uygun."
                        )
                    )
                else:
                    checks.append(
                        cls._create_check(
                            analysis_id, quote.id, rule_name, desc, ComplianceResult.FAIL,
                            quote.payment_terms, json.dumps(allowed_terms), "Kabul edilemez ödeme koşulu."
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
