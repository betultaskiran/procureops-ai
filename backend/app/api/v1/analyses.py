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


# ── Request / Response Schemas ────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    organization_id: uuid.UUID
    rules: PolicyRules


class RecommendationResponse(BaseModel):
    recommended_quote_id: uuid.UUID | None
    reasoning: str
    risks: str | None
    alternative_notes: str | None
    verification_status: str

    model_config = {"from_attributes": True}


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    rfq_id: uuid.UUID
    status: str
    tco_results: List[TCOResultResponse] = []
    compliance_checks: List[ComplianceCheckResponse] = []
    recommendation: RecommendationResponse | None = None

    model_config = {"from_attributes": True}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/rfqs/{rfq_id}/analyze",
    response_model=AnalysisResponse,
    summary="Run Full Analysis (Deterministic + Agentic)",
    description=(
        "1. Deterministic Engine: TCO ve Hard Rule kontrollerini yapar.\n"
        "2. RAG Engine: Kurumsal hafızadan verileri çeker.\n"
        "3. Agentic Engine: LLM ile trade-off analizi yapıp öneri (Recommendation) sunar."
    ),
)
async def run_analysis(
    rfq_id: uuid.UUID,
    request: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> AnalysisResponse:
    """
    RFQ için Analiz başlatır.
    """
    # 1. Deterministik Analiz (TCO ve Kurallar)
    det_engine = DeterministicEngine(db=db)
    
    try:
        analysis = await det_engine.run_analysis(rfq_id=rfq_id, rules=request.rules)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # 2. Agentic Analiz (LLM Reasoning)
    from app.services.agent.service import AgentService
    agent_service = AgentService(db=db)
    
    try:
        recommendation = await agent_service.generate_recommendation(
            analysis_id=analysis.id,
            organization_id=str(request.organization_id)
        )
        # SQLAlchemy ilişkiyi otomatik yansıtmamış olabilir, manually set for response
        analysis.recommendation = recommendation
        return AnalysisResponse.model_validate(analysis)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent analysis failed: {str(e)}",
        )

