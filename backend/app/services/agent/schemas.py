"""
app/services/agent/schemas.py

Agentic AI'nin (Gemini) kararlarını yapılandırılmış (structured) olarak
döndürmesi için Pydantic şemaları.
"""

import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


class AgentRecommendationSchema(BaseModel):
    """
    LLM'in bir RFQ analizi sonucunda döneceği kesin karar formatı.
    """
    recommended_quote_id: Optional[uuid.UUID] = Field(
        None,
        description="Önerilen teklifin benzersiz UUID'si. Eğer hiçbir teklif uygun değilse null bırak."
    )
    justification: str = Field(
        ...,
        description="Neden bu teklifin seçildiğinin (veya hiçbirinin seçilmediğinin) detaylı ve profesyonel gerekçesi."
    )
    trade_off_analysis: str = Field(
        ...,
        description="Diğer alternatiflere karşı yapılan trade-off (ödünleşim) analizi (Örn: A daha ucuz ama B'nin geçmişi daha iyi)."
    )
    risk_factors: List[str] = Field(
        default_factory=list,
        description="Seçilen tedarikçi ile ilgili tespit edilen olası riskler (RAG veya Geçmiş verilerinden)."
    )
    confidence_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Bu öneriye duyulan güven skoru (0-100 arası)."
    )
    is_human_review_required: bool = Field(
        ...,
        description="Bu karar kritik mi? Risk faktörleri veya kural esnemeleri varsa true yap, yöneticinin onayından geçsin."
    )
