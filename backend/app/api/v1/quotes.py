"""
app/api/v1/quotes.py

Quote yükleme ve sorgulama endpoint'leri.

ENDPOINT'LER:
  POST /api/v1/rfqs/{rfq_id}/quote-documents
    → PDF yükle, extraction başlat, sonucu dön

  GET  /api/v1/rfqs/{rfq_id}/quotes
    → Bir RFQ'ya ait tüm structured quote'ları listele

  GET  /api/v1/quotes/{quote_id}
    → Tek bir quote ve kalemleri

NEDEN SENKRON EXTRACTION?
  Şu an upload endpoint'i extraction bitene kadar bekliyor.
  Gerçek hayatta bu 10-30 saniye sürebilir → kötü UX.
  Phase 13'te background job'a taşınacak.
  Şimdi: basitlik ve test edilebilirlik öncelikli.

DOSYA BOYUTU LİMİTİ:
  MAX_UPLOAD_SIZE_MB settings'ten okunur.
  FastAPI'nin built-in file size limitasyonu yok, manuel kontrol yapıyoruz.

SUPPLIER_ID:
  Upload sırasında supplier_id zorunlu. Neden?
  QuoteDocument ve Quote tedarikçiye bağlı. Tedarikçi bilinmeden
  anlamlı bir teklif kaydı oluşturulamaz.
  Şimdilik UUID form alanı olarak alıyoruz.
  Phase 11'de UI bu alanı dropdown ile dolduracak.
"""

import uuid
import os
from pathlib import Path
from typing import Optional, Any

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import require_authenticated, require_employee_or_above
from app.core.config import settings
from app.db.session import get_db
from app.models.quote import Quote, QuoteItem
from app.models.rfq import FileType, ParseStatus, QuoteDocument, RFQ
from app.models.user import User
from app.services.extraction.extractor import QuoteExtractor
from app.services.llm import get_llm_provider

router = APIRouter(prefix="/api/v1", tags=["quotes"])


# ── Response Schemas (Pydantic) ────────────────────────────────────────────────
# Bu şemalar API response formatını tanımlar.
# SQLAlchemy modelleri direkt döndürülmez çünkü:
# - ORM objeleri serializasyon sorunları çıkarır
# - API şeması ve DB şeması her zaman birebir örtüşmez
# Phase 11'de bunlar ayrı bir schemas/ klasörüne taşınacak.

class QuoteItemResponse(BaseModel):
    id: uuid.UUID
    line_number: int
    description: str
    quantity: float
    unit: str | None
    unit_price: float
    total_price: float

    model_config = {"from_attributes": True}


class QuoteResponse(BaseModel):
    id: uuid.UUID
    rfq_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    extracted_supplier_name: str | None = None
    quote_document_id: uuid.UUID | None
    currency: str
    subtotal: float
    vat_rate: float | None = None
    vat_amount: float | None = None
    shipping_cost: float | None = None
    discount_amount: float | None = 0.0
    other_costs: float | None = 0.0
    total_price: float
    delivery_days: int | None
    payment_terms: str | None
    warranty_months: int | None
    extraction_confidence: float | None
    extraction_notes: str | None = None
    is_compliant: bool | None
    items: list[QuoteItemResponse] = []
    can_delete: bool = True
    delete_block_reason: str | None = None

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    quote_document_id: uuid.UUID
    parse_status: str
    parse_error: str | None
    quote: QuoteResponse | None
    extracted_supplier_name: str | None = None
    supplier_mismatch: bool = False
    warning: str | None = None
    message: str


# ── Helper ─────────────────────────────────────────────────────────────────────

# ── Helper & Validation ────────────────────────────────────────────────────────

def _detect_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    mapping = {
        ".pdf": FileType.PDF,
        ".xlsx": FileType.EXCEL,
        ".jpg": FileType.IMAGE,
        ".jpeg": FileType.IMAGE,
        ".png": FileType.IMAGE,
        ".txt": FileType.EMAIL_TEXT,
        ".eml": FileType.EMAIL_TEXT,
    }
    return mapping.get(suffix, FileType.OTHER)


def _validate_file_content(content: bytes, filename: str) -> None:
    """
    Dosya boyutu, format uyumluluğu ve bozuk/sahte dosya tespiti yapar.
    """
    if not content or len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    suffix = Path(filename).suffix.lower()
    if suffix == ".xls":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Legacy Excel 97-2003 (.xls) format is not supported. Please save and upload as modern Excel (.xlsx) or PDF.",
        )

    # Magic byte / Header doğrulamaları
    if suffix == ".pdf":
        if not content.startswith(b"%PDF"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match PDF format or file is corrupt.",
            )
    elif suffix == ".xlsx":
        # .xlsx dosyaları PK zip arşividir
        if not content.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match Excel (.xlsx) format or file is corrupt.",
            )
        import io
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()
                if not any("xl/workbook.xml" in n or "workbook.xml" in n for n in names):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="File content does not match Excel (.xlsx) format or file is corrupt.",
                    )
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match Excel (.xlsx) format or file is corrupt.",
            )
    elif suffix == ".png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match PNG image format or file is corrupt.",
            )
    elif suffix in (".jpg", ".jpeg"):
        if not content.startswith(b"\xff\xd8\xff"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match JPEG image format or file is corrupt.",
            )


async def _build_upload_response(
    quote: Quote | None,
    quote_document: QuoteDocument,
    supplier: Any | None,
    db: AsyncSession,
) -> UploadResponse:
    quote_response = None
    extracted_supplier_name = None
    supplier_mismatch = False
    warning_message = None

    if quote:
        result = await db.execute(
            select(Quote)
            .where(Quote.id == quote.id)
            .options(
                selectinload(Quote.items),
                selectinload(Quote.supplier)
            )
        )
        quote_with_items = result.scalar_one_or_none()
        if quote_with_items:
            quote_response = QuoteResponse.model_validate(quote_with_items)
            if quote_with_items.supplier:
                quote_response.supplier_name = quote_with_items.supplier.name
            extracted_supplier_name = quote_with_items.extracted_supplier_name

            # Supplier mismatch kontrolü
            if supplier and extracted_supplier_name:
                import re
                def _words(text: str):
                    return {w for w in re.sub(r"[^\w\s]", "", text.lower()).split() if len(w) >= 3}
                sel_words = _words(supplier.name)
                ext_words = _words(extracted_supplier_name)
                if not (sel_words & ext_words):
                    supplier_mismatch = True
                    warning_message = (
                        f"Belgeden çıkarılan tedarikçi adı ('{extracted_supplier_name}') "
                        f"ile seçilen tedarikçi ('{supplier.name}') uyuşmuyor."
                    )

    status_messages = {
        ParseStatus.COMPLETED: "Quote extracted successfully",
        ParseStatus.FAILED: f"Extraction failed: {quote_document.parse_error or 'Unknown error'}",
        ParseStatus.PROCESSING: "Extraction in progress",
        ParseStatus.PENDING: "Queued for extraction",
    }

    return UploadResponse(
        quote_document_id=quote_document.id,
        parse_status=quote_document.parse_status,
        parse_error=quote_document.parse_error,
        quote=quote_response,
        extracted_supplier_name=extracted_supplier_name,
        supplier_mismatch=supplier_mismatch,
        warning=warning_message,
        message=status_messages.get(quote_document.parse_status, "Unknown status"),
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/rfqs/{rfq_id}/quote-documents",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a supplier quote document",
)
@router.post(
    "/quotes/rfqs/{rfq_id}/quote-documents",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a supplier quote document (Alias)",
)
async def upload_quote_document(
    rfq_id: uuid.UUID,
    supplier_id: uuid.UUID = Form(..., description="Supplier UUID from the suppliers table"),
    file: UploadFile = File(..., description="PDF, Excel (.xlsx), or Image quote document"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee_or_above),
) -> UploadResponse:
    """
    Belge yükle (PDF / Excel / Resim) → extraction çalıştır → Quote kaydı oluştur.
    """
    # ── RFQ kontrolü ──────────────────────────────────────────────────────────
    rfq_res = await db.execute(
        select(RFQ).where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
    )
    rfq = rfq_res.scalar_one_or_none()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} not found",
        )

    # ── Supplier kontrolü & Organization Doğrulaması ──────────────────────────
    from app.models.supplier import Supplier
    supplier_res = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.organization_id == current_user.organization_id,
            Supplier.is_active == True,
        )
    )
    supplier = supplier_res.scalar_one_or_none()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active supplier {supplier_id} not found",
        )

    # ── Dosya boyutu ve içerik kontrolü ───────────────────────────────────────
    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE_MB} MB. "
                f"Uploaded: {len(content) / 1024 / 1024:.1f} MB"
            ),
        )

    # Güvenli dosya adı ve uzantı kontrolü
    raw_filename = file.filename or "upload"
    safe_filename = Path(raw_filename).name  # Path traversal engelleme (örn. ../../)
    _validate_file_content(content, safe_filename)

    file_type = _detect_file_type(safe_filename)
    if file_type not in (FileType.PDF, FileType.EXCEL, FileType.IMAGE, FileType.EMAIL_TEXT):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Supported: PDF, Excel (.xlsx), Image (PNG/JPG), and text/email",
        )

    # ── Dosyayı diske kaydet ──────────────────────────────────────────────────
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_suffix = Path(safe_filename).suffix.lower()
    storage_filename = f"{uuid.uuid4()}{file_suffix}"
    storage_path = (upload_dir / storage_filename).resolve()

    if not storage_path.is_relative_to(upload_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsafe file path detected.",
        )

    async with aiofiles.open(storage_path, "wb") as f:
        await f.write(content)

    # ── QuoteDocument kaydı oluştur ────────────────────────────────────────────
    quote_document = QuoteDocument(
        rfq_id=rfq_id,
        supplier_id=supplier_id,
        uploaded_by_id=current_user.id,
        file_name=storage_filename,
        file_path=str(storage_path),
        file_type=file_type,
        file_size_bytes=len(content),
        parse_status=ParseStatus.PENDING,
    )
    db.add(quote_document)
    await db.flush()

    # ── Extraction çalıştır ───────────────────────────────────────────────────
    provider = get_llm_provider()
    extractor = QuoteExtractor(provider=provider)

    quote = await extractor.extract(
        quote_document=quote_document,
        db=db,
        upload_dir=str(upload_dir),
    )

    await db.commit()
    return await _build_upload_response(quote, quote_document, supplier, db)


@router.post(
    "/rfqs/{rfq_id}/quote-documents/{document_id}/reprocess",
    response_model=UploadResponse,
    summary="Reprocess an existing quote document with retry safety",
)
@router.post(
    "/quotes/documents/{document_id}/reprocess",
    response_model=UploadResponse,
    summary="Reprocess an existing quote document (Alias)",
)
async def reprocess_quote_document(
    document_id: uuid.UUID,
    rfq_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee_or_above),
) -> UploadResponse:
    """
    Önceden yüklenmiş bir teklif belgesini (QuoteDocument) yeniden işleme alır (Retry).
    Idempotent: Mevcut Quote/QuoteItems kayıtları güvenle güncellenir.
    """
    from app.models.supplier import Supplier

    doc_res = await db.execute(
        select(QuoteDocument)
        .join(RFQ, QuoteDocument.rfq_id == RFQ.id)
        .where(
            QuoteDocument.id == document_id,
            RFQ.organization_id == current_user.organization_id,
        )
    )
    quote_document = doc_res.scalar_one_or_none()
    if not quote_document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote document {document_id} not found in your organization",
        )

    supplier = None
    if quote_document.supplier_id:
        sup_res = await db.execute(
            select(Supplier).where(Supplier.id == quote_document.supplier_id)
        )
        supplier = sup_res.scalar_one_or_none()

    provider = get_llm_provider()
    extractor = QuoteExtractor(provider=provider)

    quote = await extractor.extract(
        quote_document=quote_document,
        db=db,
        upload_dir=settings.UPLOAD_DIR,
    )
    await db.commit()

    return await _build_upload_response(quote, quote_document, supplier, db)


# ── Quote Deletion Validation ──────────────────────────────────────────────────

async def _compute_quote_can_delete(quote_id: uuid.UUID, db: AsyncSession) -> tuple[bool, str | None]:
    """
    Checks if a quote can be safely deleted.
    Quotes linked to Purchase Orders or Approved Approvals/Recommendations cannot be deleted.
    """
    from app.models.order import PurchaseOrder
    from app.models.analysis import Approval, ApprovalStatus, Analysis, Recommendation

    # 1. Purchase Order check
    po_res = await db.execute(
        select(PurchaseOrder.id).where(PurchaseOrder.quote_id == quote_id).limit(1)
    )
    if po_res.scalar_one_or_none() is not None:
        return False, "Onaylanmış bir satın alma kararında veya Satın Alma Siparişinde (PO) yer alan teklif silinemez."

    # 2. Approved human approval referencing this quote
    approval_res = await db.execute(
        select(Approval.id).where(
            Approval.selected_quote_id == quote_id,
            Approval.status.in_([ApprovalStatus.APPROVED.value, ApprovalStatus.EXCEPTION_APPROVED.value])
        ).limit(1)
    )
    if approval_res.scalar_one_or_none() is not None:
        return False, "Onaylanmış bir satın alma kararında veya Satın Alma Siparişinde (PO) yer alan teklif silinemez."

    # 3. Approved recommendation referencing this quote
    rec_approval_res = await db.execute(
        select(Approval.id)
        .join(Approval.analysis)
        .join(Analysis.recommendation)
        .where(
            Recommendation.recommended_quote_id == quote_id,
            Approval.status.in_([ApprovalStatus.APPROVED.value, ApprovalStatus.EXCEPTION_APPROVED.value])
        )
        .limit(1)
    )
    if rec_approval_res.scalar_one_or_none() is not None:
        return False, "Onaylanmış bir satın alma kararında veya Satın Alma Siparişinde (PO) yer alan teklif silinemez."

    return True, None


@router.get(
    "/rfqs/{rfq_id}/quotes",
    response_model=list[QuoteResponse],
    summary="List all quotes for an RFQ",
)
async def list_quotes(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> list[QuoteResponse]:
    """Bir RFQ'ya ait tüm structured quote'ları döndür."""
    rfq_check = await db.execute(
        select(RFQ.id).where(RFQ.id == rfq_id, RFQ.organization_id == current_user.organization_id)
    )
    if not rfq_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} not found",
        )

    result = await db.execute(
        select(Quote)
        .where(Quote.rfq_id == rfq_id)
        .options(
            selectinload(Quote.items),
            selectinload(Quote.supplier)
        )
        .order_by(Quote.created_at)
    )
    quotes = result.scalars().all()
    
    response_list = []
    for q in quotes:
        can_del, block_reason = await _compute_quote_can_delete(q.id, db)
        dto = QuoteResponse.model_validate(q)
        dto.can_delete = can_del
        dto.delete_block_reason = block_reason
        if q.supplier:
            dto.supplier_name = q.supplier.name
        response_list.append(dto)
        
    return response_list


@router.get(
    "/quotes/{quote_id}",
    response_model=QuoteResponse,
    summary="Get a specific quote with line items",
)
async def get_quote(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> QuoteResponse:
    """Tek bir quote ve tüm kalemlerini döndür."""
    result = await db.execute(
        select(Quote)
        .join(Quote.rfq)
        .where(Quote.id == quote_id, RFQ.organization_id == current_user.organization_id)
        .options(
            selectinload(Quote.items),
            selectinload(Quote.supplier),
        )
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found",
        )
    can_del, block_reason = await _compute_quote_can_delete(quote.id, db)
    dto = QuoteResponse.model_validate(quote)
    dto.can_delete = can_del
    dto.delete_block_reason = block_reason
    if quote.supplier:
        dto.supplier_name = quote.supplier.name
    return dto


@router.get(
    "/rfqs/{rfq_id}/quotes/{quote_id}",
    response_model=QuoteResponse,
    summary="Get a specific quote under an RFQ",
)
async def get_rfq_quote(
    rfq_id: uuid.UUID,
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> QuoteResponse:
    """Belirli bir RFQ altındaki tek bir quote'u ve kalemlerini doğrula ve döndür."""
    result = await db.execute(
        select(Quote)
        .join(Quote.rfq)
        .where(
            Quote.id == quote_id,
            Quote.rfq_id == rfq_id,
            RFQ.organization_id == current_user.organization_id,
        )
        .options(
            selectinload(Quote.items),
            selectinload(Quote.supplier),
        )
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found under RFQ {rfq_id}",
        )
    can_del, block_reason = await _compute_quote_can_delete(quote.id, db)
    dto = QuoteResponse.model_validate(quote)
    dto.can_delete = can_del
    dto.delete_block_reason = block_reason
    if quote.supplier:
        dto.supplier_name = quote.supplier.name
    return dto


@router.delete(
    "/rfqs/{rfq_id}/quotes/{quote_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a supplier quote under an RFQ",
)
@router.delete(
    "/quotes/{quote_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a supplier quote (Alias)",
)
async def delete_quote(
    quote_id: uuid.UUID,
    rfq_id: uuid.UUID | None = None,
    organization_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee_or_above),
):
    """
    Tedarikçi teklifini güvenli bir şekilde siler.
    PO veya onaylanmış bir analizde yer alan tekliflerin silinmesi engellenir.
    """
    query = (
        select(Quote)
        .join(Quote.rfq)
        .where(Quote.id == quote_id, RFQ.organization_id == current_user.organization_id)
    )
    if rfq_id:
        query = query.where(Quote.rfq_id == rfq_id)
    result = await db.execute(query)
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teklif ({quote_id}) bulunamadı",
        )

    rfq = await db.get(RFQ, quote.rfq_id)
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teklife bağlı RFQ ({quote.rfq_id}) bulunamadı",
        )

    # Deletion rules check
    can_del, block_reason = await _compute_quote_can_delete(quote.id, db)
    if not can_del:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=block_reason,
        )

    # Clean up physical quote document file if no other quote references it
    if quote.quote_document_id:
        doc = await db.get(QuoteDocument, quote.quote_document_id)
        if doc:
            other_q = await db.execute(
                select(Quote.id).where(
                    Quote.quote_document_id == doc.id,
                    Quote.id != quote.id
                ).limit(1)
            )
            if other_q.scalar_one_or_none() is None:
                if doc.file_path and os.path.exists(doc.file_path):
                    try:
                        os.remove(doc.file_path)
                    except OSError:
                        pass
                await db.delete(doc)

    await db.delete(quote)
    await db.flush()

    # If RFQ has no quotes left and is in collecting_quotes, revert to draft
    remaining_quotes = await db.execute(select(Quote.id).where(Quote.rfq_id == rfq.id))
    if not remaining_quotes.scalars().all():
        from sqlalchemy import update
        from app.models.rfq import RFQStatus
        if rfq.status == RFQStatus.COLLECTING_QUOTES.value:
            await db.execute(
                update(RFQ).where(RFQ.id == rfq.id).values(status=RFQStatus.DRAFT.value)
            )

    await db.commit()

    return {
        "status": "success",
        "message": "Tedarikçi teklifi başarıyla silindi",
        "id": str(quote_id),
        "rfq_id": str(rfq.id),
    }

