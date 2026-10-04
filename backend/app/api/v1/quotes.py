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
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models.quote import Quote, QuoteItem
from app.models.rfq import FileType, ParseStatus, QuoteDocument, RFQ
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
    quote_document_id: uuid.UUID | None
    currency: str
    subtotal: float
    vat_rate: float
    vat_amount: float
    shipping_cost: float
    discount_amount: float
    other_costs: float
    total_price: float
    delivery_days: int | None
    payment_terms: str | None
    warranty_months: int | None
    extraction_confidence: float | None
    extraction_notes: str | None = None
    is_compliant: bool | None
    items: list[QuoteItemResponse] = []

    model_config = {"from_attributes": True}

    # extraction_notes QuoteDocument'te saklı, Quote'ta değil.
    # Phase 11'de join sorgusu ile doldurulacak.


class UploadResponse(BaseModel):
    quote_document_id: uuid.UUID
    parse_status: str
    parse_error: str | None
    quote: QuoteResponse | None
    message: str


# ── Helper ─────────────────────────────────────────────────────────────────────

def _detect_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    mapping = {
        ".pdf": FileType.PDF,
        ".xlsx": FileType.EXCEL,
        ".xls": FileType.EXCEL,
        ".jpg": FileType.IMAGE,
        ".jpeg": FileType.IMAGE,
        ".png": FileType.IMAGE,
        ".txt": FileType.EMAIL_TEXT,
        ".eml": FileType.EMAIL_TEXT,
    }
    return mapping.get(suffix, FileType.OTHER)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/rfqs/{rfq_id}/quote-documents",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a supplier quote document",
    description=(
        "Upload a PDF or Excel file from a supplier. "
        "The system will extract structured quote data using AI. "
        "Returns the extraction result synchronously (Phase 13 will move this to background)."
    ),
)
async def upload_quote_document(
    rfq_id: uuid.UUID,
    supplier_id: uuid.UUID = Form(..., description="Supplier UUID from the suppliers table"),
    file: UploadFile = File(..., description="PDF or Excel quote document"),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """
    PDF yükle → extraction çalıştır → Quote kaydı oluştur.
    """
    # ── RFQ kontrolü ──────────────────────────────────────────────────────────
    rfq = await db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} not found",
        )

    # ── Dosya boyutu kontrolü ──────────────────────────────────────────────────
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

    # ── Dosya tipi kontrolü ───────────────────────────────────────────────────
    file_type = _detect_file_type(file.filename or "")
    if file_type not in (FileType.PDF, FileType.EXCEL, FileType.IMAGE, FileType.EMAIL_TEXT):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Supported: PDF, Excel, image, text/email",
        )

    # ── Dosyayı diske kaydet ──────────────────────────────────────────────────
    # UUID ile eşsiz dosya adı → aynı isimli dosyalar çakışmaz
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_suffix = Path(file.filename or "upload").suffix
    storage_filename = f"{uuid.uuid4()}{file_suffix}"
    storage_path = upload_dir / storage_filename

    async with aiofiles.open(storage_path, "wb") as f:
        await f.write(content)

    # ── QuoteDocument kaydı oluştur ────────────────────────────────────────────
    quote_document = QuoteDocument(
        rfq_id=rfq_id,
        supplier_id=supplier_id,
        file_name=storage_filename,
        file_path=str(storage_path),
        file_type=file_type,
        file_size_bytes=len(content),
        parse_status=ParseStatus.PENDING,
    )
    db.add(quote_document)
    await db.flush()  # ID üret, commit etme

    # ── Extraction çalıştır (senkron — Phase 13'te background'a taşınacak) ─────
    provider = get_llm_provider()
    extractor = QuoteExtractor(provider=provider)

    quote = await extractor.extract(
        quote_document=quote_document,
        db=db,
        upload_dir=str(upload_dir),
    )

    await db.commit()

    # ── Response ───────────────────────────────────────────────────────────────
    quote_response = None
    if quote:
        # QuoteItems'ı yükle (selectin ile)
        result = await db.execute(
            select(Quote)
            .where(Quote.id == quote.id)
            .options(selectinload(Quote.items))
        )
        quote_with_items = result.scalar_one_or_none()
        if quote_with_items:
            quote_response = QuoteResponse.model_validate(quote_with_items)

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
        message=status_messages.get(quote_document.parse_status, "Unknown status"),
    )


@router.get(
    "/rfqs/{rfq_id}/quotes",
    response_model=list[QuoteResponse],
    summary="List all quotes for an RFQ",
)
async def list_quotes(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[QuoteResponse]:
    """Bir RFQ'ya ait tüm structured quote'ları döndür."""
    result = await db.execute(
        select(Quote)
        .where(Quote.rfq_id == rfq_id)
        .options(selectinload(Quote.items))
        .order_by(Quote.created_at)
    )
    quotes = result.scalars().all()
    return [QuoteResponse.model_validate(q) for q in quotes]


@router.get(
    "/quotes/{quote_id}",
    response_model=QuoteResponse,
    summary="Get a specific quote with line items",
)
async def get_quote(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Tek bir quote ve tüm kalemlerini döndür."""
    result = await db.execute(
        select(Quote)
        .where(Quote.id == quote_id)
        .options(selectinload(Quote.items))
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found",
        )
    return QuoteResponse.model_validate(quote)
