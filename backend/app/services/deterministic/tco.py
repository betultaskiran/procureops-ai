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
    def calculate(cls, quote: Quote, analysis_id: uuid.UUID) -> TCOResult:
        """
        Formül:
        TCO = Subtotal - Discount + Shipping + Other Costs + (Subtotal - Discount) * VAT Rate
        
        Ancak Quote modeli içindeki veriler zaten çıkartılmış durumda. 
        Biz burada kendi sağlamamızı yapıp nihai TCO'yu oluşturacağız.
        """
        
        # None olan değerleri güvenli şekilde Decimal(0) yapalım
        subtotal = Decimal(str(quote.subtotal or 0))
        discount = Decimal(str(quote.discount_amount or 0))
        shipping = Decimal(str(quote.shipping_cost or 0))
        other_costs = Decimal(str(quote.other_costs or 0))
        vat_rate = Decimal(str(quote.vat_rate or 0))
        
        # KDV hesaplama
        taxable_amount = subtotal - discount
        calculated_vat = taxable_amount * vat_rate
        
        # Toplam TCO
        total_tco = taxable_amount + calculated_vat + shipping + other_costs
        
        # Not oluştur (İnsan okumasına uygun formatlama)
        notes = (
            f"Subtotal: {subtotal:,.2f}, Discount: {discount:,.2f}, "
            f"Taxable: {taxable_amount:,.2f}, VAT({vat_rate*100:.0f}%): {calculated_vat:,.2f}, "
            f"Shipping: {shipping:,.2f}, Other: {other_costs:,.2f} => TCO: {total_tco:,.2f}"
        )
        
        return TCOResult(
            analysis_id=analysis_id,
            quote_id=quote.id,
            subtotal=subtotal,
            vat_amount=calculated_vat,
            shipping_cost=shipping,
            discount_amount=discount,
            other_costs=other_costs,
            total_tco=total_tco,
            currency=quote.currency,
            calculation_notes=notes,
        )
