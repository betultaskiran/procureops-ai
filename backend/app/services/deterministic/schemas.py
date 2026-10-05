"""
app/services/deterministic/schemas.py

Deterministik kural motoru için gerekli Pydantic şemaları.
Buradaki PolicyRules şeması, gelecekte veritabanındaki JSON sütunundan
veya arayüzdeki bir konfigürasyon ekranından doldurulacaktır.
"""

from pydantic import BaseModel, Field


class PolicyRules(BaseModel):
    """
    Şirketin satın alma politikalarındaki "Hard Rules" (Kesin Kurallar).
    Bunlara uymayan teklifler LLM'e (agentic reasoning'e) gitmeden reddedilir.
    """
    max_delivery_days: int | None = Field(
        default=None, 
        description="Maksimum kabul edilebilir teslimat süresi (gün)"
    )
    min_warranty_months: int | None = Field(
        default=None, 
        description="Minimum kabul edilebilir garanti süresi (ay)"
    )
    require_payment_terms: list[str] | None = Field(
        default=None, 
        description="Kabul edilen ödeme koşulları listesi (örn: ['net-30', 'net-60'])"
    )
    max_tco_budget: float | None = Field(
        default=None, 
        description="Bu RFQ için maksimum bütçe"
    )
