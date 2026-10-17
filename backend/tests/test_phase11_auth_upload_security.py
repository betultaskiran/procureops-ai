"""
backend/tests/test_phase11_auth_upload_security.py

Phase 11: Authentication Security, Upload Regression & Production Readiness Test Suite.

Scenarios Covered:
1. Authenticated multipart PDF upload with Bearer token (201 Created).
2. Authenticated multipart PDF upload with HttpOnly cookie (201 Created).
3. Authenticated Excel (.xlsx) upload with Bearer token (201 Created).
4. Missing authentication credentials rejected with 401 and WWW-Authenticate: Bearer.
5. Expired JWT token rejected with 401.
6. Invalid/forged JWT signature rejected with 401.
7. Inactive user rejected with 400 Bad Request.
8. Inactive organization rejected with 403 Forbidden.
9. Cross-tenant RFQ upload isolation (Org B cannot upload to Org A RFQ -> 404).
10. Cross-tenant supplier validation (cannot specify supplier from another org -> 404).
11. Unsupported, empty (0-byte), legacy .xls, and corrupt files rejected (400/415).
12. Insecure query parameter tokens (?token=, ?access_token=) strictly rejected with 401.
13. CSRF defense: Cookie-only request with Sec-Fetch-Site: cross-site rejected with 403.
14. CSRF defense: Cookie-only request with untrusted Origin rejected with 403.
15. CSRF defense: Cookie-only request with trusted Origin succeeds (201 Created).
16. Reprocess quote document idempotency: repeated extraction updates existing records without duplication.
"""

from datetime import timedelta
import io
from pathlib import Path
from unittest.mock import patch
import uuid

import jwt
import openpyxl
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.quote import Quote, QuoteItem
from app.models.rfq import FileType, ParseStatus, QuoteDocument, RFQ
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services.extraction.schemas import (
    QuoteExtractionSchema,
    QuoteItemExtractionSchema,
)
from app.services.llm.base import LLMProvider
from tests.auth_helper import AuthContext, create_test_auth_context


# ── Synthetic Helpers ──────────────────────────────────────────────────────────

def make_digital_pdf_bytes(text: str = "Standard Procurement Quote") -> bytes:
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


def make_sample_xlsx_bytes() -> bytes:
    """Creates a synthetic .xlsx workbook in memory."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Quote_Details"
    ws.append(["Line", "Description", "Qty", "Unit Price", "Total Price"])
    ws.append([1, "Enterprise Server Hardware", 2, 5000.0, 10000.0])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider returning deterministic QuoteExtractionSchema."""
    def __init__(self, return_schema: QuoteExtractionSchema | None = None):
        self.return_schema = return_schema or QuoteExtractionSchema(
            supplier_name="Verified Supplier Inc",
            currency="USD",
            subtotal=1000.0,
            vat_rate=0.0,
            vat_amount=0.0,
            shipping_cost=0.0,
            discount_amount=0.0,
            total_price=1000.0,
            delivery_days=10,
            payment_terms="net-30",
            warranty_months=12,
            items=[
                QuoteItemExtractionSchema(
                    line_number=1,
                    description="Standard IT Equipment",
                    quantity=1.0,
                    unit_price=1000.0,
                    total_price=1000.0,
                )
            ],
        )

    @property
    def model_name(self) -> str:
        return "mock-gemini-flash"

    async def extract_structured(self, prompt, schema, system_prompt=None, config=None):
        return self.return_schema

    async def generate(self, prompt, system_prompt=None, config=None):
        return "Mock response"


async def create_rfq_and_supplier(auth: AuthContext) -> tuple[RFQ, Supplier]:
    """Helper to persist an active RFQ and active Supplier in the test organization."""
    async with AsyncSessionLocal() as session:
        rfq = RFQ(
            organization_id=auth.organization.id,
            title=f"RFQ-{uuid.uuid4().hex[:6]}",
            status="collecting_quotes",
            budget=50000,
        )
        session.add(rfq)
        await session.flush()

        supplier = Supplier(
            organization_id=auth.organization.id,
            name=f"Supplier-{uuid.uuid4().hex[:6]}",
            email=f"supp_{uuid.uuid4().hex[:6]}@suppliercorp.com",
            is_active=True,
        )
        session.add(supplier)
        await session.commit()
        await session.refresh(rfq)
        await session.refresh(supplier)
        return rfq, supplier


# ── 1. Bearer Token Upload Success ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_authenticated_multipart_pdf_upload_bearer_success():
    """1. Uploading a valid PDF using Authorization: Bearer <token> succeeds with HTTP 201."""
    auth = await create_test_auth_context(role=UserRole.EMPLOYEE)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    mock_provider = MockLLMProvider()

    with patch("app.api.v1.quotes.get_llm_provider", return_value=mock_provider):
        async with AsyncClient(transport=transport, base_url="http://test", headers=auth.headers) as client:
            pdf_bytes = make_digital_pdf_bytes("Quote from Verified Supplier Inc")
            res = await client.post(
                f"/api/v1/rfqs/{rfq.id}/quote-documents",
                data={"supplier_id": str(supplier.id)},
                files={"file": ("quote_doc.pdf", pdf_bytes, "application/pdf")},
            )

            assert res.status_code == 201
            data = res.json()
            assert data["parse_status"] == ParseStatus.COMPLETED
            assert data["quote"] is not None
            assert data["quote"]["total_price"] == 1000.0
            assert len(data["quote"]["items"]) == 1

    # Verify DB persistence
    async with AsyncSessionLocal() as session:
        doc = await session.get(QuoteDocument, uuid.UUID(data["quote_document_id"]))
        assert doc is not None
        assert doc.parse_status == ParseStatus.COMPLETED
        assert doc.file_type == FileType.PDF


# ── 2. Cookie Authentication Upload Success ───────────────────────────────────

@pytest.mark.asyncio
async def test_authenticated_multipart_pdf_upload_cookie_success():
    """2. Uploading a valid PDF using HttpOnly access_token cookie from a trusted Origin succeeds with HTTP 201."""
    auth = await create_test_auth_context(role=UserRole.EMPLOYEE)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    mock_provider = MockLLMProvider()

    with patch("app.api.v1.quotes.get_llm_provider", return_value=mock_provider):
        # Authenticate purely via cookie (no Authorization header), Origin matches allowed frontend
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"access_token": auth.token},
            headers={"Origin": "http://localhost:3000"},
        ) as client:
            pdf_bytes = make_digital_pdf_bytes("Quote content via cookie auth")
            res = await client.post(
                f"/api/v1/rfqs/{rfq.id}/quote-documents",
                data={"supplier_id": str(supplier.id)},
                files={"file": ("cookie_quote.pdf", pdf_bytes, "application/pdf")},
            )

            assert res.status_code == 201
            data = res.json()
            assert data["parse_status"] == ParseStatus.COMPLETED
            assert data["quote"]["total_price"] == 1000.0


# ── 3. Excel Upload Success ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_authenticated_xlsx_upload_success():
    """3. Uploading a valid Excel (.xlsx) file with Bearer token succeeds with HTTP 201."""
    auth = await create_test_auth_context(role=UserRole.ADMIN)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    mock_provider = MockLLMProvider()

    with patch("app.api.v1.quotes.get_llm_provider", return_value=mock_provider):
        async with AsyncClient(transport=transport, base_url="http://test", headers=auth.headers) as client:
            xlsx_bytes = make_sample_xlsx_bytes()
            res = await client.post(
                f"/api/v1/rfqs/{rfq.id}/quote-documents",
                data={"supplier_id": str(supplier.id)},
                files={
                    "file": (
                        "hardware_quote.xlsx",
                        xlsx_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )

            assert res.status_code == 201
            data = res.json()
            assert data["parse_status"] == ParseStatus.COMPLETED
            assert data["quote"] is not None


# ── 4. Missing Auth Credentials ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quote_upload_missing_auth_returns_401():
    """4. Unauthenticated quote upload returns 401 with WWW-Authenticate: Bearer header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        dummy_rfq_id = uuid.uuid4()
        res = await client.post(
            f"/api/v1/rfqs/{dummy_rfq_id}/quote-documents",
            data={"supplier_id": str(uuid.uuid4())},
            files={"file": ("quote.pdf", b"%PDF-1.4...", "application/pdf")},
        )
        assert res.status_code == 401
        assert res.headers.get("WWW-Authenticate") == "Bearer"
        assert res.json()["detail"] == "Authentication credentials were not provided"


# ── 5. Expired Token ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quote_upload_expired_token_returns_401():
    """5. An expired JWT bearer token returns 401 with 'Token has expired'."""
    auth = await create_test_auth_context()
    rfq, supplier = await create_rfq_and_supplier(auth)

    expired_token = create_access_token(
        {"sub": str(auth.user.id), "org_id": str(auth.organization.id), "role": auth.user.role},
        expires_delta=timedelta(seconds=-10),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {expired_token}"},
    ) as client:
        res = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("quote.pdf", b"%PDF-1.4...", "application/pdf")},
        )
        assert res.status_code == 401
        assert res.json()["detail"] == "Token has expired"
        assert res.headers.get("WWW-Authenticate") == "Bearer"


# ── 6. Invalid Signature Token ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quote_upload_invalid_signature_returns_401():
    """6. A JWT signed with a bogus secret returns 401 with 'Could not validate credentials'."""
    auth = await create_test_auth_context()
    rfq, supplier = await create_rfq_and_supplier(auth)

    forged_token = jwt.encode(
        {"sub": str(auth.user.id), "org_id": str(auth.organization.id), "role": auth.user.role, "exp": 9999999999},
        "attacker-fabricated-secret-key-that-does-not-match-backend",
        algorithm="HS256",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {forged_token}"},
    ) as client:
        res = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("quote.pdf", b"%PDF-1.4...", "application/pdf")},
        )
        assert res.status_code == 401
        assert res.json()["detail"] == "Could not validate credentials"


# ── 7. Inactive User ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inactive_user_cannot_upload():
    """7. An inactive user account returns 400 Bad Request."""
    auth = await create_test_auth_context(is_active=False)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth.headers) as client:
        res = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("quote.pdf", b"%PDF-1.4...", "application/pdf")},
        )
        assert res.status_code == 400
        assert res.json()["detail"] == "Inactive user account"


# ── 8. Inactive Organization ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inactive_org_cannot_upload():
    """8. A user belonging to a suspended/inactive organization returns 403 Forbidden."""
    auth = await create_test_auth_context(org_active=False)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth.headers) as client:
        res = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("quote.pdf", b"%PDF-1.4...", "application/pdf")},
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "Organization is inactive or suspended"


# ── 9. Cross-Tenant RFQ Upload Blocked ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_tenant_isolation_quote_upload_blocked():
    """9. A user from Org B cannot upload quotes to an RFQ owned by Org A (returns 404)."""
    auth_a = await create_test_auth_context(role=UserRole.ADMIN)
    auth_b = await create_test_auth_context(role=UserRole.ADMIN)
    rfq_a, supplier_a = await create_rfq_and_supplier(auth_a)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_b.headers) as client_b:
        pdf_bytes = make_digital_pdf_bytes("Cross org attack")
        res = await client_b.post(
            f"/api/v1/rfqs/{rfq_a.id}/quote-documents",
            data={"supplier_id": str(supplier_a.id)},
            files={"file": ("cross_quote.pdf", pdf_bytes, "application/pdf")},
        )
        # Returns 404 to avoid leaking existence of RFQs in other organizations
        assert res.status_code == 404
        assert f"RFQ {rfq_a.id} not found" in res.json()["detail"]


# ── 10. Cross-Tenant Supplier Validation ──────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_tenant_supplier_validation():
    """10. An Org A user cannot associate a quote with a supplier belonging to Org B."""
    auth_a = await create_test_auth_context(role=UserRole.ADMIN)
    auth_b = await create_test_auth_context(role=UserRole.ADMIN)
    rfq_a, supplier_a = await create_rfq_and_supplier(auth_a)
    rfq_b, supplier_b = await create_rfq_and_supplier(auth_b)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_a.headers) as client_a:
        pdf_bytes = make_digital_pdf_bytes("Supplier mismatch test")
        res = await client_a.post(
            f"/api/v1/rfqs/{rfq_a.id}/quote-documents",
            data={"supplier_id": str(supplier_b.id)},  # supplier belongs to Org B!
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        )
        assert res.status_code == 404
        assert f"Active supplier {supplier_b.id} not found" in res.json()["detail"]


# ── 11. Unsupported, Empty, and Corrupt Files ──────────────────────────────────

@pytest.mark.asyncio
async def test_unsupported_file_types_rejected():
    """11. Rejects empty, corrupted, legacy .xls, and unsupported binary files."""
    auth = await create_test_auth_context(role=UserRole.ADMIN)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth.headers) as client:
        # A. Empty 0-byte file
        res_empty = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert res_empty.status_code == 400
        assert "Uploaded file is empty (0 bytes)" in res_empty.json()["detail"]

        # B. Corrupt PDF header (does not start with %PDF)
        res_corrupt = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("fake.pdf", b"NOT_A_REAL_PDF_HEADER", "application/pdf")},
        )
        assert res_corrupt.status_code == 400
        assert "File content does not match PDF format" in res_corrupt.json()["detail"]

        # C. Legacy .xls file
        res_xls = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("legacy.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/vnd.ms-excel")},
        )
        assert res_xls.status_code == 400
        assert "Legacy Excel 97-2003 (.xls) format is not supported" in res_xls.json()["detail"]

        # D. Unsupported extension (.exe)
        res_exe = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream")},
        )
        assert res_exe.status_code == 415
        assert "Unsupported file type" in res_exe.json()["detail"]


# ── 12. Query Parameter Tokens Strictly Rejected ──────────────────────────────

@pytest.mark.asyncio
async def test_query_param_tokens_rejected_with_401():
    """
    12. Passing tokens via URL query parameters (?token= or ?access_token=)
    is strictly ignored and returns 401 when no Authorization header or cookie is present.
    """
    auth = await create_test_auth_context()
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    # Neither headers nor cookies supplied, only URL query param
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A. ?token=
        res1 = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents?token={auth.token}",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("quote.pdf", make_digital_pdf_bytes(), "application/pdf")},
        )
        assert res1.status_code == 401
        assert res1.json()["detail"] == "Authentication credentials were not provided"

        # B. ?access_token=
        res2 = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents?access_token={auth.token}",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("quote.pdf", make_digital_pdf_bytes(), "application/pdf")},
        )
        assert res2.status_code == 401
        assert res2.json()["detail"] == "Authentication credentials were not provided"


# ── 13. CSRF: Sec-Fetch-Site: cross-site Rejected ─────────────────────────────

@pytest.mark.asyncio
async def test_csrf_cookie_auth_cross_site_rejected():
    """13. A state-changing request authenticated purely via cookie with Sec-Fetch-Site: cross-site is rejected with 403."""
    auth = await create_test_auth_context(role=UserRole.ADMIN)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"access_token": auth.token},
        headers={"Sec-Fetch-Site": "cross-site"},
    ) as client:
        res = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("quote.pdf", make_digital_pdf_bytes(), "application/pdf")},
        )
        assert res.status_code == 403
        assert "cross-site requests with session cookie are prohibited" in res.json()["detail"]


# ── 14. CSRF: Untrusted Origin Rejected ───────────────────────────────────────

@pytest.mark.asyncio
async def test_csrf_cookie_auth_untrusted_origin_rejected():
    """14. A state-changing request authenticated purely via cookie from an untrusted Origin is rejected with 403."""
    auth = await create_test_auth_context(role=UserRole.ADMIN)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"access_token": auth.token},
        headers={"Origin": "https://attacker-phishing-portal.com"},
    ) as client:
        res = await client.post(
            f"/api/v1/rfqs/{rfq.id}/quote-documents",
            data={"supplier_id": str(supplier.id)},
            files={"file": ("quote.pdf", make_digital_pdf_bytes(), "application/pdf")},
        )
        assert res.status_code == 403
        assert "untrusted origin" in res.json()["detail"]


# ── 15. CSRF: Trusted Origin Allowed ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_csrf_cookie_auth_trusted_origin_succeeds():
    """15. A state-changing request authenticated purely via cookie from a configured CORS origin (e.g. localhost:3000) succeeds."""
    auth = await create_test_auth_context(role=UserRole.ADMIN)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)
    mock_provider = MockLLMProvider()

    with patch("app.api.v1.quotes.get_llm_provider", return_value=mock_provider):
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"access_token": auth.token},
            headers={"Origin": "http://localhost:3000"},
        ) as client:
            res = await client.post(
                f"/api/v1/rfqs/{rfq.id}/quote-documents",
                data={"supplier_id": str(supplier.id)},
                files={"file": ("quote.pdf", make_digital_pdf_bytes(), "application/pdf")},
            )
            assert res.status_code == 201


# ── 16. Reprocess Idempotency ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reprocess_quote_document_idempotency():
    """16. Reprocessing a quote document updates the existing Quote and QuoteItems without duplicate rows."""
    auth = await create_test_auth_context(role=UserRole.ADMIN)
    rfq, supplier = await create_rfq_and_supplier(auth)

    transport = ASGITransport(app=app)

    # First extraction: returns 1 item at 1000.0
    mock_provider_v1 = MockLLMProvider(
        QuoteExtractionSchema(
            supplier_name="Idempotent Supplier",
            currency="USD",
            subtotal=1000.0,
            total_price=1000.0,
            items=[QuoteItemExtractionSchema(line_number=1, description="Item A", quantity=1.0, unit_price=1000.0, total_price=1000.0)],
        )
    )

    with patch("app.api.v1.quotes.get_llm_provider", return_value=mock_provider_v1):
        async with AsyncClient(transport=transport, base_url="http://test", headers=auth.headers) as client:
            upload_res = await client.post(
                f"/api/v1/rfqs/{rfq.id}/quote-documents",
                data={"supplier_id": str(supplier.id)},
                files={"file": ("idempotent_quote.pdf", make_digital_pdf_bytes(), "application/pdf")},
            )
            assert upload_res.status_code == 201
            doc_id = upload_res.json()["quote_document_id"]

    # Second extraction (reprocess): returns updated price 2500.0
    mock_provider_v2 = MockLLMProvider(
        QuoteExtractionSchema(
            supplier_name="Idempotent Supplier",
            currency="USD",
            subtotal=2500.0,
            total_price=2500.0,
            items=[QuoteItemExtractionSchema(line_number=1, description="Item A updated", quantity=1.0, unit_price=2500.0, total_price=2500.0)],
        )
    )

    with patch("app.api.v1.quotes.get_llm_provider", return_value=mock_provider_v2):
        async with AsyncClient(transport=transport, base_url="http://test", headers=auth.headers) as client:
            reprocess_res = await client.post(
                f"/api/v1/quotes/documents/{doc_id}/reprocess",
            )
            assert reprocess_res.status_code == 200
            data = reprocess_res.json()
            assert data["quote"]["total_price"] == 2500.0
            assert data["quote"]["items"][0]["description"] == "Item A updated"

    # Confirm in DB that exactly 1 Quote and 1 QuoteItem exist for this document
    async with AsyncSessionLocal() as session:
        quotes = (await session.execute(select(Quote).where(Quote.quote_document_id == uuid.UUID(doc_id)))).scalars().all()
        assert len(quotes) == 1
        items = (await session.execute(select(QuoteItem).where(QuoteItem.quote_id == quotes[0].id))).scalars().all()
        assert len(items) == 1
        assert items[0].description == "Item A updated"
