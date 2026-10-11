"""
app/services/extraction/extractor.py

Orchestrator: PDF → metin → LLM → validation → veritabanı.

Bu dosya Phase 3'ün kalbidir. Şu işlemi yönetir:

  QuoteDocument (status=PENDING)
       │
       ▼
  pdfplumber → ham metin
       │
       ▼
  LLM (Gemini) → QuoteExtractionSchema
       │
       ▼
  Pydantic validation (field_validator'lar)
       │
       ├── BAŞARILI → Quote + QuoteItems DB'ye yazılır → status=COMPLETED
       │
       └── BAŞARISIZ → parse_error yazılır → status=FAILED

PHASE 13 NOTU:
  Şu an extraction senkron çalışıyor — HTTP isteği extraction bitene kadar bekler.
  Bu gerçek hayatta kabul edilemez (10-30 saniyelik request).
  Phase 13'te bu Celery task veya FastAPI BackgroundTask'a taşınacak.
  Şimdi temeli doğru kuruyoruz; async'leştirme sonra gelecek.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quote import Quote, QuoteItem
from app.models.rfq import ParseStatus, QuoteDocument
from app.services.extraction.pdf_parser import (
    PDFParseError,
    ScannedPDFError,
    extract_text_from_pdf,
)
from app.services.extraction.schemas import QuoteExtractionSchema
from app.services.llm.base import EXTRACTION_CONFIG, LLMExtractionError, LLMProvider


EXTRACTION_SYSTEM_PROMPT = """
You are a precise financial document extraction assistant for a procurement system.

Your task: Extract structured data from supplier quote documents.

Guidelines:
- Be precise with numbers — do not round or estimate
- If a field is not mentioned in the document, return null (do not guess)
- Express VAT/KDV as a decimal fraction: 0.20 for 20%
- Use ISO 4217 currency codes: TRY (not TL or ₺), USD, EUR
- Convert all dates to ISO 8601: YYYY-MM-DD
- Convert "business days" to calendar days (multiply by 1.4, round up)
- Set extraction_confidence based on clarity:
    1.0 = all fields explicitly stated
    0.7 = most fields stated, some inferred
    0.4 = many fields missing or ambiguous
    0.2 = document is unclear or poorly formatted
- In extraction_notes, document any field that required inference or was missing
""".strip()


class QuoteExtractor:
    """
    PDF'den Quote çıkaran servis.

    Kullanım:
        extractor = QuoteExtractor(provider=get_llm_provider())
        quote = await extractor.extract(
            quote_document=doc,
            db=session,
        )
    """

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def extract(
        self,
        quote_document: QuoteDocument,
        db: AsyncSession,
        upload_dir: str = "uploads",
    ) -> Quote | None:
        """
        QuoteDocument'ten structured Quote çıkarır.

        Adımlar:
        1. status → PROCESSING
        2. PDF → metin (pdfplumber)
        3. Metin → QuoteExtractionSchema (LLM)
        4. Schema → Quote + QuoteItems (DB)
        5. status → COMPLETED

        Herhangi bir adımda hata → status → FAILED, parse_error doldurulur.

        Returns:
            Oluşturulan Quote instance veya None (hata durumunda)
        """
        # ── 1. Processing başladı ──────────────────────────────────────────────
        quote_document.parse_status = ParseStatus.PROCESSING
        await db.commit()

        file_path = Path(upload_dir) / quote_document.file_name
        # Gerçek dosya yolu farklı saklanıyor olabilir
        if quote_document.file_path:
            file_path = Path(quote_document.file_path)

        try:
            # ── 2. PDF → Metin ─────────────────────────────────────────────────
            pdf_text = extract_text_from_pdf(file_path)

            # ── 3. LLM Extraction ──────────────────────────────────────────────
            extraction_result: QuoteExtractionSchema = await self.provider.extract_structured(
                prompt=pdf_text,
                schema=QuoteExtractionSchema,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                config=EXTRACTION_CONFIG,  # thinking_budget=0: hızlı extraction
            )

            # ── 4. Quote ve QuoteItems oluştur ─────────────────────────────────
            quote = await self._create_quote(
                extraction=extraction_result,
                quote_document=quote_document,
                db=db,
            )

            # ── 5. Başarılı ────────────────────────────────────────────────────
            quote_document.parse_status = ParseStatus.COMPLETED
            await db.commit()
            await db.refresh(quote)
            return quote

        except ScannedPDFError as e:
            await self._mark_failed(quote_document, str(e), db)
            return None

        except PDFParseError as e:
            await self._mark_failed(quote_document, f"PDF parse error: {e}", db)
            return None

        except LLMExtractionError as e:
            raw = e.raw_response or ""
            await self._mark_failed(
                quote_document,
                f"LLM extraction failed: {e}. Raw: {raw[:200]}",
                db,
            )
            return None

        except Exception as e:
            await self._mark_failed(
                quote_document, f"Unexpected error: {type(e).__name__}: {e}", db
            )
            return None

    async def _create_quote(
        self,
        extraction: QuoteExtractionSchema,
        quote_document: QuoteDocument,
        db: AsyncSession,
    ) -> Quote:
        """
        QuoteExtractionSchema'yı Quote + QuoteItems olarak veritabanına yazar.

        Neden ayrı bir metod?
          - Sorumluluğu ayır: extraction ≠ persistence
          - Test edilebilirlik: extraction'ı mock'layarak sadece persistence'ı test edebilirsin
        """
        # valid_until string'ini date'e çevir
        valid_until_date: date | None = None
        if extraction.valid_until:
            try:
                valid_until_date = date.fromisoformat(extraction.valid_until)
            except ValueError:
                pass  # Geçersiz tarih formatı — None bırak

        quote = Quote(
            rfq_id=quote_document.rfq_id,
            supplier_id=quote_document.supplier_id,
            quote_document_id=quote_document.id,
            currency=extraction.currency,
            subtotal=extraction.subtotal,
            vat_rate=extraction.vat_rate,
            vat_amount=extraction.vat_amount,
            shipping_cost=extraction.shipping_cost,
            discount_amount=extraction.discount_amount,
            other_costs=extraction.other_costs,
            total_price=extraction.total_price,
            delivery_days=extraction.delivery_days,
            payment_terms=extraction.payment_terms,
            warranty_months=extraction.warranty_months,
            valid_until=valid_until_date,
            notes=extraction.notes,
            extracted_supplier_name=extraction.supplier_name,
            extraction_confidence=Decimal(str(extraction.extraction_confidence)),
            is_compliant=None,  # Phase 4'te deterministik katman dolduracak
        )

        db.add(quote)
        await db.flush()  # quote.id'yi oluştur (commit etmeden)

        # QuoteItems
        for item in extraction.items:
            quote_item = QuoteItem(
                quote_id=quote.id,
                line_number=item.line_number,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                total_price=item.total_price,
            )
            db.add(quote_item)

        return quote

    async def _mark_failed(
        self,
        quote_document: QuoteDocument,
        error_message: str,
        db: AsyncSession,
    ) -> None:
        """Extraction başarısız olduğunda QuoteDocument'i günceller."""
        quote_document.parse_status = ParseStatus.FAILED
        quote_document.parse_error = error_message
        await db.commit()
