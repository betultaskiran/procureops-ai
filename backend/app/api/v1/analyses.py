"""
app/api/v1/analyses.py

Analiz endpoint'leri. Şimdilik sadece deterministik (TCO + Compliance) çalışır.
İlerleyen fazlarda LLM Reasoning bu endpoint üzerinden tetiklenecek.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
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
    organization_id: uuid.UUID | None = None
    rules: PolicyRules | None = None


class EvidenceItemResponse(BaseModel):
    source_type: str
    source_reference: str
    claim: str

    model_config = {"from_attributes": True}

class RecommendationResponse(BaseModel):
    recommended_quote_id: uuid.UUID | None
    reasoning: str
    risks: str | None
    alternative_notes: str | None
    verification_status: str
    verification_notes: str | None = None
    # evidence_items must not be mandatory or the model_validate will fail if it's not loaded
    # wait, we didn't add evidence_items relationship to the Pydantic schema properly yet. We'll skip evidence_items in the schema for now and just show verification_notes.
    
    model_config = {"from_attributes": True}


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    rfq_id: uuid.UUID
    status: str
    tco_results: List[TCOResultResponse] = []
    compliance_checks: List[ComplianceCheckResponse] = []
    recommendation: RecommendationResponse | None = None
    evidence_items: List[EvidenceItemResponse] = []

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
        analysis = await det_engine.run_analysis(rfq_id=rfq_id, rules=request.rules or PolicyRules())
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
        
        # 3. Doğrulama Katmanı (Verification)
        from app.services.agent.verification import VerificationService
        verification_service = VerificationService(db=db)
        verified_recommendation = await verification_service.verify_recommendation(recommendation_id=recommendation.id)

        # Reload analysis with evidence items
        await db.refresh(analysis, ["evidence_items"])

        # SQLAlchemy ilişkiyi otomatik yansıtmamış olabilir, manually set for response
        # Update RFQ status
        from app.models.rfq import RFQ
        rfq_obj = await db.get(RFQ, rfq_id)
        if rfq_obj:
            rfq_obj.status = "pending_approval"
            await db.commit()

        analysis.recommendation = verified_recommendation
        return AnalysisResponse.model_validate(analysis)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent analysis failed: {str(e)}",
        )

class ReviewRequest(BaseModel):
    status: str # "approved", "rejected", "revision_requested", "exception_requested", "exception_approved"
    comment: str | None = None
    reviewer_id: uuid.UUID | None = None # Geliştirme ortamı için opsiyonel
    selected_quote_id: uuid.UUID | None = None
    acknowledged_policy_violation: bool = False

class ReviewResponse(BaseModel):
    id: uuid.UUID
    analysis_id: uuid.UUID
    status: str
    comment: str | None
    selected_quote_id: uuid.UUID | None
    acknowledged_policy_violation: bool
    
    model_config = {"from_attributes": True}

@router.post(
    "/analyses/{analysis_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analiz Önerisini Değerlendir (Human Approval)"
)
async def review_analysis(
    analysis_id: uuid.UUID,
    request: ReviewRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Sistemin sunduğu LLM tavsiyesini bir insanın (manager) inceleyip 
    onaylaması veya reddetmesi işlemini gerçekleştirir.
    """
    from app.models.analysis import Analysis, Approval, ApprovalStatus
    from app.services.workflow.order import PurchaseOrderService
    from app.services.workflow.email import EmailService
    from sqlalchemy import select
    from datetime import datetime

    # Analizin varlığını kontrol et
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if request.status not in [e.value for e in ApprovalStatus]:
        raise HTTPException(status_code=400, detail="Invalid approval status")

    approval = Approval(
        analysis_id=analysis_id,
        reviewer_id=request.reviewer_id,
        status=request.status,
        comment=request.comment,
        reviewed_at=datetime.utcnow(),
        selected_quote_id=request.selected_quote_id,
        acknowledged_policy_violation=request.acknowledged_policy_violation
    )
    
    db.add(approval)
    await db.commit()
    await db.refresh(approval)

    # İş akışı (Workflow) ayrımı:
    if request.status in [ApprovalStatus.APPROVED.value, ApprovalStatus.EXCEPTION_APPROVED.value]:
        # 1. PO Kaydı oluştur (senkron)
        po = await PurchaseOrderService.create_po_from_approval(db, approval)
        # 2. Email Job'ı kuyruğa at (asenkron, BackgroundTasks)
        background_tasks.add_task(EmailService.send_po_email, str(po.id))
    
    # REJECTED veya REVISION_REQUESTED durumlarında PO/Email çalışmaz.

    return ReviewResponse.model_validate(approval)


@router.get(
    "/rfqs/{rfq_id}/analysis",
    response_model=AnalysisResponse,
    summary="Get Latest Analysis for RFQ",
    description="Fetches the most recent analysis (TCO, compliance, and AI recommendation) for an RFQ."
)
async def get_latest_analysis(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AnalysisResponse:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.analysis import Analysis

    result = await db.execute(
        select(Analysis)
        .where(Analysis.rfq_id == rfq_id)
        .options(
            selectinload(Analysis.tco_results),
            selectinload(Analysis.compliance_checks),
            selectinload(Analysis.recommendation),
            selectinload(Analysis.evidence_items)
        )
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No analysis found for RFQ {rfq_id}"
        )
        
    return AnalysisResponse.model_validate(analysis)
