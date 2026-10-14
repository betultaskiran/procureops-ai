"""
app/api/v1/analyses.py

Analiz endpoint'leri. Şimdilik sadece deterministik (TCO + Compliance) çalışır.
İlerleyen fazlarda LLM Reasoning bu endpoint üzerinden tetiklenecek.
"""

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.orchestrator import DeterministicEngine
from app.models.analysis import ComplianceResult

router = APIRouter(prefix="/api/v1", tags=["analyses"])


def _is_later(dt_a: datetime | None, dt_b: datetime | None) -> bool:
    """
    dt_a'nın dt_b'den sonra olup olmadığını güvenle kontrol eder.
    None değerlerini ve timezone-aware / naive datetime uyuşmazlıklarını
    hata üretmeden UTC tabanında eşitler.
    """
    if dt_a is None or dt_b is None:
        return False
    if dt_a.tzinfo is not None and dt_b.tzinfo is None:
        dt_b = dt_b.replace(tzinfo=timezone.utc)
    elif dt_a.tzinfo is None and dt_b.tzinfo is not None:
        dt_a = dt_a.replace(tzinfo=timezone.utc)
    return dt_a > dt_b


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
    is_stale: bool = False

    model_config = {"from_attributes": True}


def _resolve_policy_rules(rfq, explicit_rules: PolicyRules | None) -> PolicyRules:
    """
    İstek gövdesinde açıkça belirtilmeyen kuralları RFQ'nun kendi
    ticari ve bütçe alanlarından otomatik olarak türetir.
    """
    budget = (
        explicit_rules.max_tco_budget
        if explicit_rules and explicit_rules.max_tco_budget is not None
        else (float(rfq.budget) if rfq.budget is not None else None)
    )
    delivery = (
        explicit_rules.max_delivery_days
        if explicit_rules and explicit_rules.max_delivery_days is not None
        else rfq.max_delivery_days
    )
    warranty = (
        explicit_rules.min_warranty_months
        if explicit_rules and explicit_rules.min_warranty_months is not None
        else rfq.min_warranty_months
    )
    if explicit_rules and explicit_rules.require_payment_terms is not None:
        payment_terms = explicit_rules.require_payment_terms
    elif rfq.payment_terms:
        payment_terms = [rfq.payment_terms]
    else:
        payment_terms = None

    return PolicyRules(
        max_tco_budget=budget,
        max_delivery_days=delivery,
        min_warranty_months=warranty,
        require_payment_terms=payment_terms,
    )


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
    from app.models.rfq import RFQ, RFQStatus
    from app.models.analysis import Analysis, AnalysisStatus
    from app.models.audit import AuditEvent
    from sqlalchemy import select

    # 1. RFQ kontrolü
    rfq = await db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} bulunamadı."
        )

    # İptal edilmiş RFQ kontrolü
    if rfq.status == RFQStatus.CANCELLED.value or rfq.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="İptal edilmiş (cancelled) bir talep için analiz çalıştırılamaz."
        )

    # Multi-tenancy kontrolü: İstemci başka bir organizasyon kimliği gönderdiyse yetkisiz
    if request.organization_id and rfq.organization_id and request.organization_id != rfq.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu organizasyona ait olmayan bir talep için analiz başlatamazsınız."
        )

    # Concurrency kilidi: Halen RUNNING durumunda olan bir analiz varsa 409 dön
    running_res = await db.execute(
        select(Analysis.id).where(
            Analysis.rfq_id == rfq_id,
            Analysis.status == AnalysisStatus.RUNNING.value
        ).limit(1)
    )
    if running_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu RFQ için devam eden aktif bir analiz süreci bulunmaktadır."
        )

    # Kuralları çözümle (RFQ alanları ile fallback)
    effective_rules = _resolve_policy_rules(rfq, request.rules)

    # Deterministik Analiz (TCO ve Kurallar)
    det_engine = DeterministicEngine(db=db)
    try:
        analysis = await det_engine.run_analysis(rfq_id=rfq_id, rules=effective_rules)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # 2. Agentic Analiz (LLM Reasoning)
    from app.services.agent.service import AgentService
    agent_service = AgentService(db=db)
    
    try:
        # Organizasyon otoritesi RFQ'dan türetilir, istemciye güvenilmez
        tenant_org_id = str(rfq.organization_id) if rfq.organization_id else ""
        recommendation = await agent_service.generate_recommendation(
            analysis_id=analysis.id,
            organization_id=tenant_org_id
        )
        
        # 3. Doğrulama Katmanı (Verification)
        from app.services.agent.verification import VerificationService
        verification_service = VerificationService(db=db)
        verified_recommendation = await verification_service.verify_recommendation(recommendation_id=recommendation.id)

        # Reload analysis with evidence items
        await db.refresh(analysis, ["evidence_items"])

        # RFQ durumunu güncelle ve analiz zaman damgasını senkronize et
        rfq.status = "pending_approval"
        analysis.created_at = func.now()
        analysis.updated_at = func.now()

        # AuditEvent kaydet
        db.add(AuditEvent(
            organization_id=rfq.organization_id,
            event_type="analysis_completed",
            entity_type="analysis",
            entity_id=analysis.id,
            payload={
                "rfq_id": str(rfq.id),
                "quote_count": len(analysis.tco_results),
                "rules": effective_rules.model_dump(),
            }
        ))
        await db.commit()
        await db.refresh(analysis, ["created_at", "updated_at"])

        analysis.recommendation = verified_recommendation
        resp = AnalysisResponse.model_validate(analysis)
        resp.is_stale = False
        return resp
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        analysis.status = AnalysisStatus.FAILED
        await db.commit()
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
    organization_id: uuid.UUID | None = None

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
    from app.models.rfq import RFQ, RFQStatus
    from app.models.quote import Quote
    from app.models.order import PurchaseOrder
    from app.models.audit import AuditEvent
    from app.services.workflow.order import PurchaseOrderService
    from app.services.workflow.email import EmailService
    from sqlalchemy import select
    from datetime import datetime

    # Analizin varlığını kontrol et
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # RFQ kontrolü
    rfq = await db.get(RFQ, analysis.rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    # İptal edilmiş RFQ kontrolü
    if rfq.status == "cancelled" or rfq.status == RFQStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="İptal edilmiş (cancelled) bir RFQ'ya ait analiz onaylanamaz veya değerlendirilemez."
        )

    # Multi-tenancy kontrolü
    if request.organization_id and rfq.organization_id and request.organization_id != rfq.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu organizasyona ait olmayan bir analiz için işlem yapamazsınız."
        )

    if request.status not in [e.value for e in ApprovalStatus]:
        raise HTTPException(status_code=400, detail="Invalid approval status")

    # Seçilen teklifin RFQ'ya ait olduğunu doğrula
    if request.selected_quote_id:
        selected_quote = await db.get(Quote, request.selected_quote_id)
        if not selected_quote or selected_quote.rfq_id != rfq.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Seçilen teklif bu RFQ'ya ait değildir."
            )

    # Onay işlemlerinde kural uyumsuzluğu ve duplicate PO koruması
    if request.status in [ApprovalStatus.APPROVED.value, ApprovalStatus.EXCEPTION_APPROVED.value]:
        # Hangi quote onaylanacak?
        chosen_quote_id = request.selected_quote_id
        if not chosen_quote_id:
            await db.refresh(analysis, ["recommendation"])
            if analysis.recommendation:
                chosen_quote_id = analysis.recommendation.recommended_quote_id

        if chosen_quote_id:
            chosen_quote = await db.get(Quote, chosen_quote_id)
            if chosen_quote and chosen_quote.is_compliant is False:
                # Kural ihlali olan teklif için zorunlu exception_approved ve acknowledge kontrolü
                if (
                    request.status != ApprovalStatus.EXCEPTION_APPROVED.value
                    or not request.acknowledged_policy_violation
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Deterministik kurallara uymayan teklifler standart olarak onaylanamaz. "
                            "'exception_approved' statüsü ve kural ihlalinin açıkça teyit edilmesi "
                            "(acknowledged_policy_violation=True) zorunludur."
                        )
                    )

        # Mükerrer PO koruması: RFQ için aktif bir PO varsa tekrar onaylanamaz
        existing_po_res = await db.execute(
            select(PurchaseOrder)
            .join(Quote, PurchaseOrder.quote_id == Quote.id)
            .where(
                Quote.rfq_id == rfq.id,
                PurchaseOrder.status != "cancelled"
            )
        )
        active_po = existing_po_res.scalar_one_or_none()
        if active_po:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Bu RFQ için zaten düzenlenmiş aktif bir Sipariş Emri ({active_po.po_number}) bulunmaktadır."
            )

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
    await db.flush()

    # İş akışı (Workflow) ayrımı:
    if request.status in [ApprovalStatus.APPROVED.value, ApprovalStatus.EXCEPTION_APPROVED.value]:
        rfq.status = RFQStatus.APPROVED.value
        db.add(rfq)
        await db.flush()
            
        # 1. PO Kaydı oluştur (senkron)
        po = await PurchaseOrderService.create_po_from_approval(db, approval)
        # 2. Email Job'ı kuyruğa at (asenkron, BackgroundTasks)
        background_tasks.add_task(EmailService.send_po_email, str(po.id))
    
    # AuditEvent kaydet
    db.add(AuditEvent(
        organization_id=rfq.organization_id,
        actor_id=request.reviewer_id,
        event_type="analysis_reviewed",
        entity_type="approval",
        entity_id=approval.id,
        payload={
            "analysis_id": str(analysis_id),
            "status": request.status,
            "selected_quote_id": str(request.selected_quote_id) if request.selected_quote_id else None,
            "acknowledged_policy_violation": request.acknowledged_policy_violation,
            "comment": request.comment
        }
    ))

    await db.commit()
    await db.refresh(approval)

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
    from app.models.quote import Quote
    from app.models.rfq import RFQ

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

    # Dinamik bayatlama (staleness) kontrolü:
    # 1. RFQ kuralları/detayları analizden sonra güncellendiyse (rfq.updated_at > analysis.created_at)
    # 2. Teklif sayısı analizde temsil edilen teklif sayısından farklıysa (yeni teklif eklendi/silindi)
    # 3. Herhangi bir teklif analizden sonra güncellendiyse (quote.updated_at > analysis.created_at)
    rfq = await db.get(RFQ, rfq_id)
    quotes_res = await db.execute(
        select(Quote).where(Quote.rfq_id == rfq_id)
    )
    current_quotes = list(quotes_res.scalars().all())

    # Analizde temsil edilen teklif sayısı:
    # Cascade delete nedeniyle silinen tekliflerin tco_results kayıtları silinmiş olabileceğinden,
    # analizin tamamlandığı andaki orijinal teklif sayısını AuditEvent kaydından teyit ederiz.
    from app.models.audit import AuditEvent
    represented_quote_count = len(analysis.tco_results)
    audit_res = await db.execute(
        select(AuditEvent.payload).where(
            AuditEvent.entity_id == analysis.id,
            AuditEvent.event_type == "analysis_completed"
        ).limit(1)
    )
    audit_payload = audit_res.scalar_one_or_none()
    if audit_payload and isinstance(audit_payload, dict) and "quote_count" in audit_payload:
        represented_quote_count = int(audit_payload["quote_count"])

    is_stale = False
    if rfq and _is_later(rfq.updated_at, analysis.created_at):
        is_stale = True
    elif len(current_quotes) != represented_quote_count:
        is_stale = True
    else:
        analyzed_quote_ids = {tco.quote_id for tco in analysis.tco_results}
        for q in current_quotes:
            if q.id not in analyzed_quote_ids:
                is_stale = True
                break
            if _is_later(q.updated_at, analysis.created_at):
                is_stale = True
                break
        
    resp = AnalysisResponse.model_validate(analysis)
    resp.is_stale = is_stale
    return resp
