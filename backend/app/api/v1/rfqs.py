import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import (
    require_authenticated,
    require_employee_or_above,
    require_manager_or_above,
)
from app.db.session import get_db
from app.models.analysis import Analysis, Approval, ApprovalStatus
from app.models.order import PurchaseOrder
from app.models.quote import Quote
from app.models.rfq import RFQ, RFQItem, RFQStatus, QuoteDocument
from app.models.user import User

router = APIRouter(prefix="/api/v1/rfqs", tags=["rfqs"])

# Response Schemas

class RFQItemResponse(BaseModel):
    id: uuid.UUID
    line_number: int
    description: str
    quantity: float
    unit: str | None

    model_config = ConfigDict(from_attributes=True)

class RFQResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_id: uuid.UUID | None
    created_by_name: str | None = None
    title: str
    description: str | None
    required_quantity: int | None
    required_date: date | None
    budget: float | None = None
    max_delivery_days: int | None = None
    min_warranty_months: int | None = None
    payment_terms: str | None = None
    status: str
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime | None
    items: list[RFQItemResponse] = []
    quotes_count: int = 0
    can_delete: bool = True
    delete_block_reason: str | None = None
    has_po: bool = False

    model_config = ConfigDict(from_attributes=True)

class RFQItemCreate(BaseModel):
    description: str
    quantity: float
    unit: str | None = None

class RFQCreateRequest(BaseModel):
    title: str
    description: str | None = None
    required_quantity: int | None = None
    required_date: date | None = None
    budget: float | None = None
    max_delivery_days: int | None = None
    min_warranty_months: int | None = None
    payment_terms: str | None = None
    items: list[RFQItemCreate] = []

class RFQCancelRequest(BaseModel):
    reason: str
    cancel_pos: bool = True
    organization_id: Optional[uuid.UUID] = None

class RFQArchiveRequest(BaseModel):
    reason: Optional[str] = None
    organization_id: Optional[uuid.UUID] = None

class POCancelRequest(BaseModel):
    reason: str
    organization_id: Optional[uuid.UUID] = None


# ── Metadata & Safe Deletion Validation ────────────────────────────────────────

async def _compute_rfq_metadata(rfq: RFQ, db: AsyncSession) -> tuple[int, bool, bool, str | None]:
    """
    Computes quotes count, deletion eligibility, presence of Purchase Orders,
    and deletion blocking reason based on business rules.
    """
    quotes_count = len(rfq.quotes) if rfq.quotes else 0

    # 1. Any Purchase Orders created for quotes under this RFQ?
    po_res = await db.execute(
        select(PurchaseOrder.id)
        .join(PurchaseOrder.quote)
        .where(Quote.rfq_id == rfq.id)
        .limit(1)
    )
    has_po = po_res.scalar_one_or_none() is not None

    # 2. Is RFQ status marked as approved?
    is_approved_status = (rfq.status == RFQStatus.APPROVED.value)

    # 3. Any approved Human Approval records?
    approval_res = await db.execute(
        select(Approval.id)
        .join(Approval.analysis)
        .where(
            Analysis.rfq_id == rfq.id,
            Approval.status.in_([ApprovalStatus.APPROVED.value, ApprovalStatus.EXCEPTION_APPROVED.value])
        )
        .limit(1)
    )
    has_approved_approval = approval_res.scalar_one_or_none() is not None

    if has_po or is_approved_status or has_approved_approval:
        can_delete = False
        delete_block_reason = (
            "Onaylanmış veya Satın Alma Siparişi (PO) oluşturulmuş bir RFQ silinemez. "
            "Kayıt arşivlenmeli veya iş akışı iptal edilmelidir."
        )
    else:
        can_delete = True
        delete_block_reason = None

    return quotes_count, can_delete, has_po, delete_block_reason


class PaginatedRFQResponse(BaseModel):
    items: list[RFQResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


# Endpoints

@router.get(
    "",
    response_model=PaginatedRFQResponse,
    summary="List all RFQs with pagination",
    description="Fetch a paginated list of Request for Quotations with optional filters and search."
)
async def list_rfqs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page (default 20, supports 10, 20, 50)"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Alias for page_size"),
    status: Optional[str] = Query(None, description="Filter by RFQ status"),
    search: Optional[str] = Query(None, description="Search in title, description, or items"),
    is_archived: Optional[bool] = Query(None, description="Filter by archived status"),
    include_archived: bool = Query(False, description="Include archived RFQs in listing"),
    archived_only: bool = Query(False, description="Return only archived RFQs"),
    organization_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> PaginatedRFQResponse:
    import math
    from sqlalchemy import func, or_, cast, String
    from app.models.rfq import RFQItem

    effective_limit = page_size or limit or 20

    # Tenant isolation: strictly filter by the authenticated user's organization
    conditions = [RFQ.organization_id == current_user.organization_id]

    if status and status != "all":
        conditions.append(RFQ.status == status)

    if is_archived is not None:
        conditions.append(RFQ.is_archived == is_archived)
    elif archived_only:
        conditions.append(RFQ.is_archived == True)
    elif not include_archived:
        conditions.append(RFQ.is_archived == False)

    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append(
            or_(
                RFQ.title.ilike(term),
                RFQ.description.ilike(term),
                cast(RFQ.id, String).ilike(term),
                RFQ.items.any(RFQItem.description.ilike(term))
            )
        )

    # 1. Total Count Query (executed on SQL server)
    count_query = select(func.count(RFQ.id))
    if conditions:
        count_query = count_query.where(*conditions)
    total_count_res = await db.execute(count_query)
    total_count = total_count_res.scalar_one()

    # 2. Paginated Data Query with OFFSET and LIMIT
    offset_val = (page - 1) * effective_limit
    data_query = (
        select(RFQ)
        .options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.quotes),
        )
        .order_by(RFQ.created_at.desc())
    )
    if conditions:
        data_query = data_query.where(*conditions)
    data_query = data_query.offset(offset_val).limit(effective_limit)

    result = await db.execute(data_query)
    rfqs = result.scalars().all()
    
    response_items = []
    for rfq in rfqs:
        quotes_count, can_delete, has_po, delete_block_reason = await _compute_rfq_metadata(rfq, db)
        dto = RFQResponse.model_validate(rfq)
        dto.quotes_count = quotes_count
        dto.can_delete = can_delete
        dto.has_po = has_po
        dto.delete_block_reason = delete_block_reason
        if rfq.created_by:
            dto.created_by_name = rfq.created_by.full_name
        response_items.append(dto)

    total_pages = math.ceil(total_count / effective_limit) if total_count > 0 else 0
        
    return PaginatedRFQResponse(
        items=response_items,
        total_count=total_count,
        page=page,
        page_size=effective_limit,
        total_pages=total_pages
    )


@router.get(
    "/{rfq_id}",
    response_model=RFQResponse,
    summary="Get a specific RFQ",
    description="Fetch a single Request for Quotation by its UUID."
)
async def get_rfq(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> RFQResponse:
    result = await db.execute(
        select(RFQ)
        .where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
        .options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.quotes),
        )
    )
    rfq = result.scalars().first()
    
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} not found"
        )
        
    quotes_count, can_delete, has_po, delete_block_reason = await _compute_rfq_metadata(rfq, db)
    dto = RFQResponse.model_validate(rfq)
    dto.quotes_count = quotes_count
    dto.can_delete = can_delete
    dto.has_po = has_po
    dto.delete_block_reason = delete_block_reason
    if rfq.created_by:
        dto.created_by_name = rfq.created_by.full_name
        
    return dto


@router.delete(
    "/{rfq_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete an RFQ safely",
    description="Deletes an RFQ if it has not been approved and no PO has been issued."
)
async def delete_rfq(
    rfq_id: uuid.UUID,
    organization_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_above),
):
    result = await db.execute(
        select(RFQ)
        .where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
        .options(
            selectinload(RFQ.quotes),
            selectinload(RFQ.quote_documents),
            selectinload(RFQ.analyses)
        )
    )
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} bulunamadı",
        )

    # Business rule verification
    _, can_delete, has_po, block_reason = await _compute_rfq_metadata(rfq, db)
    if not can_delete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=block_reason,
        )

    # Remove physical quote document files from disk
    for doc in rfq.quote_documents:
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except OSError:
                pass

    # Delete RFQ (DB cascades to items, quotes, quote_documents, unapproved analyses)
    await db.delete(rfq)
    await db.commit()

    return {
        "status": "success",
        "message": f"RFQ '{rfq.title}' ve ilişkili teklifler başarıyla silindi",
        "id": str(rfq_id),
    }


class PurchaseOrderResponse(BaseModel):
    id: uuid.UUID
    po_number: str
    quote_id: uuid.UUID
    approval_id: uuid.UUID
    status: str
    email_sent: bool
    cancellation_reason: str | None = None
    cancelled_at: datetime | None = None
    expected_delivery_date: date | None = None
    actual_delivery_date: date | None = None
    delivered_at: datetime | None = None
    final_amount: Decimal | None = None
    delivery_notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

@router.post(
    "/{rfq_id}/cancel",
    response_model=RFQResponse,
    summary="Cancel an RFQ",
    description="Cancels an RFQ and optionally cancels linked active Purchase Orders with audit logging."
)
async def cancel_rfq(
    rfq_id: uuid.UUID,
    payload: RFQCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_above),
) -> RFQResponse:
    from app.models.order import PurchaseOrder
    from app.models.quote import Quote
    from app.models.audit import AuditEvent
    from datetime import timezone

    if not payload.reason or len(payload.reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="İptal gerekçesi en az 3 karakter olmalıdır.",
        )

    result = await db.execute(
        select(RFQ)
        .where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
        .options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.quotes),
        )
    )
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} bulunamadı",
        )

    if rfq.status == RFQStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RFQ zaten iptal edilmiş durumda.",
        )

    # Check for active POs linked to this RFQ's quotes
    po_query = await db.execute(
        select(PurchaseOrder)
        .join(PurchaseOrder.quote)
        .where(Quote.rfq_id == rfq.id)
    )
    all_pos = po_query.scalars().all()
    active_pos = [po for po in all_pos if po.status != "cancelled"]

    cancelled_po_numbers = []
    if active_pos:
        if not payload.cancel_pos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RFQ'ya bağlı aktif Satın Alma Siparişleri (PO) bulunmaktadır. RFQ'yu iptal etmek için önce PO'ları iptal edin veya cancel_pos parametresini onaylayın.",
            )
        now_utc = datetime.now(timezone.utc)
        for po in active_pos:
            po.status = "cancelled"
            po.cancellation_reason = f"RFQ iptali nedeniyle: {payload.reason.strip()}"
            po.cancelled_at = now_utc
            cancelled_po_numbers.append(po.po_number)
            db.add(
                AuditEvent(
                    organization_id=rfq.organization_id,
                    actor_id=current_user.id,
                    event_type="po_cancelled",
                    entity_type="purchase_order",
                    entity_id=po.id,
                    payload={
                        "po_number": po.po_number,
                        "reason": f"RFQ iptali nedeniyle: {payload.reason.strip()}",
                        "rfq_id": str(rfq.id),
                    }
                )
            )

    rfq.status = RFQStatus.CANCELLED.value

    # Audit log for RFQ cancellation
    db.add(
        AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=current_user.id,
            event_type="rfq_cancelled",
            entity_type="rfq",
            entity_id=rfq.id,
            payload={
                "reason": payload.reason.strip(),
                "cancelled_pos": cancelled_po_numbers,
            }
        )
    )

    await db.commit()
    refreshed_result = await db.execute(
        select(RFQ)
        .where(RFQ.id == rfq_id)
        .options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.quotes),
        )
    )
    rfq = refreshed_result.scalar_one()

    quotes_count, can_delete, has_po, delete_block_reason = await _compute_rfq_metadata(rfq, db)
    dto = RFQResponse.model_validate(rfq)
    dto.quotes_count = quotes_count
    dto.can_delete = can_delete
    dto.has_po = has_po
    dto.delete_block_reason = delete_block_reason
    if rfq.created_by:
        dto.created_by_name = rfq.created_by.full_name
    return dto


@router.post(
    "/{rfq_id}/archive",
    response_model=RFQResponse,
    summary="Archive an RFQ",
    description="Archives an RFQ to remove it from the active list without deleting or changing business status."
)
async def archive_rfq(
    rfq_id: uuid.UUID,
    payload: Optional[RFQArchiveRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee_or_above),
) -> RFQResponse:
    from app.models.audit import AuditEvent

    result = await db.execute(
        select(RFQ)
        .where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
        .options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.quotes),
        )
    )
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} bulunamadı",
        )

    if rfq.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RFQ zaten arşivlenmiş durumda.",
        )

    rfq.is_archived = True

    db.add(
        AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=current_user.id,
            event_type="rfq_archived",
            entity_type="rfq",
            entity_id=rfq.id,
            payload={
                "reason": payload.reason if payload else None,
            }
        )
    )

    await db.commit()
    refreshed_result = await db.execute(
        select(RFQ)
        .where(RFQ.id == rfq_id)
        .options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.quotes),
        )
    )
    rfq = refreshed_result.scalar_one()

    quotes_count, can_delete, has_po, delete_block_reason = await _compute_rfq_metadata(rfq, db)
    dto = RFQResponse.model_validate(rfq)
    dto.quotes_count = quotes_count
    dto.can_delete = can_delete
    dto.has_po = has_po
    dto.delete_block_reason = delete_block_reason
    if rfq.created_by:
        dto.created_by_name = rfq.created_by.full_name
    return dto


@router.post(
    "/{rfq_id}/unarchive",
    response_model=RFQResponse,
    summary="Unarchive an RFQ",
    description="Restores an archived RFQ back to the active list."
)
async def unarchive_rfq(
    rfq_id: uuid.UUID,
    payload: Optional[RFQArchiveRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee_or_above),
) -> RFQResponse:
    from app.models.audit import AuditEvent

    result = await db.execute(
        select(RFQ)
        .where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
        .options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.quotes),
        )
    )
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} bulunamadı",
        )

    if not rfq.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RFQ arşivlenmiş değil.",
        )

    rfq.is_archived = False

    db.add(
        AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=current_user.id,
            event_type="rfq_unarchived",
            entity_type="rfq",
            entity_id=rfq.id,
            payload={}
        )
    )

    await db.commit()
    refreshed_result = await db.execute(
        select(RFQ)
        .where(RFQ.id == rfq_id)
        .options(
            selectinload(RFQ.items),
            selectinload(RFQ.created_by),
            selectinload(RFQ.quotes),
        )
    )
    rfq = refreshed_result.scalar_one()

    quotes_count, can_delete, has_po, delete_block_reason = await _compute_rfq_metadata(rfq, db)
    dto = RFQResponse.model_validate(rfq)
    dto.quotes_count = quotes_count
    dto.can_delete = can_delete
    dto.has_po = has_po
    dto.delete_block_reason = delete_block_reason
    if rfq.created_by:
        dto.created_by_name = rfq.created_by.full_name
    return dto


@router.post(
    "/{rfq_id}/purchase-orders/{po_id}/cancel",
    response_model=PurchaseOrderResponse,
    summary="Cancel a Purchase Order under an RFQ",
    description="Cancels an issued Purchase Order with mandatory reason, recording audit event without deleting financial record."
)
async def cancel_rfq_purchase_order(
    rfq_id: uuid.UUID,
    po_id: uuid.UUID,
    payload: POCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_above),
) -> PurchaseOrderResponse:
    from app.models.order import PurchaseOrder
    from app.models.quote import Quote
    from app.models.audit import AuditEvent
    from datetime import timezone

    if not payload.reason or len(payload.reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="İptal gerekçesi en az 3 karakter olmalıdır.",
        )

    rfq_res = await db.execute(
        select(RFQ).where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
    )
    rfq = rfq_res.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} bulunamadı",
        )

    po_query = await db.execute(
        select(PurchaseOrder)
        .join(PurchaseOrder.quote)
        .where(
            PurchaseOrder.id == po_id,
            Quote.rfq_id == rfq_id
        )
    )
    po = po_query.scalar_one_or_none()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Satın Alma Siparişi ({po_id}) bu RFQ altında bulunamadı",
        )

    if po.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Satın Alma Siparişi zaten iptal edilmiş durumda.",
        )

    po.status = "cancelled"
    po.cancellation_reason = payload.reason.strip()
    po.cancelled_at = datetime.now(timezone.utc)

    db.add(
        AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=current_user.id,
            event_type="po_cancelled",
            entity_type="purchase_order",
            entity_id=po.id,
            payload={
                "po_number": po.po_number,
                "reason": payload.reason.strip(),
                "rfq_id": str(rfq.id),
            }
        )
    )

    await db.commit()
    await db.refresh(po)
    return PurchaseOrderResponse.model_validate(po)


@router.post(
    "/purchase-orders/{po_id}/cancel",
    response_model=PurchaseOrderResponse,
    summary="Cancel a Purchase Order directly",
)
async def cancel_purchase_order_direct(
    po_id: uuid.UUID,
    payload: POCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_above),
) -> PurchaseOrderResponse:
    from app.models.order import PurchaseOrder
    from app.models.quote import Quote
    from app.models.audit import AuditEvent
    from datetime import timezone

    if not payload.reason or len(payload.reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="İptal gerekçesi en az 3 karakter olmalıdır.",
        )

    po_query = await db.execute(
        select(PurchaseOrder)
        .join(PurchaseOrder.quote)
        .join(Quote.rfq)
        .options(selectinload(PurchaseOrder.quote).selectinload(Quote.rfq))
        .where(
            PurchaseOrder.id == po_id,
            RFQ.organization_id == current_user.organization_id,
        )
    )
    po = po_query.scalar_one_or_none()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Satın Alma Siparişi ({po_id}) bulunamadı",
        )

    rfq = po.quote.rfq if po.quote else None
    org_id = current_user.organization_id

    if po.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Satın Alma Siparişi zaten iptal edilmiş durumda.",
        )

    po.status = "cancelled"
    po.cancellation_reason = payload.reason.strip()
    po.cancelled_at = datetime.now(timezone.utc)

    db.add(
        AuditEvent(
            organization_id=org_id,
            actor_id=current_user.id,
            event_type="po_cancelled",
            entity_type="purchase_order",
            entity_id=po.id,
            payload={
                "po_number": po.po_number,
                "reason": payload.reason.strip(),
                "rfq_id": str(rfq.id) if rfq else None,
            }
        )
    )

    await db.commit()
    await db.refresh(po)
    return PurchaseOrderResponse.model_validate(po)

@router.get(
    "/{rfq_id}/purchase-orders",
    response_model=list[PurchaseOrderResponse],
    summary="Get POs for an RFQ",
)
async def get_rfq_purchase_orders(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> list[PurchaseOrderResponse]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.order import PurchaseOrder
    from app.models.quote import Quote

    rfq_check = await db.execute(
        select(RFQ.id).where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
    )
    if not rfq_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} not found"
        )
    
    result = await db.execute(
        select(PurchaseOrder)
        .join(PurchaseOrder.quote)
        .where(Quote.rfq_id == rfq_id)
    )
    pos = result.scalars().all()
    return [PurchaseOrderResponse.model_validate(po) for po in pos]

@router.post(
    "",
    response_model=RFQResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new RFQ",
)
async def create_rfq(
    request: RFQCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee_or_above),
) -> RFQResponse:
    rfq = RFQ(
        organization_id=current_user.organization_id,
        created_by_id=current_user.id,
        title=request.title,
        description=request.description,
        required_quantity=request.required_quantity,
        required_date=request.required_date,
        budget=request.budget,
        max_delivery_days=request.max_delivery_days,
        min_warranty_months=request.min_warranty_months,
        payment_terms=request.payment_terms,
        status="draft"
    )
    db.add(rfq)
    await db.flush()

    from app.models.rfq import RFQItem
    for i, item in enumerate(request.items, start=1):
        rfq_item = RFQItem(
            rfq_id=rfq.id,
            line_number=i,
            description=item.description,
            quantity=item.quantity,
            unit=item.unit
        )
        db.add(rfq_item)
    
    await db.commit()
    await db.refresh(rfq, ["items"])
    return RFQResponse.model_validate(rfq)

from app.api.v1.suppliers import SupplierResponse

@router.get(
    "/suppliers/list",
    response_model=list[SupplierResponse],
    summary="List all Suppliers (Alias)",
)
async def list_suppliers_alias(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> list[SupplierResponse]:
    from app.models.supplier import Supplier

    result = await db.execute(
        select(Supplier)
        .where(
            Supplier.organization_id == current_user.organization_id,
            Supplier.is_active == True,
        )
        .order_by(Supplier.name.asc())
    )
    suppliers = result.scalars().all()
    return [SupplierResponse.model_validate(s) for s in suppliers]
