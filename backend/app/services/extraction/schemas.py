"""
app/services/extraction/schemas.py

LLM'e "bu formatta veri döndür" diye gösterdiğimiz Pydantic şemaları.

Bu şema iki iş birden yapıyor:
  1. LLM'e response_schema olarak gönderilir → constrained JSON output
  2. Pydantic validation → field_validator'larla değerler normalize edilir

FIELD_VALIDATOR NEDEN LAZIM?
  LLM çıktısı her zaman mükemmel değildir:
    "KDV: %20" → vat_rate=20  (0.20 olmalıydı)
    "Para Birimi: TL" → currency="TL"  ("TRY" olmalı)
    "Teslimat: 7 iş günü" → delivery_days=7  (doğru)

  Validator bu düzeltmeleri otomatik yapar.
  LLM'e "0.20 yaz, 20 yazma" demek yerine, validator her ikisini de kabul eder.

NOT: Bu şemayı SQLAlchemy modeliyle (Quote) karıştırma.
  - Bu şema → LLM'den veri AL
  - Quote model → Veritabanına yaz
  Aralarında bir dönüşüm adımı var (extractor.py'de).
"""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


class QuoteItemExtractionSchema(BaseModel):
    """
    Teklif içindeki tek bir kalem.

    Örnek:
      line_number=1, description="HP Laptop 14s",
      quantity=50, unit="adet", unit_price=4500.00, total_price=225000.00
    """
    line_number: int = Field(ge=1, description="Line number in the document")
    description: str = Field(description="Product or service description")
    quantity: Decimal = Field(ge=0, description="Quantity ordered")
    unit: str | None = Field(
        default=None,
        description="Unit of measure: adet, kg, m2, etc."
    )
    unit_price: Decimal = Field(ge=0, description="Price per unit")
    total_price: Decimal = Field(ge=0, description="quantity × unit_price")


class QuoteExtractionSchema(BaseModel):
    """
    Tedarikçi teklifinden çıkarılan tüm finansal ve ticari veriler.

    LLM bu şemayı alır ve belgeyi okuyarak her alanı doldurur.
    Bilinmeyen veya bulunamayan alanlar None olarak döner.

    ÖNEMLI FIELD AÇIKLAMALARI (LLM bunları okur):
      description= parametreleri LLM'e talimat verir.
      "0.20 for 20% VAT" gibi açıklamalar hataları önler.
    """

    # ── Tedarikçi bilgisi ─────────────────────────────────────────────────────
    supplier_name: str | None = Field(
        default=None,
        description="Supplier company name as it appears in the document",
    )

    # ── Para birimi ───────────────────────────────────────────────────────────
    currency: str = Field(
        description=(
            "ISO 4217 currency code. "
            "Use 'TRY' for Turkish Lira (even if document says TL or ₺). "
            "Use 'USD' for US Dollar, 'EUR' for Euro."
        ),
    )

    # ── Finansal alanlar ──────────────────────────────────────────────────────
    subtotal: Decimal = Field(
        description="Sum of all line items before tax, shipping, and discounts",
        ge=0,
    )

    vat_rate: Decimal = Field(
        description=(
            "VAT/KDV rate as a decimal fraction. "
            "Express 20%% as 0.20, not 20. "
            "If no VAT, use 0.0."
        ),
        ge=0,
        le=1,
    )

    vat_amount: Decimal = Field(
        description="Absolute VAT amount in the document's currency",
        ge=0,
    )

    shipping_cost: Decimal = Field(
        default=Decimal("0"),
        description="Shipping, freight, or delivery cost. 0 if not mentioned.",
        ge=0,
    )

    discount_amount: Decimal = Field(
        default=Decimal("0"),
        description="Discount amount (positive number). 0 if no discount.",
        ge=0,
    )

    other_costs: Decimal = Field(
        default=Decimal("0"),
        description=(
            "Any additional costs: installation, handling, customs, etc. "
            "0 if none."
        ),
        ge=0,
    )

    total_price: Decimal = Field(
        description="Grand total: subtotal + vat + shipping + other - discount",
        ge=0,
    )

    # ── Ticari koşullar ───────────────────────────────────────────────────────
    delivery_days: int | None = Field(
        default=None,
        description=(
            "Delivery time in calendar days. "
            "Convert 'business days' to calendar days by multiplying by 1.4. "
            "Null if not specified."
        ),
        ge=1,
    )

    payment_terms: str | None = Field(
        default=None,
        description=(
            "Payment terms in English. Examples: 'net-30', 'net-60', "
            "'advance-payment', 'on-delivery'. Null if not specified."
        ),
    )

    warranty_months: int | None = Field(
        default=None,
        description=(
            "Warranty period in months. Convert years to months (2 years = 24). "
            "Null if not specified."
        ),
        ge=0,
    )

    valid_until: str | None = Field(
        default=None,
        description=(
            "Quote validity date in ISO 8601 format: YYYY-MM-DD. "
            "Null if not specified."
        ),
    )

    notes: str | None = Field(
        default=None,
        description="Any important terms or conditions not captured in other fields.",
    )

    # ── Kalem listesi ─────────────────────────────────────────────────────────
    items: list[QuoteItemExtractionSchema] = Field(
        default_factory=list,
        description="Individual line items from the quote. Empty list if not itemized.",
    )

    # ── Extraction metadata ───────────────────────────────────────────────────
    extraction_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Your confidence in the extraction accuracy (0.0 to 1.0). "
            "1.0 = all fields clearly stated. "
            "0.5 = some fields inferred or ambiguous. "
            "0.2 = many fields missing or unclear."
        ),
    )

    extraction_notes: str | None = Field(
        default=None,
        description=(
            "Note any fields that were missing, ambiguous, or required inference. "
            "Examples: 'VAT rate inferred from percentage shown', "
            "'delivery days converted from business days'."
        ),
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        """
        Para birimi normalizasyonu.
        LLM "TL", "Türk Lirası", "lira" gibi değerler döndürebilir.
        Bunları ISO 4217 koduna çeviriyoruz.
        """
        if not isinstance(v, str):
            return v
        mapping = {
            "TL": "TRY",
            "₺": "TRY",
            "TURK LIRASI": "TRY",
            "TÜRK LİRASI": "TRY",
            "TÜRK LIRASI": "TRY",
            "TURKISH LIRA": "TRY",
            "$": "USD",
            "DOLLAR": "USD",
            "DOLLARS": "USD",
            "€": "EUR",
            "EURO": "EUR",
            "EUROS": "EUR",
            "£": "GBP",
            "POUND": "GBP",
        }
        normalized = v.strip().upper()
        return mapping.get(normalized, normalized)

    @field_validator("vat_rate", mode="before")
    @classmethod
    def normalize_vat_rate(cls, v) -> Decimal:
        """
        KDV oranı normalizasyonu.

        LLM bazen yüzde olarak verir (20), bazen ondalık olarak (0.20).
        1'den büyükse yüzde olarak gelmiştir, 100'e bölüyoruz.

        Örnekler:
          20   → 0.20  (%20 KDV)
          0.20 → 0.20  (zaten doğru)
          18   → 0.18  (%18 KDV)
        """
        val = Decimal(str(v))
        if val > 1:
            return val / 100
        return val

    @model_validator(mode="after")
    def validate_total_price_consistency(self) -> "QuoteExtractionSchema":
        """
        total_price'ın hesaplanan değerle yakın olup olmadığını kontrol eder.

        Not: Bu bir HARD ERROR değil, sadece confidence'ı düşürür.
        Neden? LLM belgedeki "toplam" değerini almış olabilir,
        bizim hesabımız ise biraz farklı olabilir (yuvarlama vb.)

        HARD validation Phase 4'te deterministik katmanda yapılacak.
        Burada sadece "bir şeyler garip" işareti koyuyoruz.
        """
        calculated = (
            self.subtotal
            + self.vat_amount
            + self.shipping_cost
            + self.other_costs
            - self.discount_amount
        )
        # %5'ten fazla sapma → confidence'ı düşür ve not ekle
        if self.total_price > 0:
            deviation = abs(calculated - self.total_price) / self.total_price
            if deviation > Decimal("0.05"):
                self.extraction_confidence = max(0.0, self.extraction_confidence - 0.2)
                note = (
                    f"Total price mismatch: document says {self.total_price}, "
                    f"calculated {calculated:.2f} "
                    f"(deviation: {deviation:.1%})"
                )
                self.extraction_notes = (
                    f"{self.extraction_notes or ''} | {note}".strip(" |")
                )
        return self
