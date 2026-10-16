import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import (
    require_authenticated,
    require_manager_or_above,
)
from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.order import (
    PurchaseOrder,
    PurchaseOrderStatus,
    POQualityIssue,
    IssueType,
    IssueSeverity,
    QualityIssueStatus,
)
from app.models.quote import Quote
from app.models.rfq import RFQ
from app.models.supplier import Supplier, SupplierHistory
from app.models.user import User

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


# ── Pydantic Request / Response Schemas ────────────────────────────────────────

class DeliverPORequest(BaseModel):
    actual_delivery_date: Optional[date] = None
    delivery_notes: Optional[str] = None


class CompletePORequest(BaseModel):
    final_amount: Optional[Decimal] = Field(None, ge=0)
    completion_notes: Optional[str] = None


class POCancelRequest(BaseModel):
    reason: str = Field(..., min_length=3)


class POQualityIssueCreate(BaseModel):
    issue_type: str = Field(..., description="defect, late_delivery, missing_items, documentation, damaged, other")
    severity: str = Field(default="medium", description="low, medium, critical")
    description: str = Field(..., min_length=3)
    rejection_count: int = Field(default=0, ge=0)


class POQualityIssueUpdate(BaseModel):
    status: str = Field(..., description="resolved, dismissed, open")
    resolution_notes: Optional[str] = Field(None, min_length=2)


class POQualityIssueResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    purchase_order_id: uuid.UUID
    supplier_id: uuid.UUID
    reported_by_id: uuid.UUID | None = None
    reported_by_name: str | None = None
    issue_type: str
    severity: str
    description: str
    rejection_count: int
    status: str = "open"
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderDetailResponse(BaseModel):
    id: uuid.UUID
    po_number: str
    quote_id: uuid.UUID
    approval_id: uuid.UUID
    status: str
    email_sent: bool
    email_sent_at: datetime | None = None
    cancellation_reason: str | None = None
    cancelled_at: datetime | None = None
    expected_delivery_date: date | None = None
    actual_delivery_date: date | None = None
    delivered_at: datetime | None = None
    final_amount: Decimal | None = None
    delivery_notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    # Relationship metadata
    rfq_id: uuid.UUID
    rfq_title: str
    supplier_id: uuid.UUID
    supplier_name: str
    currency: str
    quoted_amount: Decimal
    quality_issues: list[POQualityIssueResponse] = []
    allowed_actions: list[str] = []

    model_config = ConfigDict(from_attributes=True)


# ── Helper Query Functions ────────────────────────────────────────────────────

async def _get_order_or_404(
    po_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> tuple[PurchaseOrder, Quote, RFQ]:
    """
    Purchase Order'ı tenant izolasyonuyla birlikte ilişkileriyle çeker.
    Eğer sipariş başka bir organizasyona aitse veya bulunamazsa 404 fırlatır.
    """
    stmt = (
        select(PurchaseOrder)
        .join(PurchaseOrder.quote)
        .join(Quote.rfq)
        .where(
            PurchaseOrder.id == po_id,
            RFQ.organization_id == current_user.organization_id,
        )
        .options(
            selectinload(PurchaseOrder.quote).selectinload(Quote.rfq),
            selectinload(PurchaseOrder.quote).selectinload(Quote.supplier),
            selectinload(PurchaseOrder.quality_issues).selectinload(POQualityIssue.reported_by),
            selectinload(PurchaseOrder.supplier_history_entry),
        )
    )
    res = await db.execute(stmt)
    po = res.scalar_one_or_none()
    if not po or not po.quote or not po.quote.rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Satın Alma Siparişi ({po_id}) bulunamadı.",
        )
    return po, po.quote, po.quote.rfq


def _compute_allowed_actions(po: PurchaseOrder, is_manager_or_above: bool) -> list[str]:
    """Siparişin durumuna ve kullanıcı yetkisine göre izin verilen aksiyonları listeler."""
    if not is_manager_or_above:
        return []
    
    actions: list[str] = []
    if po.status == PurchaseOrderStatus.ISSUED.value:
        actions.extend(["deliver", "cancel", "add_quality_issue"])
    elif po.status == PurchaseOrderStatus.DELIVERED.value:
        actions.extend(["complete", "cancel", "add_quality_issue"])
    elif po.status == PurchaseOrderStatus.COMPLETED.value:
        actions.append("add_quality_issue")
    elif po.status == PurchaseOrderStatus.DRAFT.value:
        actions.append("cancel")
    return actions


def _build_order_response(
    po: PurchaseOrder,
    quote: Quote,
    rfq: RFQ,
    is_manager_or_above: bool,
) -> PurchaseOrderDetailResponse:
    """PurchaseOrder modelini zenginleştirilmiş yanıt DTO'suna çevirir."""
    quality_issues_dto = [
        POQualityIssueResponse(
            id=qi.id,
            organization_id=qi.organization_id,
            purchase_order_id=qi.purchase_order_id,
            supplier_id=qi.supplier_id,
            reported_by_id=qi.reported_by_id,
            reported_by_name=qi.reported_by.full_name if qi.reported_by else None,
            issue_type=qi.issue_type,
            severity=qi.severity,
            description=qi.description,
            rejection_count=int(qi.rejection_count),
            status=getattr(qi, "status", QualityIssueStatus.OPEN.value),
            resolution_notes=getattr(qi, "resolution_notes", None),
            resolved_at=getattr(qi, "resolved_at", None),
            created_at=qi.created_at,
        )
        for qi in (po.quality_issues or [])
    ]

    return PurchaseOrderDetailResponse(
        id=po.id,
        po_number=po.po_number,
        quote_id=po.quote_id,
        approval_id=po.approval_id,
        status=po.status,
        email_sent=po.email_sent,
        email_sent_at=po.email_sent_at,
        cancellation_reason=po.cancellation_reason,
        cancelled_at=po.cancelled_at,
        expected_delivery_date=po.expected_delivery_date,
        actual_delivery_date=po.actual_delivery_date,
        delivered_at=po.delivered_at,
        final_amount=po.final_amount,
        delivery_notes=po.delivery_notes,
        created_at=po.created_at,
        updated_at=po.updated_at,
        rfq_id=rfq.id,
        rfq_title=rfq.title,
        supplier_id=quote.supplier_id,
        supplier_name=quote.supplier.name if quote.supplier else (quote.supplier_name or "Bilinmeyen Tedarikçi"),
        currency=quote.currency or "TRY",
        quoted_amount=quote.total_price,
        quality_issues=quality_issues_dto,
        allowed_actions=_compute_allowed_actions(po, is_manager_or_above),
    )


async def _sync_supplier_history(
    db: AsyncSession,
    po: PurchaseOrder,
    quote: Quote,
) -> SupplierHistory:
    """
    PO teslimat, tamamlama veya kalite kaydı sonrasında SupplierHistory tablosunu senkronize eder.
    Dismissed (reddedilmiş/hükümsüz) kalite kayıtları tedarikçi istatistiğine dahil edilmez.
    """
    sh_query = await db.execute(
        select(SupplierHistory).where(SupplierHistory.purchase_order_id == po.id)
    )
    sh = sh_query.scalar_one_or_none()

    total_amount = po.final_amount if po.final_amount is not None else quote.total_price
    currency = quote.currency or "TRY"

    delay_days = None
    if po.actual_delivery_date and po.expected_delivery_date:
        delay_days = (po.actual_delivery_date - po.expected_delivery_date).days

    active_issues = [
        q for q in (po.quality_issues or [])
        if getattr(q, "status", QualityIssueStatus.OPEN.value) != QualityIssueStatus.DISMISSED.value
    ]
    quality_count = len(active_issues)
    rejections_count = sum(q.rejection_count for q in active_issues)

    if not sh:
        sh = SupplierHistory(
            supplier_id=quote.supplier_id,
            purchase_order_id=po.id,
            order_reference=po.po_number,
            order_date=po.created_at.date(),
            promised_date=po.expected_delivery_date,
            delivered_date=po.actual_delivery_date,
            total_amount=total_amount,
            currency=currency,
            quantity_ordered=1,
            quantity_received=1 if po.actual_delivery_date else None,
            delay_days=delay_days,
            quality_issues=quality_count,
            rejection_count=rejections_count,
            notes=po.delivery_notes,
        )
        db.add(sh)
    else:
        sh.promised_date = po.expected_delivery_date
        sh.delivered_date = po.actual_delivery_date
        sh.total_amount = total_amount
        sh.currency = currency
        if po.actual_delivery_date:
            sh.quantity_received = 1
        sh.delay_days = delay_days
        sh.quality_issues = quality_count
        sh.rejection_count = rejections_count
        if po.delivery_notes:
            sh.notes = po.delivery_notes

    return sh


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/{po_id}",
    response_model=PurchaseOrderDetailResponse,
    summary="Get Purchase Order details",
)
async def get_order_detail(
    po_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> PurchaseOrderDetailResponse:
    po, quote, rfq = await _get_order_or_404(po_id, db, current_user)
    is_manager = current_user.role in ("admin", "manager")
    return _build_order_response(po, quote, rfq, is_manager)


@router.post(
    "/{po_id}/deliver",
    response_model=PurchaseOrderDetailResponse,
    summary="Record actual delivery for a Purchase Order",
)
async def deliver_order(
    po_id: uuid.UUID,
    payload: DeliverPORequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_above),
) -> PurchaseOrderDetailResponse:
    po, quote, rfq = await _get_order_or_404(po_id, db, current_user)

    # State Machine Invariants
    if po.status == PurchaseOrderStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Taslak durumundaki sipariş henüz yayınlanmadan teslim edilemez.",
        )
    if po.status == PurchaseOrderStatus.DELIVERED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sipariş zaten teslim alınmış durumda.",
        )
    if po.status == PurchaseOrderStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tamamlanmış siparişin durumu değiştirilemez.",
        )
    if po.status == PurchaseOrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="İptal edilmiş sipariş teslim alınamaz.",
        )
    if po.status != PurchaseOrderStatus.ISSUED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sipariş durumu ({po.status}) teslim almaya uygun değil.",
        )

    delivery_date = payload.actual_delivery_date or date.today()
    po.status = PurchaseOrderStatus.DELIVERED.value
    po.actual_delivery_date = delivery_date
    po.delivered_at = datetime.now(timezone.utc)

    if payload.delivery_notes and payload.delivery_notes.strip():
        note_text = payload.delivery_notes.strip()
        if po.delivery_notes:
            po.delivery_notes = f"{po.delivery_notes}\n[Teslimat Notu]: {note_text}"
        else:
            po.delivery_notes = f"[Teslimat Notu]: {note_text}"

    delay = (delivery_date - po.expected_delivery_date).days if po.expected_delivery_date else 0

    await _sync_supplier_history(db, po, quote)

    db.add(
        AuditEvent(
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            event_type="po_delivered",
            entity_type="purchase_order",
            entity_id=po.id,
            payload={
                "po_number": po.po_number,
                "actual_delivery_date": str(delivery_date),
                "delay_days": delay,
                "notes": payload.delivery_notes,
            },
        )
    )

    await db.commit()
    await db.refresh(po)
    return _build_order_response(po, quote, rfq, is_manager_or_above=True)


@router.post(
    "/{po_id}/complete",
    response_model=PurchaseOrderDetailResponse,
    summary="Complete a Purchase Order after delivery verification",
)
async def complete_order(
    po_id: uuid.UUID,
    payload: CompletePORequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_above),
) -> PurchaseOrderDetailResponse:
    po, quote, rfq = await _get_order_or_404(po_id, db, current_user)

    # State Machine Invariants
    if po.status == PurchaseOrderStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sipariş zaten tamamlanmış durumda.",
        )
    if po.status == PurchaseOrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="İptal edilmiş sipariş tamamlanamaz.",
        )
    if po.status != PurchaseOrderStatus.DELIVERED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sipariş tamamlanmadan önce teslim edilmiş (delivered) olmalıdır.",
        )

    # Validate final amount - required financial information
    final_amount = payload.final_amount if payload.final_amount is not None else (po.final_amount or (quote.total_price if quote else None))
    if final_amount is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Siparişin tamamlanabilmesi için nihai tutar (final_amount) zorunludur.",
        )
    if final_amount < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nihai fatura/sipariş tutarı negatif olamaz.",
        )

    # Check for unresolved critical quality issues
    open_critical = [
        qi for qi in (po.quality_issues or [])
        if qi.severity == IssueSeverity.CRITICAL.value and getattr(qi, "status", QualityIssueStatus.OPEN.value) == QualityIssueStatus.OPEN.value
    ]
    if open_critical:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Siparişte {len(open_critical)} adet çözümlenmemiş kritik kalite sorunu bulunmaktadır. Siparişi tamamlamadan önce bu kayıtları çözümleyin veya kapatın.",
        )

    po.status = PurchaseOrderStatus.COMPLETED.value
    po.final_amount = final_amount

    if payload.completion_notes and payload.completion_notes.strip():
        c_notes = payload.completion_notes.strip()
        if po.delivery_notes:
            po.delivery_notes = f"{po.delivery_notes}\n[Tamamlama]: {c_notes}"
        else:
            po.delivery_notes = f"[Tamamlama]: {c_notes}"

    await _sync_supplier_history(db, po, quote)

    db.add(
        AuditEvent(
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            event_type="po_completed",
            entity_type="purchase_order",
            entity_id=po.id,
            payload={
                "po_number": po.po_number,
                "final_amount": str(final_amount) if final_amount is not None else None,
                "currency": quote.currency or "TRY",
            },
        )
    )

    await db.commit()
    await db.refresh(po)
    return _build_order_response(po, quote, rfq, is_manager_or_above=True)


@router.post(
    "/{po_id}/cancel",
    response_model=PurchaseOrderDetailResponse,
    summary="Cancel a Purchase Order with mandatory reason",
)
async def cancel_order(
    po_id: uuid.UUID,
    payload: POCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_above),
) -> PurchaseOrderDetailResponse:
    po, quote, rfq = await _get_order_or_404(po_id, db, current_user)

    if po.status == PurchaseOrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Satın Alma Siparişi zaten iptal edilmiş durumda.",
        )
    if po.status == PurchaseOrderStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tamamlanmış (completed) Satın Alma Siparişi iptal edilemez.",
        )

    po.status = PurchaseOrderStatus.CANCELLED.value
    po.cancellation_reason = payload.reason.strip()
    po.cancelled_at = datetime.now(timezone.utc)

    db.add(
        AuditEvent(
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            event_type="po_cancelled",
            entity_type="purchase_order",
            entity_id=po.id,
            payload={
                "po_number": po.po_number,
                "reason": payload.reason.strip(),
                "rfq_id": str(rfq.id),
            },
        )
    )

    await db.commit()
    await db.refresh(po)
    return _build_order_response(po, quote, rfq, is_manager_or_above=True)


@router.post(
    "/{po_id}/quality-issues",
    response_model=POQualityIssueResponse,
    summary="Log a quality issue or item rejection for a Purchase Order",
)
async def create_quality_issue(
    po_id: uuid.UUID,
    payload: POQualityIssueCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_above),
) -> POQualityIssueResponse:
    po, quote, rfq = await _get_order_or_404(po_id, db, current_user)

    if po.status == PurchaseOrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="İptal edilmiş sipariş için kalite kaydı girilemez.",
        )

    # Validate issue type
    valid_types = [t.value for t in IssueType]
    if payload.issue_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz kalite sorunu tipi '{payload.issue_type}'. Geçerli tipler: {', '.join(valid_types)}",
        )

    # Validate severity
    valid_severities = [s.value for s in IssueSeverity]
    if payload.severity not in valid_severities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz önem seviyesi '{payload.severity}'. Geçerli seviyeler: {', '.join(valid_severities)}",
        )

    issue = POQualityIssue(
        organization_id=current_user.organization_id,
        purchase_order_id=po.id,
        supplier_id=quote.supplier_id,
        reported_by_id=current_user.id,
        issue_type=payload.issue_type,
        severity=payload.severity,
        description=payload.description.strip(),
        rejection_count=payload.rejection_count,
    )
    db.add(issue)
    await db.flush()

    # Re-fetch issues to sync summary to SupplierHistory
    await db.refresh(po, ["quality_issues"])
    await _sync_supplier_history(db, po, quote)

    db.add(
        AuditEvent(
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            event_type="po_quality_issue_recorded",
            entity_type="purchase_order",
            entity_id=po.id,
            payload={
                "po_number": po.po_number,
                "issue_id": str(issue.id),
                "issue_type": issue.issue_type,
                "severity": issue.severity,
                "rejection_count": issue.rejection_count,
            },
        )
    )

    await db.commit()
    await db.refresh(issue)

    return POQualityIssueResponse(
        id=issue.id,
        organization_id=issue.organization_id,
        purchase_order_id=issue.purchase_order_id,
        supplier_id=issue.supplier_id,
        reported_by_id=issue.reported_by_id,
        reported_by_name=current_user.full_name,
        issue_type=issue.issue_type,
        severity=issue.severity,
        description=issue.description,
        rejection_count=issue.rejection_count,
        status=issue.status,
        resolution_notes=issue.resolution_notes,
        resolved_at=issue.resolved_at,
        created_at=issue.created_at,
    )


@router.patch(
    "/{po_id}/quality-issues/{issue_id}",
    response_model=POQualityIssueResponse,
    summary="Resolve or dismiss a quality issue",
)
async def update_quality_issue(
    po_id: uuid.UUID,
    issue_id: uuid.UUID,
    payload: POQualityIssueUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_above),
) -> POQualityIssueResponse:
    po, quote, rfq = await _get_order_or_404(po_id, db, current_user)

    valid_statuses = [s.value for s in QualityIssueStatus]
    if payload.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz durum '{payload.status}'. Geçerli durumlar: {', '.join(valid_statuses)}",
        )

    stmt = select(POQualityIssue).where(
        POQualityIssue.id == issue_id,
        POQualityIssue.purchase_order_id == po.id,
        POQualityIssue.organization_id == current_user.organization_id,
    )
    res = await db.execute(stmt)
    issue = res.scalar_one_or_none()
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kalite kaydı bulunamadı.",
        )

    issue.status = payload.status
    if payload.resolution_notes is not None:
        issue.resolution_notes = payload.resolution_notes.strip()
    if payload.status in (QualityIssueStatus.RESOLVED.value, QualityIssueStatus.DISMISSED.value):
        issue.resolved_at = datetime.now(timezone.utc)
    else:
        issue.resolved_at = None

    # Resync supplier history
    await db.refresh(po, ["quality_issues"])
    await _sync_supplier_history(db, po, quote)

    db.add(
        AuditEvent(
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            event_type="po_quality_issue_updated",
            entity_type="purchase_order",
            entity_id=po.id,
            payload={
                "po_number": po.po_number,
                "issue_id": str(issue.id),
                "new_status": issue.status,
                "resolution_notes": issue.resolution_notes,
            },
        )
    )

    await db.commit()
    await db.refresh(issue)

    return POQualityIssueResponse(
        id=issue.id,
        organization_id=issue.organization_id,
        purchase_order_id=issue.purchase_order_id,
        supplier_id=issue.supplier_id,
        reported_by_id=issue.reported_by_id,
        reported_by_name=issue.reported_by.full_name if issue.reported_by else current_user.full_name,
        issue_type=issue.issue_type,
        severity=issue.severity,
        description=issue.description,
        rejection_count=issue.rejection_count,
        status=issue.status,
        resolution_notes=issue.resolution_notes,
        resolved_at=issue.resolved_at,
        created_at=issue.created_at,
    )


@router.get(
    "/{po_id}/quality-issues",
    response_model=list[POQualityIssueResponse],
    summary="List all quality issues logged for a Purchase Order",
)
async def list_quality_issues(
    po_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> list[POQualityIssueResponse]:
    po, quote, rfq = await _get_order_or_404(po_id, db, current_user)
    return [
        POQualityIssueResponse(
            id=qi.id,
            organization_id=qi.organization_id,
            purchase_order_id=qi.purchase_order_id,
            supplier_id=qi.supplier_id,
            reported_by_id=qi.reported_by_id,
            reported_by_name=qi.reported_by.full_name if qi.reported_by else None,
            issue_type=qi.issue_type,
            severity=qi.severity,
            description=qi.description,
            rejection_count=int(qi.rejection_count),
            status=getattr(qi, "status", QualityIssueStatus.OPEN.value),
            resolution_notes=getattr(qi, "resolution_notes", None),
            resolved_at=getattr(qi, "resolved_at", None),
            created_at=qi.created_at,
        )
        for qi in (po.quality_issues or [])
    ]
