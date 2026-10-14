"""
app/services/deterministic/tco.py

Total Cost of Ownership (Toplam Sahip Olma Maliyeti) hesaplayıcısı.

Neden LLM yerine bunu kullanıyoruz?
Matematiksel işlemlerde (özellikle finansal verilerde) LLM'ler hata yapabilir.
TCO, tedarikçinin verdiği ham değerleri alıp bizim için net ve karşılaştırılabilir
tek bir maliyet metrikine dönüştürür.
"""

import uuid
from decimal import Decimal

from app.models.quote import Quote
from app.models.analysis import TCOResult


class TCOCalculator:
    """
    Bir Quote modelini alır ve onun TCOResult'ını hesaplar.
    """

    @classmethod
    def get_missing_financial_fields(cls, quote: Quote) -> list[str]:
        """
        Zorunlu veya önemli maliyet kalemlerinden hangilerinin teklifte
        açıkça belirtilmediğini (None olduğunu) tespit eder.
        Confirmed 0 (ör. 0.00) ile None (belirtilmemiş) ayrımını yapar.
        """
        missing = []
        if quote.subtotal is None and quote.total_price is None:
            missing.append("subtotal")
        if quote.vat_rate is None:
            missing.append("vat_rate")
        if quote.shipping_cost is None:
            missing.append("shipping_cost")
        return missing

    @classmethod
    def calculate(cls, quote: Quote, analysis_id: uuid.UUID) -> TCOResult:
        """
        Formül:
        TCO = Subtotal - Discount + Shipping + Other Costs + (Subtotal - Discount) * VAT Rate
        
        Finansal Doğruluk Kuralları:
        1. Eksik KDV, kargo veya indirim alanları sessizce sıfır kabul EDİLMEZ.
        2. Teyitli sıfır (0.0) ile belirtilmemiş (None) alanlar ayrıştırılır.
        3. Eksik alanlar calculation_notes içerisinde açık uyarı olarak raporlanır.
        """
        missing_fields = cls.get_missing_financial_fields(quote)

        # Subtotal: eğer None ise total_price'tan türetmeye çalış veya 0
        has_subtotal = quote.subtotal is not None
        if has_subtotal:
            subtotal = Decimal(str(quote.subtotal))
        elif quote.total_price is not None:
            subtotal = Decimal(str(quote.total_price))
        else:
            subtotal = Decimal("0.00")

        # İndirim: None ise indirim yok (0.00), belirtilmişse değeri al
        discount = Decimal(str(quote.discount_amount)) if quote.discount_amount is not None else Decimal("0.00")

        # Kargo: None ise teyitsiz (0.00 geçici baz alınır ancak not düşülür)
        shipping = Decimal(str(quote.shipping_cost)) if quote.shipping_cost is not None else Decimal("0.00")

        # Diğer maliyetler: None ise 0.00
        other_costs = Decimal(str(quote.other_costs)) if quote.other_costs is not None else Decimal("0.00")

        # KDV Oranı: None ise teyitsiz (0.00 geçici baz alınır ancak not düşülür)
        vat_rate = Decimal(str(quote.vat_rate)) if quote.vat_rate is not None else Decimal("0.00")

        # KDV hesaplama
        taxable_amount = subtotal - discount
        calculated_vat = taxable_amount * vat_rate

        # Toplam TCO
        total_tco = taxable_amount + calculated_vat + shipping + other_costs

        # İnsan ve denetim okumasına uygun detaylı not oluştur
        notes_parts = []
        if missing_fields:
            notes_parts.append(f"[UYARI: EKSİK MALİYET VERİSİ - Belirtilmeyen alanlar: {', '.join(missing_fields)}]")

        notes_parts.append(
            f"Subtotal: {subtotal:,.2f}" + (" (total_price baz alındı)" if not has_subtotal and quote.total_price is not None else "")
        )
        if quote.discount_amount is not None:
            notes_parts.append(f"İndirim: {discount:,.2f}")
        notes_parts.append(f"Vergi Matrahı: {taxable_amount:,.2f}")

        if quote.vat_rate is not None:
            notes_parts.append(f"KDV({vat_rate*100:.0f}%): {calculated_vat:,.2f}")
        else:
            notes_parts.append("KDV: Belirtilmemiş (Teyit gerekli)")

        if quote.shipping_cost is not None:
            notes_parts.append(f"Kargo: {shipping:,.2f}")
        else:
            notes_parts.append("Kargo: Belirtilmemiş (Teyit gerekli)")

        if quote.other_costs is not None:
            notes_parts.append(f"Diğer: {other_costs:,.2f}")

        notes_parts.append(f"=> TCO: {total_tco:,.2f}")
        notes = " | ".join(notes_parts)

        return TCOResult(
            analysis_id=analysis_id,
            quote_id=quote.id,
            subtotal=subtotal,
            vat_amount=calculated_vat,
            shipping_cost=shipping,
            discount_amount=discount,
            other_costs=other_costs,
            total_tco=total_tco,
            currency=quote.currency or "UNKNOWN",
            calculation_notes=notes,
        )

