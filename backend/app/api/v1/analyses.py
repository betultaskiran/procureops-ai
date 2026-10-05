"""
app/api/v1/analyses.py

Analiz endpoint'leri. Şimdilik sadece deterministik (TCO + Compliance) çalışır.
İlerleyen fazlarda LLM Reasoning bu endpoint üzerinden tetiklenecek.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.orchestrator import DeterministicEngine
from app.models.analysis import ComplianceResult

router = APIRouter(prefix="/api/v1", tags=["analyses"])


# ── Response Schemas ───────────────────────────────────────────────────────────

class TCOResultResponse(BaseModel):
    quote_id: uuid.UUID
    total_tco: float
    currency: str
    calculation_notes: str | None

    model_config = {"from_attributes": True}


class ComplianceCheckResponse(BaseModel):
    quote_id: uuid.UUID
    rule_name: str
    rule_description: str
    result: ComplianceResult
    actual_value: str
    required_value: str
    notes: str

    model_config = {"from_attributes": True}


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    rfq_id: uuid.UUID
    status: str
    tco_results: List[TCOResultResponse] = []
    compliance_checks: List[ComplianceCheckResponse] = []

    model_config = {"from_attributes": True}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/rfqs/{rfq_id}/analyze",
    response_model=AnalysisResponse,
    summary="Run Deterministic Analysis (TCO + Rules)",
    description=(
        "Belirtilen RFQ'ya ait tüm Quote'ları alır. "
        "TCO (Maliyet) hesaplaması yapar ve PolicyRules (Kurallar) üzerinden "
        "geçirerek uygunluk (Compliance) denetimi yapar."
    ),
)
async def run_analysis(
    rfq_id: uuid.UUID,
    rules: PolicyRules,  # Request body olarak kural parametrelerini alıyoruz
    db: AsyncSession = Depends(get_db),
) -> AnalysisResponse:
    """
    RFQ için Analiz başlatır.
    """
    engine = DeterministicEngine(db=db)
    
    try:
        analysis = await engine.run_analysis(rfq_id=rfq_id, rules=rules)
        return AnalysisResponse.model_validate(analysis)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
