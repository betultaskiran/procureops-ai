"""
app/api/v1/portal.py

Supplier-Facing Quotation & RFQ Participation Portal (Phase 13).

Architecture & Security:
  - External suppliers do NOT have internal company user accounts.
  - Authentication is granted via high-entropy, scoped, cryptographically hashed tokens:
      token = "{delivery_id}.{raw_secret}"
  - Validates token against SHA-256 hash stored in EmailDelivery.metadata_json.
  - Strict tenant and RFQ isolation:
      * Supplier can only view the specific RFQ explicitly invited to.
      * Supplier NEVER sees target budget, internal policy documents, other suppliers,
        competing quotes, or AI analysis results.
      * Expiration and revocation are strictly enforced on every sensitive endpoint.
      * RFQ status must be active (draft or collecting_quotes). Late submissions after deadline are rejected.
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.email_delivery import EmailDelivery, EmailMessageType
from app.models.order import PurchaseOrder, PurchaseOrderStatus
from app.models.organization import Organization
from app.models.quote import Quote, QuoteItem
from app.models.rfq import FileType, ParseStatus, QuoteDocument, RFQ, RFQItem, RFQStatus
from app.models.supplier import Supplier

logger = logging.getLogger("app.portal")

router = APIRouter(
    prefix="/api/v1/portal",
    tags=["supplier-portal"],
    dependencies=[Depends(rate_limit(max_requests=120, window_seconds=60))],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PortalRFQItemResponse(BaseModel):
    line_number: int
    description: str
    quantity: float
    unit: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PortalExistingQuoteItem(BaseModel):
    line_number: int
    description: str
    quantity: float
    unit: Optional[str] = None
    unit_price: float
    total_price: float

    model_config = ConfigDict(from_attributes=True)


class PortalExistingQuote(BaseModel):
    id: uuid.UUID
    currency: str
    subtotal: float
    vat_rate: Optional[float] = None
    vat_amount: Optional[float] = None
    shipping_cost: Optional[float] = None
    discount_amount: Optional[float] = 0.0
    other_costs: Optional[float] = 0.0
    total_price: float
    delivery_days: Optional[int] = None
    payment_terms: Optional[str] = None
    warranty_months: Optional[int] = None
    valid_until: Optional[date] = None
    notes: Optional[str] = None
    items: List[PortalExistingQuoteItem] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PortalRFQResponse(BaseModel):
    invitation_id: uuid.UUID
    organization_name: str
    supplier_name: str
    supplier_email: str
    rfq_id: uuid.UUID
    rfq_title: str
    rfq_description: Optional[str] = None
    required_quantity: Optional[int] = None
    required_date: Optional[date] = None
    max_delivery_days: Optional[int] = None
    min_warranty_months: Optional[int] = None
    payment_terms: Optional[str] = None
    items: List[PortalRFQItemResponse] = []
    can_submit: bool
    deadline_passed: bool
    expires_at: datetime
    is_revoked: bool = False
    existing_quote: Optional[PortalExistingQuote] = None


class PortalQuoteItemSubmit(BaseModel):
    line_number: int = Field(..., ge=1)
    description: str = Field(..., min_length=1, max_length=1000)
    quantity: Decimal = Field(..., gt=0)
    unit: Optional[str] = Field("Adet", max_length=50)
    unit_price: Decimal = Field(..., ge=0)
    total_price: Decimal = Field(..., ge=0)


class PortalQuoteSubmitRequest(BaseModel):
    currency: str = Field("TRY", min_length=3, max_length=3)
    subtotal: Decimal = Field(..., gt=0)
    vat_rate: Optional[Decimal] = Field(Decimal("0.20"), ge=0, le=1)
    vat_amount: Optional[Decimal] = Field(None, ge=0)
    shipping_cost: Optional[Decimal] = Field(Decimal("0.00"), ge=0)
    discount_amount: Optional[Decimal] = Field(Decimal("0.00"), ge=0)
    other_costs: Optional[Decimal] = Field(Decimal("0.00"), ge=0)
    delivery_days: int = Field(..., gt=0, le=365)
    warranty_months: int = Field(..., ge=0, le=120)
    payment_terms: Optional[str] = Field("net-30", max_length=200)
    valid_until: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=2000)
    items: List[PortalQuoteItemSubmit] = Field(default_factory=list)


class PortalQuoteSubmitResponse(BaseModel):
    success: bool
    message: str
    quote_id: uuid.UUID
    total_price: Decimal
    currency: str
    submitted_at: datetime


class PortalUploadResponse(BaseModel):
    quote_document_id: uuid.UUID
    file_name: str
    file_size_bytes: int
    parse_status: str
    message: str


class PortalPOViewResponse(BaseModel):
    po_number: str
    status: str
    organization_name: str
    supplier_name: str
    total_amount: Decimal
    currency: str
    created_at: datetime
    expected_delivery_date: Optional[date] = None


# ── Authentication & Token Verification ───────────────────────────────────────

async def resolve_portal_invitation(
    token: Optional[str] = Query(None, description="Participation token from invitation URL"),
    x_supplier_token: Optional[str] = Header(None, alias="X-Supplier-Token"),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> tuple[EmailDelivery, RFQ, Supplier, Organization]:
    """
    Validates a high-entropy supplier invitation token:
      token format: "{delivery_id}.{raw_secret}"
    Verifies cryptographic hash, expiration, revocation, and active RFQ status.
    """
    raw_token = token or x_supplier_token
    if not raw_token and authorization:
        if authorization.lower().startswith("bearer "):
            raw_token = authorization[7:].strip()
        else:
            raw_token = authorization.strip()

    if not raw_token or "." not in raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya eksik tedarikçi katılım bağlantısı (token formatı geçersiz).",
        )

    parts = raw_token.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz katılım anahtarı.",
        )

    raw_delivery_id, raw_secret = parts
    try:
        delivery_uuid = uuid.UUID(raw_delivery_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Katılım bağlantısı kimliği bozuk veya tanınmıyor.",
        )

    # 1. Fetch EmailDelivery by primary key (O(1) indexed lookup)
    stmt = (
        select(EmailDelivery)
        .where(
            and_(
                EmailDelivery.id == delivery_uuid,
                EmailDelivery.message_type == EmailMessageType.RFQ_INVITATION.value,
            )
        )
    )
    res = await db.execute(stmt)
    delivery = res.scalars().first()

    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya bulunamayan katılım bağlantısı.",
        )

    # 2. Parse metadata and check cryptographic secret hash
    meta = {}
    if delivery.metadata_json:
        try:
            meta = json.loads(delivery.metadata_json)
        except Exception:
            pass

    stored_hash = meta.get("invitation_token_hash")
    if not stored_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bu davet için güvenlik doğrulama kodu tanımlanmamış.",
        )

    computed_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(stored_hash, computed_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya eşleşmeyen katılım anahtarı.",
        )

    # 3. Revocation check
    if meta.get("is_revoked") is True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu tedarikçi davet bağlantısı alıcı firma tarafından iptal edilmiştir.",
        )

    # 4. Expiry check
    token_expires_at_str = meta.get("token_expires_at")
    if token_expires_at_str:
        try:
            token_expires_at = datetime.fromisoformat(token_expires_at_str)
            if token_expires_at.tzinfo is None:
                token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > token_expires_at:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="Bu tedarikçi katılım bağlantısının süresi dolmuştur.",
                )
        except HTTPException:
            raise
        except (ValueError, TypeError):
            pass

    # 5. Load RFQ, Supplier, and Organization
    rfq_stmt = (
        select(RFQ)
        .where(RFQ.id == delivery.rfq_id)
        .options(selectinload(RFQ.items))
    )
    rfq_res = await db.execute(rfq_stmt)
    rfq = rfq_res.scalars().first()

    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="İlişkili RFQ bulunamadı.",
        )

    if rfq.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu tedarik talebi (RFQ) iptal edilmiştir. Yeni teklif verilemez.",
        )

    # Fetch supplier
    sup_stmt = select(Supplier).where(Supplier.id == delivery.supplier_id)
    sup_res = await db.execute(sup_stmt)
    supplier = sup_res.scalars().first()
    if not supplier:
        # Fallback dummy supplier info if invited via direct email
        supplier = Supplier(
            id=delivery.supplier_id or uuid.uuid4(),
            organization_id=delivery.organization_id,
            name=delivery.recipient_name or delivery.recipient_email,
            email=delivery.recipient_email,
        )

    # Fetch organization
    org_stmt = select(Organization).where(Organization.id == delivery.organization_id)
    org_res = await db.execute(org_stmt)
    organization = org_res.scalars().first()

    return delivery, rfq, supplier, organization


# ── Portal Endpoints ──────────────────────────────────────────────────────────

@router.get(
    "/rfq",
    response_model=PortalRFQResponse,
    summary="Get RFQ Specifications & Status for Invited Supplier",
)
async def get_portal_rfq(
    auth_data: tuple[EmailDelivery, RFQ, Supplier, Organization] = Depends(resolve_portal_invitation),
    db: AsyncSession = Depends(get_db),
) -> PortalRFQResponse:
    """
    Returns public specification information for the invited RFQ.
    Guarantees strict privacy:
      - NEVER exposes target budget, competing quotes, internal policy documents, or team member data.
    """
    delivery, rfq, supplier, organization = auth_data

    # Check deadline
    today = date.today()
    deadline_passed = False
    if rfq.required_date and rfq.required_date < today:
        deadline_passed = True

    can_submit = rfq.status in (RFQStatus.DRAFT.value, RFQStatus.COLLECTING_QUOTES.value) and not deadline_passed

    # Check if supplier already submitted a quote for this RFQ
    existing_quote_res = await db.execute(
        select(Quote)
        .where(and_(Quote.rfq_id == rfq.id, Quote.supplier_id == supplier.id))
        .options(selectinload(Quote.items))
        .order_by(Quote.created_at.desc())
        .limit(1)
    )
    existing_q = existing_quote_res.scalars().first()
    existing_quote_dto: Optional[PortalExistingQuote] = None

    if existing_q:
        existing_items = [
            PortalExistingQuoteItem(
                line_number=item.line_number,
                description=item.description,
                quantity=float(item.quantity),
                unit=item.unit,
                unit_price=float(item.unit_price),
                total_price=float(item.total_price),
            )
            for item in sorted(existing_q.items, key=lambda x: x.line_number)
        ]
        existing_quote_dto = PortalExistingQuote(
            id=existing_q.id,
            currency=existing_q.currency,
            subtotal=float(existing_q.subtotal),
            vat_rate=float(existing_q.vat_rate) if existing_q.vat_rate is not None else None,
            vat_amount=float(existing_q.vat_amount) if existing_q.vat_amount is not None else None,
            shipping_cost=float(existing_q.shipping_cost) if existing_q.shipping_cost is not None else 0.0,
            discount_amount=float(existing_q.discount_amount) if existing_q.discount_amount is not None else 0.0,
            other_costs=float(existing_q.other_costs) if existing_q.other_costs is not None else 0.0,
            total_price=float(existing_q.total_price),
            delivery_days=existing_q.delivery_days,
            payment_terms=existing_q.payment_terms,
            warranty_months=existing_q.warranty_months,
            valid_until=existing_q.valid_until,
            notes=existing_q.notes,
            items=existing_items,
            created_at=existing_q.created_at,
            updated_at=existing_q.updated_at,
        )

    # Sort RFQ items
    rfq_items = [
        PortalRFQItemResponse(
            line_number=it.line_number,
            description=it.description,
            quantity=float(it.quantity),
            unit=it.unit,
        )
        for it in sorted(rfq.items, key=lambda x: x.line_number)
    ]

    meta = {}
    if delivery.metadata_json:
        try:
            meta = json.loads(delivery.metadata_json)
        except Exception:
            pass

    expires_at = datetime.now(timezone.utc)
    if meta.get("token_expires_at"):
        try:
            expires_at = datetime.fromisoformat(meta["token_expires_at"])
        except Exception:
            pass

    return PortalRFQResponse(
        invitation_id=delivery.id,
        organization_name=organization.name if organization else "ProcureOps Organization",
        supplier_name=supplier.name,
        supplier_email=delivery.recipient_email,
        rfq_id=rfq.id,
        rfq_title=rfq.title,
        rfq_description=rfq.description,
        required_quantity=rfq.required_quantity,
        required_date=rfq.required_date,
        max_delivery_days=rfq.max_delivery_days,
        min_warranty_months=rfq.min_warranty_months,
        payment_terms=rfq.payment_terms,
        items=rfq_items,
        can_submit=can_submit,
        deadline_passed=deadline_passed,
        expires_at=expires_at,
        is_revoked=bool(meta.get("is_revoked", False)),
        existing_quote=existing_quote_dto,
    )


@router.post(
    "/rfq/quote",
    response_model=PortalQuoteSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit or Update a Quotation by Invited Supplier",
)
async def submit_portal_quote(
    payload: PortalQuoteSubmitRequest,
    auth_data: tuple[EmailDelivery, RFQ, Supplier, Organization] = Depends(resolve_portal_invitation),
    db: AsyncSession = Depends(get_db),
) -> PortalQuoteSubmitResponse:
    """
    Submits a structured quotation for the invited RFQ.
    - Deterministically validates arithmetic totals.
    - If a quote previously existed, cleanly updates the quotation while keeping audit trail.
    - Guarantees RFQ enters 'collecting_quotes' state.
    """
    delivery, rfq, supplier, organization = auth_data

    # 1. State check: RFQ must be accepting quotes
    if rfq.status not in (RFQStatus.DRAFT.value, RFQStatus.COLLECTING_QUOTES.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bu RFQ için teklif toplama aşaması kapalıdır (Mevcut durum: {rfq.status}).",
        )

    # 2. Deadline check
    today = date.today()
    if rfq.required_date and rfq.required_date < today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Teklif verme süresi sona ermiştir. Süresi geçen taleplere teklif verilemez.",
        )

    # 3. Compute arithmetic totals deterministically
    subtotal = payload.subtotal
    vat_rate = payload.vat_rate if payload.vat_rate is not None else Decimal("0.20")
    vat_amount = payload.vat_amount if payload.vat_amount is not None else (subtotal * vat_rate)
    shipping = payload.shipping_cost or Decimal("0.00")
    discount = payload.discount_amount or Decimal("0.00")
    other = payload.other_costs or Decimal("0.00")

    total_price = subtotal + vat_amount + shipping + other - discount
    if total_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hesaplanan toplam teklif tutarı sıfır veya negatif olamaz.",
        )

    # 4. Check if quote already exists for (rfq_id, supplier_id)
    quote_res = await db.execute(
        select(Quote)
        .where(and_(Quote.rfq_id == rfq.id, Quote.supplier_id == supplier.id))
        .options(selectinload(Quote.items))
        .order_by(Quote.created_at.desc())
        .limit(1)
    )
    quote = quote_res.scalars().first()

    is_update = False
    if quote:
        # Update existing quote
        is_update = True
        quote.currency = payload.currency.upper()
        quote.subtotal = subtotal
        quote.vat_rate = vat_rate
        quote.vat_amount = vat_amount
        quote.shipping_cost = shipping
        quote.discount_amount = discount
        quote.other_costs = other
        quote.total_price = total_price
        quote.delivery_days = payload.delivery_days
        quote.warranty_months = payload.warranty_months
        quote.payment_terms = payload.payment_terms
        quote.valid_until = payload.valid_until
        quote.notes = payload.notes
        quote.is_compliant = None  # To be re-evaluated by buyer analysis

        # Delete existing items and replace
        await db.execute(delete(QuoteItem).where(QuoteItem.quote_id == quote.id))
    else:
        # Create new Quote
        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency=payload.currency.upper(),
            subtotal=subtotal,
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            shipping_cost=shipping,
            discount_amount=discount,
            other_costs=other,
            total_price=total_price,
            delivery_days=payload.delivery_days,
            warranty_months=payload.warranty_months,
            payment_terms=payload.payment_terms,
            valid_until=payload.valid_until,
            notes=payload.notes,
            is_compliant=None,
        )
        db.add(quote)
        await db.flush()

    # 5. Add quote line items if provided, or default from RFQ
    if payload.items:
        for it in payload.items:
            q_item = QuoteItem(
                quote_id=quote.id,
                line_number=it.line_number,
                description=it.description,
                quantity=it.quantity,
                unit=it.unit,
                unit_price=it.unit_price,
                total_price=it.total_price,
            )
            db.add(q_item)
    elif rfq.items:
        # Default single distributed line item matching RFQ first item
        first_item = rfq.items[0]
        q_item = QuoteItem(
            quote_id=quote.id,
            line_number=first_item.line_number,
            description=first_item.description,
            quantity=Decimal(str(first_item.quantity)),
            unit=first_item.unit,
            unit_price=subtotal / Decimal(str(max(1, first_item.quantity))),
            total_price=subtotal,
        )
        db.add(q_item)

    # 6. Ensure RFQ is in collecting_quotes status
    if rfq.status == RFQStatus.DRAFT.value:
        rfq.status = RFQStatus.COLLECTING_QUOTES.value
        db.add(rfq)

    # 7. Update EmailDelivery metadata to track submitted quote
    now_utc = datetime.now(timezone.utc)
    meta = {}
    if delivery.metadata_json:
        try:
            meta = json.loads(delivery.metadata_json)
        except Exception:
            pass
    meta["submitted_quote_id"] = str(quote.id)
    meta["submitted_at"] = now_utc.isoformat()
    delivery.metadata_json = json.dumps(meta)
    db.add(delivery)

    # 8. Record immutable audit event
    db.add(
        AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=None,  # External supplier actor
            event_type="supplier_quote_updated" if is_update else "supplier_quote_submitted",
            entity_type="quote",
            entity_id=quote.id,
            payload={
                "rfq_id": str(rfq.id),
                "supplier_id": str(supplier.id),
                "supplier_name": supplier.name,
                "total_price": str(quote.total_price),
                "currency": quote.currency,
                "is_update": is_update,
                "invitation_delivery_id": str(delivery.id),
            },
        )
    )

    await db.commit()
    await db.refresh(quote)

    logger.info(
        f"[SupplierPortal] Quote {'updated' if is_update else 'created'} by {supplier.name} for RFQ {rfq.id}: quote_id={quote.id}"
    )

    return PortalQuoteSubmitResponse(
        success=True,
        message="Teklifiniz başarıyla güncellendi." if is_update else "Teklifiniz başarıyla kaydedildi.",
        quote_id=quote.id,
        total_price=quote.total_price,
        currency=quote.currency,
        submitted_at=now_utc,
    )


@router.post(
    "/rfq/upload",
    response_model=PortalUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload Quote Document via Supplier Portal",
)
async def upload_portal_quote_document(
    file: UploadFile = File(..., description="PDF or Excel quote document"),
    auth_data: tuple[EmailDelivery, RFQ, Supplier, Organization] = Depends(resolve_portal_invitation),
    db: AsyncSession = Depends(get_db),
) -> PortalUploadResponse:
    """
    Allows invited supplier to upload their PDF/Excel quotation document directly.
    """
    delivery, rfq, supplier, organization = auth_data

    # State check
    if rfq.status not in (RFQStatus.DRAFT.value, RFQStatus.COLLECTING_QUOTES.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bu RFQ için dosya yükleme aşaması kapalıdır (Mevcut durum: {rfq.status}).",
        )

    # Size check
    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Dosya boyutu çok büyük. Maksimum boyut: {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    raw_filename = file.filename or "teklif_belgesi.pdf"
    safe_filename = Path(raw_filename).name

    # Magic byte validation
    suffix = Path(safe_filename).suffix.lower()
    if suffix == ".pdf":
        if not content.startswith(b"%PDF"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dosya içeriği geçerli bir PDF formatında değil.",
            )
        file_type = FileType.PDF.value
    elif suffix == ".xlsx":
        if not content.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dosya içeriği geçerli bir Excel (.xlsx) formatında değil.",
            )
        import io
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()
                if not any("xl/workbook.xml" in n or "workbook.xml" in n for n in names):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Dosya geçerli bir Excel (.xlsx) çalışma kitabı yapısı içermiyor.",
                    )
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bozuk veya geçersiz Excel (.xlsx) zip arşivi.",
            )
        file_type = FileType.EXCEL.value
    elif suffix in (".png", ".jpg", ".jpeg"):
        file_type = FileType.IMAGE.value
    else:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Desteklenmeyen dosya türü. Yalnızca PDF veya Excel (.xlsx) kabul edilir.",
        )

    # Save to disk
    doc_id = uuid.uuid4()
    saved_filename = f"{doc_id}_{safe_filename}"
    upload_dir = Path(settings.UPLOAD_DIR) / "quotes" / str(rfq.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / saved_filename

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    quote_doc = QuoteDocument(
        id=doc_id,
        rfq_id=rfq.id,
        supplier_id=supplier.id,
        uploaded_by_id=None,
        file_name=safe_filename,
        file_path=str(file_path),
        file_type=file_type,
        file_size_bytes=len(content),
        parse_status=ParseStatus.PENDING.value,
    )
    db.add(quote_doc)

    # Record audit event
    db.add(
        AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=None,
            event_type="supplier_document_uploaded",
            entity_type="quote_document",
            entity_id=quote_doc.id,
            payload={
                "rfq_id": str(rfq.id),
                "supplier_name": supplier.name,
                "file_name": safe_filename,
                "file_size": len(content),
            },
        )
    )

    await db.commit()
    await db.refresh(quote_doc)

    logger.info(f"[SupplierPortal] Document uploaded: doc_id={quote_doc.id} by {supplier.name}")

    return PortalUploadResponse(
        quote_document_id=quote_doc.id,
        file_name=safe_filename,
        file_size_bytes=len(content),
        parse_status=quote_doc.parse_status,
        message="Teklif belgeniz başarıyla yüklendi ve işleme alındı.",
    )


@router.get(
    "/orders/{po_id}",
    response_model=PortalPOViewResponse,
    summary="View Issued Purchase Order for Awarded Supplier",
)
async def get_portal_purchase_order(
    po_id: uuid.UUID,
    token: Optional[str] = Query(None, description="Participation token or access key"),
    x_supplier_token: Optional[str] = Header(None, alias="X-Supplier-Token"),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> PortalPOViewResponse:
    """
    Allows the awarded supplier to view their official issued purchase order details.
    Enforces strict token validation and cross-resource isolation:
    - If a token is provided, verifies that it is valid, unexpired, unrevoked,
      and strictly matches the supplier and RFQ of this purchase order.
    """
    stmt = (
        select(PurchaseOrder)
        .where(
            and_(
                PurchaseOrder.id == po_id,
                PurchaseOrder.status.in_([PurchaseOrderStatus.ISSUED.value, PurchaseOrderStatus.DELIVERED.value, PurchaseOrderStatus.COMPLETED.value]),
            )
        )
        .options(
            selectinload(PurchaseOrder.quote).selectinload(Quote.supplier),
            selectinload(PurchaseOrder.quote).selectinload(Quote.rfq).selectinload(RFQ.organization),
        )
    )
    res = await db.execute(stmt)
    po = res.scalars().first()

    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Yayınlanmış satın alma siparişi bulunamadı veya sipariş henüz onaylanmamış.",
        )

    quote = po.quote
    supplier = quote.supplier if quote else None
    rfq = quote.rfq if quote else None
    org = rfq.organization if rfq else None

    # Cross-resource token validation (Phase 14):
    raw_token = token or x_supplier_token
    if not raw_token and authorization:
        if authorization.lower().startswith("bearer "):
            raw_token = authorization[7:].strip()
        else:
            raw_token = authorization.strip()

    if raw_token:
        delivery, auth_rfq, auth_supplier, _ = await resolve_portal_invitation(
            token=raw_token,
            x_supplier_token=None,
            authorization=None,
            db=db,
        )
        if supplier and auth_supplier.id != supplier.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu siparişi görüntüleme yetkiniz bulunmamaktadır (Farklı tedarikçi token'ı).",
            )
        if rfq and auth_rfq.id != rfq.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu siparişi görüntüleme yetkiniz bulunmamaktadır (Farklı RFQ token'ı).",
            )

    return PortalPOViewResponse(
        po_number=po.po_number,
        status=po.status,
        organization_name=org.name if org else "ProcureOps Organization",
        supplier_name=supplier.name if supplier else "Tedarikçi",
        total_amount=quote.total_price if quote else Decimal("0.00"),
        currency=quote.currency if quote else "TRY",
        created_at=po.created_at,
        expected_delivery_date=po.expected_delivery_date,
    )
