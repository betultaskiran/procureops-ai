"""
app/services/extraction/extractor.py

Orchestrator: PDF / Excel / Resim → metin/multimodal → LLM → validation → veritabanı.

Phase 8 Yenilikleri:
  1. Çoklu Format Desteği:
     - Metin tabanlı PDF: pdfplumber ile hızlı, yerel metin/tablo çıkarımı
     - Taranmış (Scanned) PDF: Metin katmanı yoksa Gemini Multimodal Vision ile OCR fallback
     - Excel (.xlsx): openpyxl ile sayfaların tablo formatına dönüştürülmesi
     - Resim (.png, .jpg, .jpeg): Gemini Vision ile doğrudan görsel teklif çıkarma
  2. Idempotency (Yinelenen İstek Güvenliği):
     - Yeniden denemelerde (retry) eski Quote/QuoteItem kayıtları temizlenir, mükerrer kayıt oluşmaz.
  3. Matematiksel ve Şema Validasyonu:
     - Eksik ve sıfır değer ayrımı, tutar uyumsuzluğu uyarıları Quote.notes ve metadata'ya kaydedilir.
"""

import logging
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_correlation_id
from app.models.quote import Quote, QuoteItem
from app.models.rfq import ParseStatus, QuoteDocument
from app.services.extraction.excel_parser import (
    EmptyExcelError,
    ExcelParseError,
    extract_text_from_excel,
)
from app.services.extraction.pdf_parser import (
    PDFParseError,
    ScannedPDFError,
    extract_text_from_pdf,
)
from app.services.extraction.schemas import QuoteExtractionSchema
from app.services.llm.base import EXTRACTION_CONFIG, LLMExtractionError, LLMProvider

try:
    from google.genai import types as genai_types
except ImportError:
    genai_types = None


logger = logging.getLogger("app.services.extraction")


def _extract_token_counts(provider: LLMProvider) -> tuple[int | None, int | None]:
    """Safely extracts token usage numbers from provider's last_usage_metadata."""
    metadata = getattr(provider, "last_usage_metadata", None)
    if metadata is None:
        return None, None
    prompt_tokens = getattr(metadata, "prompt_token_count", None)
    if prompt_tokens is None:
        prompt_tokens = getattr(metadata, "prompt_tokens", None)
    if prompt_tokens is None and isinstance(metadata, dict):
        prompt_tokens = metadata.get("prompt_token_count") or metadata.get("prompt_tokens")

    output_tokens = getattr(metadata, "candidates_token_count", None)
    if output_tokens is None:
        output_tokens = getattr(metadata, "output_tokens", None)
    if output_tokens is None and isinstance(metadata, dict):
        output_tokens = metadata.get("candidates_token_count") or metadata.get("output_tokens")

    return prompt_tokens, output_tokens


EXTRACTION_SYSTEM_PROMPT = """
You are a precise financial document extraction assistant for a procurement system.

Your task: Extract structured data from supplier quote documents.

Guidelines:
- Be precise with numbers — do not round or estimate
- If a field is not mentioned in the document, return null (do not guess or assume zero)
- For shipping_cost, discount_amount, other_costs: use 0.0 ONLY if explicitly stated as free/0. Otherwise return null.
- Express VAT/KDV as a decimal fraction: 0.20 for 20%, 0.10 for 10%
- Use ISO 4217 currency codes: TRY (not TL or ₺), USD, EUR, GBP
- Convert all dates to ISO 8601: YYYY-MM-DD
- Convert "business days" to calendar days (multiply by 1.4, round up)
- Extract all line items (description, quantity, unit_price, total_price) accurately
- Set extraction_confidence based on document clarity:
    1.0 = all fields explicitly stated and mathematically consistent
    0.7 = most fields stated, minor ambiguity
    0.4 = several fields missing or ambiguous
    0.2 = document is very poor quality or blurry
- In extraction_notes, record any fields that required inference, had math discrepancies, or were missing
""".strip()


class QuoteExtractor:
    """
    Tedarikçi teklif belgelerini (PDF, Excel, Resim) ayrıştırıp veritabanına kaydeden servis.
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
        """
        correlation_id = get_correlation_id()
        pdf_duration_ms: float = 0.0
        gemini_duration_ms: float = 0.0

        # ── 1. Processing durumuna al ──────────────────────────────────────────
        quote_document.parse_status = ParseStatus.PROCESSING
        quote_document.parse_error = None
        await db.commit()

        file_path = Path(quote_document.file_path) if quote_document.file_path else (Path(upload_dir) / quote_document.file_name)

        if not file_path.exists():
            await self._mark_failed(quote_document, f"File not found on storage: {file_path}", db)
            return None

        suffix = file_path.suffix.lower()

        try:
            extraction_result: QuoteExtractionSchema

            # ── 2. Dosya tipine göre ayrıştırma ve extraction ───────────────────
            if suffix == ".xlsx":
                # Excel ayrıştırma
                excel_text = extract_text_from_excel(file_path)
                gemini_t0 = time.monotonic()
                extraction_result = await self.provider.extract_structured(
                    prompt=excel_text,
                    schema=QuoteExtractionSchema,
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    config=EXTRACTION_CONFIG,
                )
                gemini_duration_ms = round((time.monotonic() - gemini_t0) * 1000, 2)

            elif suffix in (".png", ".jpg", ".jpeg"):
                # Resim formatları -> Doğrudan Gemini Multimodal Vision
                img_bytes = file_path.read_bytes()
                mime_type = "image/png" if suffix == ".png" else "image/jpeg"
                multimodal_content = self._create_multimodal_part(img_bytes, mime_type)

                gemini_t0 = time.monotonic()
                extraction_result = await self.provider.extract_structured(
                    prompt=[
                        multimodal_content,
                        "Extract the supplier quote data from this image document according to the schema.",
                    ],
                    schema=QuoteExtractionSchema,
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    config=EXTRACTION_CONFIG,
                )
                gemini_duration_ms = round((time.monotonic() - gemini_t0) * 1000, 2)
                self._append_extraction_note(extraction_result, "Extracted via Multimodal Vision (image)")

            elif suffix == ".pdf":
                # PDF: Önce hızlı ve yerel metin katmanı ayrıştırması
                pdf_t0 = time.monotonic()
                try:
                    pdf_text = extract_text_from_pdf(file_path)
                    pdf_duration_ms = round((time.monotonic() - pdf_t0) * 1000, 2)

                    gemini_t0 = time.monotonic()
                    extraction_result = await self.provider.extract_structured(
                        prompt=pdf_text,
                        schema=QuoteExtractionSchema,
                        system_prompt=EXTRACTION_SYSTEM_PROMPT,
                        config=EXTRACTION_CONFIG,
                    )
                    gemini_duration_ms = round((time.monotonic() - gemini_t0) * 1000, 2)
                except ScannedPDFError:
                    # Metin katmanı yok/yetersiz -> Multimodal OCR Fallback
                    pdf_duration_ms = round((time.monotonic() - pdf_t0) * 1000, 2)
                    pdf_bytes = file_path.read_bytes()
                    multimodal_part = self._create_multimodal_part(pdf_bytes, "application/pdf")

                    gemini_t0 = time.monotonic()
                    extraction_result = await self.provider.extract_structured(
                        prompt=[
                            multimodal_part,
                            "This is a scanned or image-based PDF quote. Extract all structured quote fields and line items according to the schema.",
                        ],
                        schema=QuoteExtractionSchema,
                        system_prompt=EXTRACTION_SYSTEM_PROMPT,
                        config=EXTRACTION_CONFIG,
                    )
                    gemini_duration_ms = round((time.monotonic() - gemini_t0) * 1000, 2)
                    self._append_extraction_note(
                        extraction_result, "Extracted via Gemini Multimodal OCR fallback (scanned PDF)"
                    )

            elif suffix in (".txt", ".eml"):
                # Düz metin / e-posta teklifi
                text_content = file_path.read_text(encoding="utf-8", errors="replace")
                gemini_t0 = time.monotonic()
                extraction_result = await self.provider.extract_structured(
                    prompt=text_content,
                    schema=QuoteExtractionSchema,
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    config=EXTRACTION_CONFIG,
                )
                gemini_duration_ms = round((time.monotonic() - gemini_t0) * 1000, 2)

            else:
                await self._mark_failed(
                    quote_document,
                    f"Unsupported file format: {suffix}. Supported: .pdf, .xlsx, .png, .jpg, .jpeg, .txt",
                    db,
                )
                return None

            prompt_tokens, output_tokens = _extract_token_counts(self.provider)
            logger.info(
                "Quote extraction telemetry: correlation_id=%s rfq_id=%s doc_id=%s file_type=%s "
                "pdf_duration_ms=%.2f gemini_duration_ms=%.2f prompt_tokens=%s output_tokens=%s",
                correlation_id or "-",
                quote_document.rfq_id,
                quote_document.id,
                suffix,
                pdf_duration_ms,
                gemini_duration_ms,
                prompt_tokens if prompt_tokens is not None else "-",
                output_tokens if output_tokens is not None else "-",
            )

            # ── 3. Quote ve QuoteItems oluştur (Idempotent: eskileri temizle) ────
            quote = await self._create_quote(
                extraction=extraction_result,
                quote_document=quote_document,
                db=db,
            )

            # ── 4. Başarılı Tamamlama ──────────────────────────────────────────
            quote_document.parse_status = ParseStatus.COMPLETED
            quote_document.parse_error = None
            await db.commit()
            await db.refresh(quote)
            return quote

        except EmptyExcelError as e:
            logger.warning(
                "Quote extraction failed (EmptyExcel): correlation_id=%s rfq_id=%s doc_id=%s",
                correlation_id or "-",
                quote_document.rfq_id,
                quote_document.id,
            )
            await self._mark_failed(quote_document, f"Excel error: {e}", db)
            return None

        except ExcelParseError as e:
            logger.warning(
                "Quote extraction failed (ExcelParseError): correlation_id=%s rfq_id=%s doc_id=%s",
                correlation_id or "-",
                quote_document.rfq_id,
                quote_document.id,
            )
            await self._mark_failed(quote_document, f"Excel parse error: {e}", db)
            return None

        except PDFParseError as e:
            logger.warning(
                "Quote extraction failed (PDFParseError): correlation_id=%s rfq_id=%s doc_id=%s pdf_duration_ms=%.2f",
                correlation_id or "-",
                quote_document.rfq_id,
                quote_document.id,
                pdf_duration_ms,
            )
            await self._mark_failed(quote_document, f"PDF parse error: {e}", db)
            return None

        except LLMExtractionError as e:
            raw = e.raw_response or ""
            logger.error(
                "Quote extraction failed (LLMExtractionError): correlation_id=%s rfq_id=%s doc_id=%s "
                "pdf_duration_ms=%.2f gemini_duration_ms=%.2f error=%s",
                correlation_id or "-",
                quote_document.rfq_id,
                quote_document.id,
                pdf_duration_ms,
                gemini_duration_ms,
                type(e).__name__,
            )
            await self._mark_failed(
                quote_document,
                f"LLM extraction failed: {e}. Raw: {raw[:200]}",
                db,
            )
            return None

        except Exception as e:
            logger.error(
                "Quote extraction unexpected error: correlation_id=%s rfq_id=%s doc_id=%s error_type=%s",
                correlation_id or "-",
                quote_document.rfq_id,
                quote_document.id,
                type(e).__name__,
            )
            await self._mark_failed(
                quote_document, f"Unexpected error during extraction: {type(e).__name__}: {e}", db
            )
            return None

    def _create_multimodal_part(self, data: bytes, mime_type: str) -> Any:
        """Multimodal API Part nesnesi oluşturur."""
        if genai_types is None:
            raise PDFParseError("Google GenAI SDK is not available for multimodal OCR extraction.")
        return genai_types.Part.from_bytes(data=data, mime_type=mime_type)

    def _append_extraction_note(self, extraction: QuoteExtractionSchema, note: str) -> None:
        if extraction.extraction_notes:
            extraction.extraction_notes = f"{extraction.extraction_notes} | {note}"
        else:
            extraction.extraction_notes = note

    async def _create_quote(
        self,
        extraction: QuoteExtractionSchema,
        quote_document: QuoteDocument,
        db: AsyncSession,
    ) -> Quote:
        """
        QuoteExtractionSchema'yı Quote + QuoteItems olarak veritabanına yazar.
        Idempotent: Aynı QuoteDocument için daha önce oluşturulmuş bir Quote varsa
        mükerrer kayıt oluşmaması için önce eski Quote ve bağlı kalemleri silinir.
        """
        # Eski kayıtları temizle (Idempotent retry)
        existing_res = await db.execute(
            select(Quote).where(Quote.quote_document_id == quote_document.id)
        )
        for old_quote in existing_res.scalars().all():
            await db.delete(old_quote)
        await db.flush()

        valid_until_date: date | None = None
        if extraction.valid_until:
            try:
                valid_until_date = date.fromisoformat(extraction.valid_until)
            except ValueError:
                pass

        # Validasyon uyarılarını notlara iliştir
        all_notes = extraction.notes or ""
        if extraction.validation_warnings:
            warning_text = "[VALIDATION WARNINGS]: " + "; ".join(extraction.validation_warnings)
            all_notes = f"{all_notes}\n{warning_text}".strip()
        if extraction.quote_number:
            all_notes = f"[Quote No: {extraction.quote_number}] {all_notes}".strip()

        quote = Quote(
            rfq_id=quote_document.rfq_id,
            supplier_id=quote_document.supplier_id,
            quote_document_id=quote_document.id,
            currency=extraction.currency,
            subtotal=Decimal(str(round(extraction.subtotal, 4))),
            vat_rate=Decimal(str(round(extraction.vat_rate, 4))) if extraction.vat_rate is not None else None,
            vat_amount=Decimal(str(round(extraction.vat_amount, 4))) if extraction.vat_amount is not None else None,
            shipping_cost=Decimal(str(round(extraction.shipping_cost, 4))) if extraction.shipping_cost is not None else None,
            discount_amount=Decimal(str(round(extraction.discount_amount or 0.0, 4))),
            other_costs=Decimal(str(round(extraction.other_costs or 0.0, 4))),
            total_price=Decimal(str(round(extraction.total_price, 4))),
            delivery_days=extraction.delivery_days,
            payment_terms=extraction.payment_terms,
            warranty_months=extraction.warranty_months,
            valid_until=valid_until_date,
            notes=all_notes if all_notes else None,
            extracted_supplier_name=extraction.supplier_name,
            extraction_confidence=Decimal(str(round(extraction.extraction_confidence, 2))),
            is_compliant=None,  # Phase 4 deterministik katman dolduracak
        )

        db.add(quote)
        await db.flush()

        # QuoteItems
        for item in extraction.items:
            quote_item = QuoteItem(
                quote_id=quote.id,
                line_number=item.line_number,
                description=item.description,
                quantity=Decimal(str(round(item.quantity, 4))),
                unit=item.unit,
                unit_price=Decimal(str(round(item.unit_price, 4))),
                total_price=Decimal(str(round(item.total_price, 4))),
            )
            db.add(quote_item)

        await db.flush()
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
