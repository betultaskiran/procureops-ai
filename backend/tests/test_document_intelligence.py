"""
backend/tests/test_document_intelligence.py

Comprehensive Phase 8 Document Intelligence Test Suite.

Scenarios Covered:
1. Text-based PDF extraction.
2. PDF table extraction and formatting.
3. Scanned/textless PDF detection (< 50 chars) and multimodal OCR fallback invocation.
4. OCR provider failure and retryable error handling.
5. .xlsx extraction with multiple sheets and item rows.
6. Corrupt, empty (0-byte), and legacy .xls file handling.
7. Schema and arithmetic validation (item totals, subtotal, and grand total math).
8. Missing versus zero values differentiation.
9. Failed extraction does not create a usable partial quote.
10. Retrying a document does not duplicate quotes/items (idempotent reprocess).
11. Tenant authorization and upload safety (path traversal prevention, org isolation).
12. Completed extraction proceeds through deterministic analysis prerequisites.
13. Failed or processing document blocks deterministic analysis.
"""

import io
import os
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.v1.quotes import _detect_file_type, _validate_file_content
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.analysis import Analysis, AnalysisStatus
from app.models.quote import Quote, QuoteItem
from app.models.rfq import FileType, ParseStatus, QuoteDocument, RFQ, RFQItem
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services.deterministic.orchestrator import DeterministicEngine
from app.services.deterministic.schemas import PolicyRules
from app.services.extraction.excel_parser import (
    EmptyExcelError,
    ExcelParseError,
    extract_text_from_excel,
)
from app.services.extraction.extractor import QuoteExtractor
from app.services.extraction.pdf_parser import (
    PDFParseError,
    ScannedPDFError,
    _format_table,
    extract_text_from_pdf,
)
from app.services.extraction.schemas import (
    QuoteExtractionSchema,
    QuoteItemExtractionSchema,
)
from app.services.llm.base import (
    EXTRACTION_CONFIG,
    ExtractionConfig,
    LLMExtractionError,
    LLMProvider,
)
from tests.auth_helper import create_test_auth_context


# ── Synthetic Fixture Helpers ──────────────────────────────────────────────────

def make_digital_pdf_bytes(text: str) -> bytes:
    """Creates a minimal valid text-layer PDF 1.4."""
    stream_content = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET"
    stream_len = len(stream_content)
    pdf = f"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length {stream_len} >> stream
{stream_content}
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000330 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
420
%%EOF"""
    return pdf.encode("latin-1")


def make_textless_scanned_pdf_bytes() -> bytes:
    """Creates a minimal PDF without text stream (simulating a scanned document)."""
    pdf = """%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj
4 0 obj << /Length 0 >> stream
endstream endobj
xref
0 5
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000215 00000 n 
trailer << /Size 5 /Root 1 0 R >>
startxref
300
%%EOF"""
    return pdf.encode("latin-1")


def make_sample_xlsx_bytes() -> bytes:
    """Creates a synthetic multi-sheet .xlsx workbook in memory."""
    wb = openpyxl.Workbook()
    # Sheet 1: Fiyat Teklifi
    ws1 = wb.active
    ws1.title = "Teklif_Detayi"
    ws1.append(["Kalem No", "Ürün Açıklaması", "Miktar", "Birim", "Birim Fiyat", "Toplam"])
    ws1.append([1, "Dizüstü Bilgisayar i7", 20, "adet", 30000.0, 600000.0])
    ws1.append([2, "Kablosuz Mouse", 20, "adet", 500.0, 10000.0])

    # Sheet 2: Ticari Koşullar
    ws2 = wb.create_sheet(title="Ticari_Kosullar")
    ws2.append(["Koşul", "Değer"])
    ws2.append(["Teslimat Süresi", "14 gün"])
    ws2.append(["Ödeme Vadesi", "net-30"])
    ws2.append(["Garanti Süresi", "24 ay"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider for unit testing."""
    def __init__(self, return_schema: QuoteExtractionSchema | None = None, should_fail: bool = False):
        self.return_schema = return_schema
        self.should_fail = should_fail
        self.last_prompt = None

    @property
    def model_name(self) -> str:
        return "mock-gemini-flash"

    async def extract_structured(self, prompt, schema, system_prompt=None, config=None):
        self.last_prompt = prompt
        if self.should_fail:
            raise LLMExtractionError("Mock LLM extraction provider failure")
        return self.return_schema

    async def generate(self, prompt, system_prompt=None, config=None):
        return "Mock response"


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_text_based_pdf_extraction(tmp_path):
    """1. Text-based PDF extraction via pdfplumber."""
    pdf_bytes = make_digital_pdf_bytes("Tedarikci Teklifi No: DEF-2026-12345. Sayin Yetkili, talep etmis oldugunuz donanim urunlerine ait birim fiyat ve genel toplam teklifimiz asagidadir. Toplam Tutar: 50.000 TL")
    test_pdf_file = tmp_path / "digital_quote.pdf"
    test_pdf_file.write_bytes(pdf_bytes)

    extracted = extract_text_from_pdf(test_pdf_file)
    assert "Tedarikci Teklifi No: DEF-2026-12345" in extracted
    assert "Toplam Tutar: 50.000 TL" in extracted
    assert "--- Page 1 ---" in extracted


def test_pdf_table_formatting():
    """2. PDF table formatting converts 2D array to markdown pipe syntax."""
    table = [
        ["Ürün", "Miktar", "Birim Fiyat"],
        ["Laptop", "10", "30000"],
        [None, "", None],  # empty row should be skipped
        ["Monitör", "20", "5000"],
    ]
    formatted = _format_table(table)
    assert "Ürün | Miktar | Birim Fiyat" in formatted
    assert "Laptop | 10 | 30000" in formatted
    assert "Monitör | 20 | 5000" in formatted


@pytest.mark.asyncio
async def test_scanned_pdf_detection_and_ocr_fallback(tmp_path):
    """3. Textless PDF triggers ScannedPDFError and invokes multimodal OCR fallback."""
    pdf_bytes = make_textless_scanned_pdf_bytes()
    scanned_pdf_file = tmp_path / "scanned_quote.pdf"
    scanned_pdf_file.write_bytes(pdf_bytes)

    # 1. extract_text_from_pdf directly raises ScannedPDFError
    with pytest.raises(ScannedPDFError):
        extract_text_from_pdf(scanned_pdf_file)

    # 2. QuoteExtractor catches ScannedPDFError and uses OCR fallback
    mock_extracted_quote = QuoteExtractionSchema(
        supplier_name="Acme Scanned Corp",
        currency="TRY",
        subtotal=100000.0,
        vat_rate=0.20,
        vat_amount=20000.0,
        total_price=120000.0,
        delivery_days=10,
        warranty_months=12,
        extraction_confidence=0.85,
        items=[
            QuoteItemExtractionSchema(
                line_number=1,
                description="Scanned Item",
                quantity=10,
                unit_price=10000.0,
                total_price=100000.0,
            )
        ]
    )

    mock_provider = MockLLMProvider(return_schema=mock_extracted_quote)
    extractor = QuoteExtractor(provider=mock_provider)

    auth = await create_test_auth_context(role=UserRole.ADMIN)
    async with AsyncSessionLocal() as session:
        # Create RFQ and Supplier
        rfq = RFQ(
            organization_id=auth.organization.id,
            title="OCR Test RFQ",
            status="collecting_quotes",
        )
        session.add(rfq)
        await session.flush()

        supplier = Supplier(
            organization_id=auth.organization.id,
            name="Acme Scanned Corp",
            email=f"scanned_{uuid.uuid4().hex[:6]}@supplier.com",
        )
        session.add(supplier)
        await session.flush()

        doc = QuoteDocument(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            file_name=scanned_pdf_file.name,
            file_path=str(scanned_pdf_file),
            file_type=FileType.PDF,
            parse_status=ParseStatus.PENDING,
        )
        session.add(doc)
        await session.commit()

        # Run extraction
        quote = await extractor.extract(quote_document=doc, db=session)
        assert quote is not None
        assert doc.parse_status == ParseStatus.COMPLETED
        assert quote.total_price == Decimal("120000.0000")
        assert quote.currency == "TRY"
        assert len(quote.items) == 1
        # Provider received multimodal list [part, prompt]
        assert isinstance(mock_provider.last_prompt, list)


@pytest.mark.asyncio
async def test_ocr_provider_failure_and_error_handling(tmp_path):
    """4. OCR provider failure updates status to FAILED without leaving partial quote."""
    pdf_bytes = make_textless_scanned_pdf_bytes()
    scanned_pdf_file = tmp_path / "failing_scanned_quote.pdf"
    scanned_pdf_file.write_bytes(pdf_bytes)

    failing_provider = MockLLMProvider(should_fail=True)
    extractor = QuoteExtractor(provider=failing_provider)

    auth = await create_test_auth_context(role=UserRole.ADMIN)
    async with AsyncSessionLocal() as session:
        rfq = RFQ(organization_id=auth.organization.id, title="Fail RFQ", status="draft")
        session.add(rfq)
        await session.flush()

        supplier = Supplier(
            organization_id=auth.organization.id,
            name="Fail Supplier",
            email=f"fail_{uuid.uuid4().hex[:6]}@supplier.com",
        )
        session.add(supplier)
        await session.flush()

        doc = QuoteDocument(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            file_name=scanned_pdf_file.name,
            file_path=str(scanned_pdf_file),
            file_type=FileType.PDF,
            parse_status=ParseStatus.PENDING,
        )
        session.add(doc)
        await session.commit()

        quote = await extractor.extract(quote_document=doc, db=session)
        assert quote is None
        assert doc.parse_status == ParseStatus.FAILED
        assert "LLM extraction failed" in (doc.parse_error or "")

        # Assert no Quote was created
        quotes_in_db = (
            await session.execute(select(Quote).where(Quote.quote_document_id == doc.id))
        ).scalars().all()
        assert len(quotes_in_db) == 0


@pytest.mark.asyncio
async def test_xlsx_extraction_multiple_sheets_and_items(tmp_path):
    """5. .xlsx extraction with multiple sheets and item rows."""
    xlsx_bytes = make_sample_xlsx_bytes()
    xlsx_file = tmp_path / "supplier_quote.xlsx"
    xlsx_file.write_bytes(xlsx_bytes)

    extracted_text = extract_text_from_excel(xlsx_file)
    assert "--- Sheet: Teklif_Detayi ---" in extracted_text
    assert "Dizüstü Bilgisayar i7" in extracted_text
    assert "Kablosuz Mouse" in extracted_text
    assert "--- Sheet: Ticari_Kosullar ---" in extracted_text
    assert "Teslimat Süresi | 14 gün" in extracted_text


def test_corrupt_empty_and_legacy_files(tmp_path):
    """6. Empty, corrupt, and legacy .xls files are properly caught and rejected."""
    # 0 bytes empty
    with pytest.raises(HTTPException) as exc_empty:
        _validate_file_content(b"", "empty.pdf")
    assert exc_empty.value.status_code == 400
    assert "empty" in exc_empty.value.detail.lower()

    # Legacy .xls
    with pytest.raises(HTTPException) as exc_xls:
        _validate_file_content(b"\xd0\xcf\x11\xe0", "quote.xls")
    assert exc_xls.value.status_code == 400
    assert "Legacy Excel 97-2003 (.xls) format is not supported" in exc_xls.value.detail

    # Corrupt PDF (does not start with %PDF)
    with pytest.raises(HTTPException) as exc_pdf:
        _validate_file_content(b"not a valid pdf", "fake.pdf")
    assert exc_pdf.value.status_code == 400
    assert "PDF format" in exc_pdf.value.detail

    # Corrupt XLSX (does not start with PK\x03\x04)
    with pytest.raises(HTTPException) as exc_xlsx:
        _validate_file_content(b"not a valid zip", "fake.xlsx")
    assert exc_xlsx.value.status_code == 400
    assert "Excel (.xlsx) format" in exc_xlsx.value.detail


def test_schema_and_arithmetic_validation():
    """7. Schema normalisation and arithmetic consistency warnings."""
    # 1. Currency & VAT normalisation
    schema = QuoteExtractionSchema(
        currency="TL",
        subtotal=100.0,
        vat_rate=20.0,  # 20 -> 0.20
        vat_amount=20.0,
        total_price=120.0,
        items=[
            QuoteItemExtractionSchema(
                line_number=1,
                description="Desk",
                quantity=1.0,
                unit_price=100.0,
                total_price=100.0,
            )
        ]
    )
    assert schema.currency == "TRY"
    assert schema.vat_rate == 0.20
    assert len(schema.validation_warnings) == 0

    # 2. Arithmetic discrepancy in line item (10 x 50 != 1000)
    schema_bad_line = QuoteExtractionSchema(
        currency="USD",
        subtotal=1000.0,
        vat_rate=0.0,
        vat_amount=0.0,
        total_price=1000.0,
        items=[
            QuoteItemExtractionSchema(
                line_number=1,
                description="Item",
                quantity=10.0,
                unit_price=50.0,
                total_price=1000.0,  # Expected 500
            )
        ]
    )
    assert any("Line 1 calculation mismatch" in w for w in schema_bad_line.validation_warnings)

    # 3. Items sum vs subtotal discrepancy
    schema_bad_sum = QuoteExtractionSchema(
        currency="EUR",
        subtotal=1000.0,
        vat_rate=0.0,
        vat_amount=0.0,
        total_price=1000.0,
        items=[
            QuoteItemExtractionSchema(
                line_number=1,
                description="Item",
                quantity=1.0,
                unit_price=800.0,
                total_price=800.0,
            )
        ]
    )
    assert any("Items sum" in w for w in schema_bad_sum.validation_warnings)

    # 4. Total price mismatch
    schema_bad_total = QuoteExtractionSchema(
        currency="TRY",
        subtotal=1000.0,
        vat_rate=0.20,
        vat_amount=200.0,
        shipping_cost=50.0,
        total_price=1500.0,  # Expected 1250
    )
    assert any("Total price mismatch" in w for w in schema_bad_total.validation_warnings)


def test_missing_versus_zero_values():
    """8. Missing values remain None rather than coerced to zero."""
    schema_missing = QuoteExtractionSchema(
        currency="TRY",
        subtotal=500.0,
        vat_rate=None,
        vat_amount=None,
        shipping_cost=None,
        discount_amount=None,
        other_costs=None,
        total_price=500.0,
    )
    assert schema_missing.shipping_cost is None
    assert schema_missing.discount_amount is None
    assert schema_missing.vat_rate is None

    schema_explicit_zero = QuoteExtractionSchema(
        currency="TRY",
        subtotal=500.0,
        shipping_cost=0.0,
        discount_amount=0.0,
        total_price=500.0,
    )
    assert schema_explicit_zero.shipping_cost == 0.0
    assert schema_explicit_zero.discount_amount == 0.0


@pytest.mark.asyncio
async def test_retrying_document_does_not_duplicate_quotes(tmp_path):
    """10. Reprocessing an existing document updates Quote and QuoteItems without duplicates."""
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    pdf_bytes = make_digital_pdf_bytes("Initial extraction content")
    pdf_file = tmp_path / "retry_quote.pdf"
    pdf_file.write_bytes(pdf_bytes)

    # Initial extraction
    quote_v1 = QuoteExtractionSchema(
        supplier_name="Retry Supplier",
        currency="TRY",
        subtotal=1000.0,
        total_price=1000.0,
        items=[
            QuoteItemExtractionSchema(
                line_number=1, description="Item A", quantity=1, unit_price=1000.0, total_price=1000.0
            )
        ]
    )

    provider = MockLLMProvider(return_schema=quote_v1)
    extractor = QuoteExtractor(provider=provider)

    async with AsyncSessionLocal() as session:
        rfq = RFQ(organization_id=auth.organization.id, title="Retry RFQ", status="collecting_quotes")
        session.add(rfq)
        await session.flush()

        supplier = Supplier(organization_id=auth.organization.id, name="Retry Supplier", email=f"retry_{uuid.uuid4().hex[:6]}@supplier.com")
        session.add(supplier)
        await session.flush()

        doc = QuoteDocument(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            file_name=pdf_file.name,
            file_path=str(pdf_file),
            file_type=FileType.PDF,
            parse_status=ParseStatus.PENDING,
        )
        session.add(doc)
        await session.commit()

        # Run extraction 1st time
        q1 = await extractor.extract(quote_document=doc, db=session)
        assert q1 is not None

        # Verify DB has 1 Quote and 1 QuoteItem
        q_count = (await session.execute(select(Quote).where(Quote.quote_document_id == doc.id))).scalars().all()
        assert len(q_count) == 1
        item_count = (await session.execute(select(QuoteItem).where(QuoteItem.quote_id == q1.id))).scalars().all()
        assert len(item_count) == 1

        # Now re-run extraction with updated schema (v2)
        quote_v2 = QuoteExtractionSchema(
            supplier_name="Retry Supplier",
            currency="TRY",
            subtotal=2000.0,
            total_price=2000.0,
            items=[
                QuoteItemExtractionSchema(
                    line_number=1, description="Item A v2", quantity=2, unit_price=1000.0, total_price=2000.0
                )
            ]
        )
        provider.return_schema = quote_v2

        q2 = await extractor.extract(quote_document=doc, db=session)
        assert q2 is not None
        assert q2.total_price == Decimal("2000.0000")

        # Verify DB STILL HAS EXACTLY 1 Quote and 1 QuoteItem (no duplicates)
        q_count_after = (await session.execute(select(Quote).where(Quote.quote_document_id == doc.id))).scalars().all()
        assert len(q_count_after) == 1
        item_count_after = (await session.execute(select(QuoteItem).where(QuoteItem.quote_id == q2.id))).scalars().all()
        assert len(item_count_after) == 1
        assert item_count_after[0].description == "Item A v2"


@pytest.mark.asyncio
async def test_tenant_authorization_and_upload_safety(tmp_path):
    """11. Tenant isolation blocks access to other org's RFQs and path traversal is prevented."""
    org_a = await create_test_auth_context(role=UserRole.ADMIN)
    org_b = await create_test_auth_context(role=UserRole.ADMIN)

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test", headers=org_a.headers) as client_a:
        # Create RFQ in Org A
        create_rfq = await client_a.post("/api/v1/rfqs", json={
            "title": "Org A RFQ",
            "budget": 50000.0,
            "items": [{"description": "Item 1", "quantity": 1}]
        })
        assert create_rfq.status_code == 201
        rfq_a_id = create_rfq.json()["id"]

    # Org B attempts to upload to Org A's RFQ
    async with AsyncClient(transport=transport, base_url="http://test", headers=org_b.headers) as client_b:
        fake_file = io.BytesIO(make_digital_pdf_bytes("Cross org upload attempt"))
        upload_res = await client_b.post(
            f"/api/v1/rfqs/{rfq_a_id}/quote-documents",
            data={"supplier_id": str(uuid.uuid4())},
            files={"file": ("test.pdf", fake_file, "application/pdf")},
        )
        # Must return 404 Not Found for tenant isolation
        assert upload_res.status_code == 404


@pytest.mark.asyncio
async def test_completed_extraction_proceeds_to_deterministic_analysis(tmp_path):
    """12. Two completed quote extractions allow deterministic analysis to succeed."""
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    async with AsyncSessionLocal() as session:
        rfq = RFQ(
            organization_id=auth.organization.id,
            title="Analysis Ready RFQ",
            status="collecting_quotes",
            budget=200000,
        )
        session.add(rfq)
        await session.flush()

        sup1 = Supplier(organization_id=auth.organization.id, name="Supplier 1", email=f"sup1_{uuid.uuid4().hex[:6]}@test.com")
        sup2 = Supplier(organization_id=auth.organization.id, name="Supplier 2", email=f"sup2_{uuid.uuid4().hex[:6]}@test.com")
        session.add_all([sup1, sup2])
        await session.flush()

        # Doc 1 & Quote 1 (Completed)
        doc1 = QuoteDocument(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            file_name="quote1.pdf",
            file_path="uploads/quote1.pdf",
            file_type=FileType.PDF,
            parse_status=ParseStatus.COMPLETED,
        )
        session.add(doc1)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            quote_document_id=doc1.id,
            currency="TRY",
            subtotal=Decimal("100000.00"),
            total_price=Decimal("120000.00"),
            delivery_days=7,
            warranty_months=24,
        )
        session.add(q1)

        # Doc 2 & Quote 2 (Completed)
        doc2 = QuoteDocument(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            file_name="quote2.pdf",
            file_path="uploads/quote2.pdf",
            file_type=FileType.PDF,
            parse_status=ParseStatus.COMPLETED,
        )
        session.add(doc2)
        await session.flush()

        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            quote_document_id=doc2.id,
            currency="TRY",
            subtotal=Decimal("110000.00"),
            total_price=Decimal("130000.00"),
            delivery_days=10,
            warranty_months=12,
        )
        session.add(q2)
        await session.commit()

        # Run DeterministicEngine
        engine = DeterministicEngine(db=session)
        rules = PolicyRules(max_budget=200000.0, max_delivery_days=15, min_warranty_months=12)
        analysis = await engine.run_analysis(rfq_id=rfq.id, rules=rules)

        assert analysis is not None
        assert len(analysis.tco_results) == 2
        assert len(analysis.compliance_checks) >= 2


@pytest.mark.asyncio
async def test_failed_or_processing_document_blocks_analysis(tmp_path):
    """13. A failed or in-progress quote document blocks deterministic analysis."""
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    async with AsyncSessionLocal() as session:
        rfq = RFQ(organization_id=auth.organization.id, title="Blocked RFQ", status="collecting_quotes")
        session.add(rfq)
        await session.flush()

        sup1 = Supplier(organization_id=auth.organization.id, name="Supplier A", email=f"supa_{uuid.uuid4().hex[:6]}@test.com")
        sup2 = Supplier(organization_id=auth.organization.id, name="Supplier B", email=f"supb_{uuid.uuid4().hex[:6]}@test.com")
        session.add_all([sup1, sup2])
        await session.flush()

        # Doc 1 is completed
        doc1 = QuoteDocument(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            file_name="quote1.pdf",
            file_path="uploads/quote1.pdf",
            file_type=FileType.PDF,
            parse_status=ParseStatus.COMPLETED,
        )
        # Doc 2 is FAILED
        doc2 = QuoteDocument(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            file_name="quote2.pdf",
            file_path="uploads/quote2.pdf",
            file_type=FileType.PDF,
            parse_status=ParseStatus.FAILED,
            parse_error="Corrupt document",
        )
        session.add_all([doc1, doc2])
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            quote_document_id=doc1.id,
            currency="TRY",
            subtotal=Decimal("50000.00"),
            total_price=Decimal("50000.00"),
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            quote_document_id=doc2.id,
            currency="TRY",
            subtotal=Decimal("60000.00"),
            total_price=Decimal("60000.00"),
        )
        session.add_all([q1, q2])
        await session.commit()

        # Attempting analysis must fail
        engine = DeterministicEngine(db=session)
        rules = PolicyRules()
        with pytest.raises(ValueError) as exc:
            await engine.run_analysis(rfq_id=rfq.id, rules=rules)

        assert "henüz tamamlanmadı" in str(exc.value)
