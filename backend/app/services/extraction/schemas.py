"""
app/services/extraction/schemas.py

LLM'e "bu formatta veri döndür" diye gösterdiğimiz Pydantic şemaları.

Bu şema iki iş birden yapıyor:
  1. LLM'e response_schema olarak gönderilir → constrained JSON output (OpenAPI uyumlu)
  2. Pydantic validation → field_validator'larla değerler normalize edilir

DİKKAT:
  Google GenAI SDK (OpenAPI schema dönüştürücü) ile uyumluluk için
  sayısal alanlar şemada 'float' ve 'int' olarak tanımlanır.
  Veritabanına (Quote / QuoteItem) yazılırken Decimal'a dönüştürülür.
  Böylece GenAI SDK'sının 'anyOf.0.exclusiveMinimum' hatası vermesi engellenir.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


class QuoteItemExtractionSchema(BaseModel):
    """
    Teklif içindeki tek bir kalem.

    Örnek:
      line_number=1, description="HP Laptop 14s",
      quantity=50.0, unit="adet", unit_price=4500.00, total_price=225000.00
    """
    line_number: int = Field(ge=1, description="Line number in the document (1, 2, 3...)")
    description: str = Field(description="Product or service description")
    quantity: float = Field(ge=0, description="Quantity ordered")
    unit: str | None = Field(
        default=None,
        description="Unit of measure: adet, kg, m2, paket, etc. Null if not specified."
    )
    unit_price: float = Field(ge=0, description="Price per unit before tax")
    total_price: float = Field(ge=0, description="Total line price: quantity × unit_price")


class QuoteExtractionSchema(BaseModel):
    """
    Tedarikçi teklifinden çıkarılan tüm finansal ve ticari veriler.

    LLM bu şemayı alır ve belgeyi okuyarak her alanı doldurur.
    Bilinmeyen veya belgede bulunmayan alanlar null döner.
    """

    # ── Tedarikçi ve Teklif Bilgisi ───────────────────────────────────────────
    supplier_name: str | None = Field(
        default=None,
        description="Supplier company name as it appears in the document",
    )

    quote_number: str | None = Field(
        default=None,
        description="Supplier quote / invoice / proposal reference number (e.g. DEF-2026-0941). Null if none.",
    )

    # ── Para birimi ───────────────────────────────────────────────────────────
    currency: str = Field(
        description=(
            "ISO 4217 currency code. "
            "Use 'TRY' for Turkish Lira (even if document says TL or ₺). "
            "Use 'USD' for US Dollar, 'EUR' for Euro, 'GBP' for Pound."
        ),
    )

    # ── Finansal alanlar (Eksik vs Sıfır ayrımı) ──────────────────────────────
    subtotal: float = Field(
        description="Sum of all line items before tax, shipping, and discounts",
        ge=0,
    )

    vat_rate: float | None = Field(
        default=None,
        description=(
            "VAT/KDV rate as a decimal fraction (e.g. 0.20 for 20%, 0.10 for 10%). "
            "Null if VAT is not mentioned or exempt."
        ),
        ge=0,
        le=1,
    )

    vat_amount: float | None = Field(
        default=None,
        description="Absolute VAT amount in the document's currency. Null if not mentioned.",
        ge=0,
    )

    shipping_cost: float | None = Field(
        default=None,
        description="Shipping or delivery cost. Explicitly 0.0 only if free/included. Null if not mentioned.",
        ge=0,
    )

    discount_amount: float | None = Field(
        default=None,
        description="Discount amount (positive number). Explicitly 0.0 only if 0 discount stated. Null if none.",
        ge=0,
    )

    other_costs: float | None = Field(
        default=None,
        description="Additional costs (handling, customs, installation, etc.). Null if none.",
        ge=0,
    )

    total_price: float = Field(
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
            "Payment terms in English. Examples: 'net-30', 'net-60', 'cash', "
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
        description="Any important terms, bank details, or conditions not captured in other fields.",
    )

    # ── Kalem listesi ─────────────────────────────────────────────────────────
    items: list[QuoteItemExtractionSchema] = Field(
        default_factory=list,
        description="Individual line items from the quote. Empty list if not itemized.",
    )

    # ── Extraction metadata ───────────────────────────────────────────────────
    extraction_confidence: float = Field(
        default=0.8,
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
        description="Note any fields that were missing, ambiguous, or required inference.",
    )

    validation_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings detected during arithmetic and field validation",
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
            return "TRY"
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
    def normalize_vat_rate(cls, v) -> float | None:
        """
        KDV oranı normalizasyonu.
        LLM bazen yüzde (20), bazen ondalık (0.20) verir.
        """
        if v is None:
            return None
        try:
            val = float(v)
            if val > 1.0:
                return round(val / 100.0, 4)
            return round(val, 4)
        except (ValueError, TypeError):
            return None

    @model_validator(mode="after")
    def validate_arithmetic_consistency(self) -> "QuoteExtractionSchema":
        """
        Matematiksel tutarlılık kontrolleri:
        1. Kalemlerin toplamı vs subtotal
        2. Her kalemin adet × birim fiyat = toplam fiyat doğrulaması
        3. subtotal + kdv + nakliye + ek - indirim vs total_price
        """
        warnings: list[str] = list(self.validation_warnings or [])

        # 1. Kalem bazlı matematik kontrolü
        for item in self.items:
            if item.quantity > 0 and item.unit_price > 0:
                expected_line = round(item.quantity * item.unit_price, 2)
                diff = abs(expected_line - item.total_price)
                if diff > max(1.0, item.total_price * 0.03):
                    warnings.append(
                        f"Line {item.line_number} calculation mismatch: "
                        f"{item.quantity} × {item.unit_price:.2f} = {expected_line:.2f}, "
                        f"document stated {item.total_price:.2f}"
                    )

        # 2. Kalemler toplamı vs subtotal
        if self.items:
            items_sum = round(sum(i.total_price for i in self.items), 2)
            if self.subtotal > 0:
                deviation = abs(items_sum - self.subtotal) / self.subtotal
                if deviation > 0.05:
                    self.extraction_confidence = max(0.1, self.extraction_confidence - 0.2)
                    warnings.append(
                        f"Items sum ({items_sum:.2f}) deviates by {deviation:.1%} from subtotal ({self.subtotal:.2f})"
                    )

        # 3. Genel toplam tutarlılığı
        calculated_total = (
            self.subtotal
            + (self.vat_amount or 0.0)
            + (self.shipping_cost or 0.0)
            + (self.other_costs or 0.0)
            - (self.discount_amount or 0.0)
        )
        if self.total_price > 0:
            total_dev = abs(calculated_total - self.total_price) / self.total_price
            if total_dev > 0.05:
                self.extraction_confidence = max(0.1, self.extraction_confidence - 0.2)
                warnings.append(
                    f"Total price mismatch: calculated {calculated_total:.2f} "
                    f"vs document total {self.total_price:.2f} (deviation: {total_dev:.1%})"
                )

        self.validation_warnings = warnings
        if warnings and not self.extraction_notes:
            self.extraction_notes = " | ".join(warnings)
        elif warnings:
            self.extraction_notes = f"{self.extraction_notes} | {' | '.join(warnings)}"

        return self
