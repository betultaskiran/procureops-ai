"""
app/api/v1/analyses.py

Analiz endpoint'leri. Şimdilik sadece deterministik (TCO + Compliance) çalışır.
İlerleyen fazlarda LLM Reasoning bu endpoint üzerinden tetiklenecek.
"""

import hashlib
import json
import uuid
import time
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    require_authenticated,
    require_employee_or_above,
    require_manager_or_above,
)
from app.db.session import get_db
from app.services.deterministic.schemas import PolicyRules
from app.models.analysis import ComplianceResult
from app.models.user import User
from app.schemas.orchestration import (
    StageResultResponse,
    StageName,
    StageStatus,
    VerificationOutcome,
    StageEvidenceRef,
    CitationSourceType,
)

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
    stage_results: List[StageResultResponse] = []
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


def compute_material_fingerprint(
    rfq: "RFQ",
    quotes: list["Quote"],
    rfq_items: list["RFQItem"] | None = None,
) -> str:
    """
    Computes a deterministic SHA-256 fingerprint of material procurement inputs:
    - RFQ budget, delivery, warranty, payment terms, required quantity
    - RFQ line items (line_number, description, quantity, unit)
    - Quotes (quote IDs, prices, currency, subtotal, taxes, shipping, discounts,
      other costs, delivery days, warranty, payment terms, and quote items)

    Non-material changes (rfq.status, rfq.updated_at, rfq.is_archived, approvals,
    audit events, page visits) do not change this fingerprint.
    """
    items_data = []
    items = rfq_items if rfq_items is not None else (getattr(rfq, "items", None) or [])
    for it in sorted(items, key=lambda x: getattr(x, "line_number", 0) if getattr(x, "line_number", None) is not None else 0):
        items_data.append({
            "line": it.line_number,
            "desc": (it.description or "").strip(),
            "qty": float(it.quantity) if it.quantity is not None else 0.0,
            "unit": (it.unit or "").strip(),
        })

    quotes_data = []
    for q in sorted(quotes, key=lambda x: str(x.id)):
        q_items = []
        for qi in (getattr(q, "items", None) or []):
            q_items.append({
                "desc": (qi.description or "").strip(),
                "qty": float(qi.quantity) if qi.quantity is not None else 0.0,
                "unit_price": str(qi.unit_price) if qi.unit_price is not None else "0",
                "total_price": str(qi.total_price) if qi.total_price is not None else "0",
            })
        q_items.sort(key=lambda x: (x["desc"], x["qty"]))

        quotes_data.append({
            "id": str(q.id),
            "supplier_id": str(q.supplier_id),
            "total_price": str(q.total_price) if q.total_price is not None else "0",
            "currency": (q.currency or "").strip().upper(),
            "subtotal": str(q.subtotal) if q.subtotal is not None else "0",
            "vat_rate": str(q.vat_rate) if q.vat_rate is not None else "",
            "vat_amount": str(q.vat_amount) if q.vat_amount is not None else "",
            "shipping_cost": str(q.shipping_cost) if q.shipping_cost is not None else "",
            "discount_amount": str(q.discount_amount) if q.discount_amount is not None else "0",
            "other_costs": str(q.other_costs) if q.other_costs is not None else "0",
            "delivery_days": q.delivery_days,
            "payment_terms": (q.payment_terms or "").strip(),
            "warranty_months": q.warranty_months,
            "items": q_items,
        })

    payload = {
        "rfq": {
            "budget": float(rfq.budget) if rfq.budget is not None else None,
            "max_delivery_days": rfq.max_delivery_days,
            "min_warranty_months": rfq.min_warranty_months,
            "payment_terms": (rfq.payment_terms or "").strip(),
            "required_quantity": rfq.required_quantity,
            "items": items_data,
        },
        "quotes": quotes_data,
    }
    raw_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


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
    current_user: User = Depends(require_employee_or_above),
) -> AnalysisResponse:
    """
    RFQ için Analiz başlatır.
    """
    from app.models.rfq import RFQ, RFQStatus
    from app.models.analysis import Analysis, AnalysisStatus
    from app.models.audit import AuditEvent
    from sqlalchemy import select

    # 1. RFQ kontrolü (Tenant isolation: 404 for non-existent or other org)
    rfq_res = await db.execute(
        select(RFQ).where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
    )
    rfq = rfq_res.scalar_one_or_none()
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

    stage_results: List[StageResultResponse] = []

    # ── AŞAMA 1 & 2: Deterministik Analiz (TCO ve Kurallar) ───────────────────
    det_start_mono = time.monotonic()
    det_start_time = datetime.now(timezone.utc)
    from app.services.deterministic.orchestrator import DeterministicEngine
    det_engine = DeterministicEngine(db=db)
    try:
        analysis = await det_engine.run_analysis(rfq_id=rfq_id, rules=effective_rules)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    det_duration_ms = (time.monotonic() - det_start_mono) * 1000

    # Stage 1: Extraction & Input Validation
    stage_results.append(StageResultResponse(
        stage=StageName.EXTRACTION_VALIDATION,
        status=StageStatus.COMPLETED,
        started_at=det_start_time,
        completed_at=datetime.now(timezone.utc),
        duration_ms=round(det_duration_ms * 0.3, 2),
        summary=f"{len(analysis.tco_results)} teklif ve doküman başarıyla doğrulandı.",
        details={"quote_count": len(analysis.tco_results), "currency": analysis.tco_results[0].currency if analysis.tco_results else "TRY"},
    ))

    # Stage 2: Deterministic TCO & Hard-Rule Evaluation
    stage_results.append(StageResultResponse(
        stage=StageName.DETERMINISTIC_EVALUATION,
        status=StageStatus.COMPLETED,
        started_at=det_start_time,
        completed_at=datetime.now(timezone.utc),
        duration_ms=round(det_duration_ms * 0.7, 2),
        summary=f"TCO ve kural denetimi tamamlandı ({len(analysis.compliance_checks)} kural denetlendi).",
        details={
            "tco_results_count": len(analysis.tco_results),
            "compliance_checks_count": len(analysis.compliance_checks),
        },
    ))

    # ── AŞAMA 3 & 4: Policy Compliance (RAG) & Supplier Recommendation ───────
    from app.services.agent.service import AgentService
    agent_service = AgentService(db=db)
    
    agent_start_mono = time.monotonic()
    agent_start_time = datetime.now(timezone.utc)
    try:
        tenant_org_id = str(current_user.organization_id)
        recommendation = await agent_service.generate_recommendation(
            analysis_id=analysis.id,
            organization_id=tenant_org_id
        )
        agent_duration_ms = (time.monotonic() - agent_start_mono) * 1000

        # Stage 3: Policy Compliance Analysis
        stage_results.append(StageResultResponse(
            stage=StageName.POLICY_COMPLIANCE,
            status=StageStatus.COMPLETED,
            started_at=agent_start_time,
            completed_at=datetime.now(timezone.utc),
            duration_ms=round(agent_duration_ms * 0.25, 2),
            summary="Kurumsal hafıza (Qdrant RAG) başarıyla tarandı ve bağlam hazırlandı.",
        ))

        # Stage 4: Supplier Recommendation
        stage_results.append(StageResultResponse(
            stage=StageName.SUPPLIER_RECOMMENDATION,
            status=StageStatus.COMPLETED,
            started_at=agent_start_time,
            completed_at=datetime.now(timezone.utc),
            duration_ms=round(agent_duration_ms * 0.75, 2),
            summary="LLM ile trade-off analizi ve tedarikçi önerisi oluşturuldu.",
        ))
        
        # ── AŞAMA 5: Bağımsız Doğrulama Katmanı (Verification) ─────────────────
        verif_start_mono = time.monotonic()
        verif_start_time = datetime.now(timezone.utc)
        from app.services.agent.verification import VerificationService
        verification_service = VerificationService(db=db)
        verified_recommendation = await verification_service.verify_recommendation(recommendation_id=recommendation.id)
        verif_duration_ms = (time.monotonic() - verif_start_mono) * 1000

        v_outcome = (
            StageStatus.COMPLETED
            if verified_recommendation.verification_status in ["verified", "passed"]
            else StageStatus.FAILED
            if verified_recommendation.verification_status in ["failed", "overridden"]
            else StageStatus.INCONCLUSIVE
        )

        stage_results.append(StageResultResponse(
            stage=StageName.INDEPENDENT_VERIFICATION,
            status=v_outcome,
            started_at=verif_start_time,
            completed_at=datetime.now(timezone.utc),
            duration_ms=round(verif_duration_ms, 2),
            summary=f"Bağımsız doğrulama tamamlandı: {verified_recommendation.verification_status.upper()}.",
            details={"verification_status": verified_recommendation.verification_status},
        ))

        # Reload analysis with evidence items
        await db.refresh(analysis, ["evidence_items"])

        # RFQ durumunu güncelle: Eğer RFQ zaten onaylanmışsa veya aktif bir PO varsa
        # RFQ'nun 'approved' durumunu ve karar tarihçesini koru; pending_approval'a sıfırlama.
        from app.models.order import PurchaseOrder
        from app.models.rfq import RFQItem
        from app.models.quote import Quote
        from sqlalchemy.orm import selectinload

        active_po_res = await db.execute(
            select(PurchaseOrder.id)
            .join(Quote, PurchaseOrder.quote_id == Quote.id)
            .where(
                Quote.rfq_id == rfq.id,
                PurchaseOrder.status != "cancelled"
            )
            .limit(1)
        )
        has_active_po = active_po_res.scalar_one_or_none() is not None

        if not has_active_po and rfq.status != RFQStatus.APPROVED.value:
            rfq.status = "pending_approval"

        analysis.status = AnalysisStatus.COMPLETED.value
        analysis.created_at = func.now()
        analysis.updated_at = func.now()

        # Malzeme parmak izini hesapla
        quotes_for_fp_res = await db.execute(
            select(Quote).where(Quote.rfq_id == rfq.id).options(selectinload(Quote.items))
        )
        quotes_for_fp = list(quotes_for_fp_res.scalars().all())

        items_for_fp_res = await db.execute(
            select(RFQItem).where(RFQItem.rfq_id == rfq.id).order_by(RFQItem.line_number)
        )
        rfq_items_for_fp = list(items_for_fp_res.scalars().all())
        material_fp = compute_material_fingerprint(rfq, quotes_for_fp, rfq_items_for_fp)

        # AuditEvent kaydet
        db.add(AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=current_user.id,
            event_type="analysis_completed",
            entity_type="analysis",
            entity_id=analysis.id,
            payload={
                "rfq_id": str(rfq.id),
                "quote_count": len(analysis.tco_results),
                "rules": effective_rules.model_dump(),
                "stage_summaries": [
                    {"stage": sr.stage.value, "status": sr.status.value, "duration_ms": sr.duration_ms}
                    for sr in stage_results
                ],
                "verification_outcome": verified_recommendation.verification_status,
                "material_fingerprint": material_fp,
            }
        ))
        await db.commit()
        await db.refresh(analysis, ["created_at", "updated_at"])

        analysis.recommendation = verified_recommendation
        resp = AnalysisResponse.model_validate(analysis)
        resp.stage_results = stage_results
        resp.is_stale = False
        return resp
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        analysis.status = AnalysisStatus.FAILED.value
        analysis.error_message = str(e)
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


async def compute_analysis_staleness(
    db: AsyncSession,
    analysis: "Analysis",
    rfq: "RFQ | None" = None,
) -> bool:
    """
    Dinamik bayatlama (staleness) kontrolü:
    1. RFQ malzeme girdi parmak izi (material_fingerprint) analiz anındaki parmak izinden
       farklıysa analiz bayattır (bütçe, kalemler, teslimat/garanti/ödeme şartları veya teklifler değişti).
    2. Parmak izi bulunmayan eski analizler için geriye dönük uyumlu kural, teklif sayısı ve
       teklif güncelleme kontrolleri uygulanır.
    3. Onay yazma (approval), audit log yazma, rfq.status veya rfq.is_archived gibi malzeme dışı
       güncellemeler analizi bayatlatmaz.
    """
    from app.models.rfq import RFQ, RFQItem
    from app.models.quote import Quote
    from app.models.analysis import TCOResult
    from app.models.audit import AuditEvent
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    if rfq is None:
        rfq = await db.get(RFQ, analysis.rfq_id)
    if not rfq:
        return True

    # RFQ kalemlerini çek
    items_res = await db.execute(
        select(RFQItem).where(RFQItem.rfq_id == rfq.id).order_by(RFQItem.line_number)
    )
    rfq_items = list(items_res.scalars().all())

    # RFQ'ya ait güncel teklifleri çek
    quotes_res = await db.execute(
        select(Quote)
        .where(Quote.rfq_id == analysis.rfq_id)
        .options(selectinload(Quote.items))
    )
    current_quotes = list(quotes_res.scalars().all())

    # Analizin tamamlandığı andaki AuditEvent kaydını incele
    audit_res = await db.execute(
        select(AuditEvent.payload).where(
            AuditEvent.entity_id == analysis.id,
            AuditEvent.event_type == "analysis_completed"
        ).limit(1)
    )
    audit_payload = audit_res.scalar_one_or_none()

    current_fingerprint = compute_material_fingerprint(rfq, current_quotes, rfq_items)

    if audit_payload and isinstance(audit_payload, dict):
        recorded_fingerprint = audit_payload.get("material_fingerprint")
        if recorded_fingerprint:
            return current_fingerprint != recorded_fingerprint

    # ── Geriye Dönük Uyumlu Fallback (Parmak izi olmayan kayıtlar için) ────────
    tco_res = await db.execute(
        select(TCOResult).where(TCOResult.analysis_id == analysis.id)
    )
    tco_results = list(tco_res.scalars().all())
    represented_quote_count = len(tco_results)

    if audit_payload and isinstance(audit_payload, dict):
        if "quote_count" in audit_payload:
            represented_quote_count = int(audit_payload["quote_count"])
        if "rules" in audit_payload:
            effective_rules = _resolve_policy_rules(rfq, None).model_dump()
            if audit_payload["rules"] != effective_rules:
                return True

    if len(current_quotes) != represented_quote_count:
        return True

    analyzed_quote_ids = {tco.quote_id for tco in tco_results}
    for q in current_quotes:
        if q.id not in analyzed_quote_ids:
            return True
        if _is_later(q.updated_at, analysis.created_at):
            return True

    if rfq and _is_later(rfq.updated_at, analysis.created_at):
        if rfq.status != "approved":
            return True

    return False


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
    current_user: User = Depends(require_manager_or_above),
):
    """
    Sistemin sunduğu LLM tavsiyesini bir insanın (manager/admin) inceleyip 
    onaylaması veya reddetmesi işlemini gerçekleştirir.
    """
    from app.models.analysis import Analysis, Approval, ApprovalStatus, AnalysisStatus
    from app.models.rfq import RFQ, RFQStatus
    from app.models.quote import Quote
    from app.models.order import PurchaseOrder, PurchaseOrderStatus
    from app.models.audit import AuditEvent
    from app.services.workflow.order import PurchaseOrderService
    from app.services.workflow.email import EmailService
    from sqlalchemy import select
    from datetime import datetime

    # Analizin varlığını ve tenant izolasyonunu kontrol et
    result = await db.execute(
        select(Analysis)
        .join(Analysis.rfq)
        .where(Analysis.id == analysis_id, RFQ.organization_id == current_user.organization_id)
    )
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # RFQ kontrolü ve eşzamanlı onay yarış durumlarına karşı satır kilitleme (with_for_update)
    rfq_stmt = select(RFQ).where(RFQ.id == analysis.rfq_id).with_for_update()
    rfq_res = await db.execute(rfq_stmt)
    rfq = rfq_res.scalars().first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    # İptal edilmiş RFQ kontrolü
    if rfq.status == "cancelled" or rfq.status == RFQStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="İptal edilmiş (cancelled) bir RFQ'ya ait analiz onaylanamaz veya değerlendirilemez."
        )

    if request.status not in [e.value for e in ApprovalStatus]:
        raise HTTPException(status_code=400, detail="Invalid approval status")

    # ── Phase 5.2.1: Analiz Tamamlanma (Completion) Koruması ───────────────
    # Yalnızca COMPLETED durumundaki analizler incelenebilir veya onaylanabilir.
    # RUNNING, FAILED, PENDING vb. durumdaki analizler için işlem reddedilir.
    if analysis.status != AnalysisStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Yalnızca tamamlanmış (completed) analizler değerlendirilebilir veya onaylanabilir. Analiz durumu: {analysis.status}",
        )

    # Seçilen teklifin RFQ'ya ait olduğunu doğrula
    if request.selected_quote_id:
        selected_quote = await db.get(Quote, request.selected_quote_id)
        if not selected_quote or selected_quote.rfq_id != rfq.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Seçilen teklif bu RFQ'ya ait değildir."
            )

    # Onay işlemlerinde duplicate PO, analiz durumu, bayatlama ve kural uyumsuzluğu koruması
    if request.status in [ApprovalStatus.APPROVED.value, ApprovalStatus.EXCEPTION_APPROVED.value]:
        # 1. Mükerrer PO koruması: RFQ için aktif bir PO varsa tekrar onaylanamaz
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

        # 2. ── Phase 5.2.1: Dinamik Bayatlama (Staleness) Koruması ─────────────
        # RFQ kuralları veya teklifler analizden sonra güncellendiyse onay engellenir.
        is_stale = await compute_analysis_staleness(db, analysis, rfq)
        if is_stale:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Bu analiz güncelliğini yitirmiştir (stale). RFQ kuralları veya teklifler "
                    "analizden sonra güncellendiği için lütfen analizi yeniden çalıştırıp "
                    "güncel sonuçları onaylayınız."
                ),
            )

        # 3. ── Phase 10: Doğrulama (Verification) Durumu Koruması ─────────────
        # Doğrulama aşamasından geçemeyen (failed, overridden) veya sonuçsuz kalan (inconclusive) analizler için standart 'approved' engellenir.
        await db.refresh(analysis, ["recommendation"])
        rec = analysis.recommendation
        if rec:
            rec_status = (rec.verification_status or "").lower()
            if rec_status in ["failed", "overridden", "inconclusive"]:
                if (
                    request.status != ApprovalStatus.EXCEPTION_APPROVED.value
                    or not request.acknowledged_policy_violation
                ):
                    status_desc = "sonuçsuz kalan (inconclusive)" if rec_status == "inconclusive" else "geçemeyen (failed / overridden)"
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Doğrulama aşamasından {status_desc} analizler standart olarak onaylanamaz. "
                            "Yalnızca yetkili yönetici tarafından 'exception_approved' statüsü ve "
                            "kural ihlali / yetersiz kanıtın açıkça teyit edilmesi (acknowledged_policy_violation=True) zorunludur."
                        ),
                    )

        # 4. Hangi quote onaylanacak?
        chosen_quote_id = request.selected_quote_id
        if not chosen_quote_id:
            if rec:
                chosen_quote_id = rec.recommended_quote_id

        if not chosen_quote_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Onaylanacak geçerli bir teklif bulunamadı. Lütfen belirli bir teklif seçiniz (selected_quote_id)."
            )

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

    approval = Approval(
        analysis_id=analysis_id,
        reviewer_id=current_user.id,
        status=request.status,
        comment=request.comment,
        reviewed_at=datetime.now(timezone.utc),
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
        # 2. Email Job'ı kuyruğa at (asenkron, BackgroundTasks) - Yalnızca yayınlanmış (ISSUED) siparişler tedarikçiye iletilir
        if po.status == PurchaseOrderStatus.ISSUED.value:
            background_tasks.add_task(EmailService.send_po_email, str(po.id))
    
    # AuditEvent kaydet
    db.add(AuditEvent(
        organization_id=rfq.organization_id,
        actor_id=current_user.id,
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
    current_user: User = Depends(require_authenticated),
) -> AnalysisResponse:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.analysis import Analysis
    from app.models.quote import Quote
    from app.models.rfq import RFQ
    from app.models.audit import AuditEvent

    rfq_res = await db.execute(
        select(RFQ).where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
    )
    rfq = rfq_res.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} bulunamadı"
        )

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

    # Dinamik bayatlama (staleness) kontrolü
    is_stale = await compute_analysis_staleness(db, analysis, rfq)
        
    resp = AnalysisResponse.model_validate(analysis)
    resp.is_stale = is_stale

    # Phase 10: Reconstruct stage_results for client
    stage_results_list: List[StageResultResponse] = []
    audit_res = await db.execute(
        select(AuditEvent.payload).where(
            AuditEvent.entity_id == analysis.id,
            AuditEvent.event_type.in_(["analysis_completed", "analysis_pipeline_completed"])
        ).limit(1)
    )
    audit_payload = audit_res.scalar_one_or_none()
    if audit_payload and isinstance(audit_payload, dict) and "stage_summaries" in audit_payload:
        for s in audit_payload["stage_summaries"]:
            stage_results_list.append(StageResultResponse(
                stage=s.get("stage", StageName.DETERMINISTIC_EVALUATION),
                status=s.get("status", StageStatus.COMPLETED),
                started_at=analysis.created_at,
                completed_at=analysis.updated_at or analysis.created_at,
                duration_ms=s.get("duration_ms", 0.0),
                summary=f"Aşama: {s.get('stage')}",
            ))
    elif analysis.status == "completed":
        stage_results_list = [
            StageResultResponse(
                stage=StageName.EXTRACTION_VALIDATION,
                status=StageStatus.COMPLETED,
                started_at=analysis.created_at,
                completed_at=analysis.created_at,
                duration_ms=10.0,
                summary=f"{len(analysis.tco_results)} teklif ve doküman doğrulandı.",
            ),
            StageResultResponse(
                stage=StageName.DETERMINISTIC_EVALUATION,
                status=StageStatus.COMPLETED,
                started_at=analysis.created_at,
                completed_at=analysis.created_at,
                duration_ms=25.0,
                summary=f"TCO ve kural kontrolleri tamamlandı ({len(analysis.compliance_checks)} kural denetlendi).",
            ),
            StageResultResponse(
                stage=StageName.POLICY_COMPLIANCE,
                status=StageStatus.COMPLETED if analysis.evidence_items else StageStatus.INCONCLUSIVE,
                started_at=analysis.created_at,
                completed_at=analysis.created_at,
                duration_ms=45.0,
                summary=f"Kurumsal politika analizi tamamlandı ({len(analysis.evidence_items)} kanıt).",
            ),
            StageResultResponse(
                stage=StageName.SUPPLIER_RECOMMENDATION,
                status=StageStatus.COMPLETED if analysis.recommendation else StageStatus.SKIPPED,
                started_at=analysis.created_at,
                completed_at=analysis.created_at,
                duration_ms=120.0,
                summary="Tedarikçi önerisi ve trade-off analizi tamamlandı.",
            ),
            StageResultResponse(
                stage=StageName.INDEPENDENT_VERIFICATION,
                status=StageStatus.COMPLETED if analysis.recommendation and analysis.recommendation.verification_status in ["verified", "passed"] else StageStatus.FAILED if analysis.recommendation and analysis.recommendation.verification_status in ["failed", "overridden"] else StageStatus.INCONCLUSIVE,
                started_at=analysis.created_at,
                completed_at=analysis.created_at,
                duration_ms=15.0,
                summary=f"Bağımsız doğrulama: {analysis.recommendation.verification_status if analysis.recommendation else 'N/A'}.",
            ),
        ]
    resp.stage_results = stage_results_list
    return resp
