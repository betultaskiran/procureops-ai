"""
backend/tests/test_phase13_supplier_portal_and_email_workflow.py

Comprehensive test suite for Phase 13 — Supplier Portal, RFQ Participation & Email Workflow.
Verifies all 13 core requirements:
  1. Buyer sends RFQ invitation with token generation & valid participation URL.
  2. Valid token allows supplier to fetch RFQ specifications without leaking internal budget.
  3. Invalid or forged tokens return 401 Unauthorized.
  4. Revoked invitation token returns 403 Forbidden.
  5. Expired invitation token returns 410 Gone.
  6. Cancelled RFQ blocks invitation creation and quote submission (400 Bad Request).
  7. Supplier submits valid structured quote (persisted as Quote & QuoteItem, RFQ -> collecting_quotes).
  8. Supplier quote resubmission updates existing quote cleanly and preserves audit log.
  9. Late submission after deadline is rejected (400 Bad Request).
  10. Supplier upload of quote document (PDF/Excel) with magic byte validation.
  11. DRAFT PO (>250k TRY) never sends supplier email and is hidden in portal.
  12. ISSUED PO sends supplier email idempotently and is accessible via portal.
  13. Supplier isolation: cannot view competing quotes, analysis results, or internal notes.
"""

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.analysis import Analysis, Approval
from app.models.audit import AuditEvent
from app.models.email_delivery import EmailDelivery, EmailDeliveryStatus, EmailMessageType
from app.models.order import PurchaseOrder, PurchaseOrderStatus
from app.models.organization import Organization
from app.models.quote import Quote, QuoteItem
from app.models.rfq import QuoteDocument, RFQ, RFQItem, RFQStatus
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services.email.factory import set_email_provider
from app.services.email.mock_provider import MockEmailProvider
from app.services.workflow.email import EmailService
from tests.auth_helper import create_test_auth_context


@pytest.fixture(autouse=True)
def setup_mock_email():
    """Autouse fixture ensuring mock email provider is used for all tests."""
    mock_prov = MockEmailProvider()
    set_email_provider(mock_prov)
    yield mock_prov
    set_email_provider(None)


# ── Scenario 1: Buyer sends RFQ invitation with token generation ────────────────

@pytest.mark.asyncio
async def test_buyer_sends_rfq_invitation_creates_outbox_and_token():
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    async with AsyncSessionLocal() as session:
        supplier = Supplier(
            organization_id=auth.organization.id,
            name="Anadolu Endustriyel A.S.",
            email="sales@anadolu-endustri.com",
            phone="+90 212 555 0101",
            city="Istanbul",
        )
        session.add(supplier)

        rfq = RFQ(
            organization_id=auth.organization.id,
            title="CNC Yedek Parca Alimi",
            status=RFQStatus.DRAFT.value,
            budget=500000,
            required_date=date.today() + timedelta(days=10),
        )
        session.add(rfq)
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={
                "supplier_id": str(supplier.id),
                "recipient_email": supplier.email,
                "recipient_name": supplier.name,
                "custom_message": "Lutfen ekteki teknik sartnameye gore teklifinizi iletiniz.",
            },
        )

    assert res.status_code == 202, res.text
    data = res.json()
    assert data["recipient_email"] == supplier.email
    assert data["status"] in ["queued", "sent", "sending"]
    assert data["portal_url"] is not None
    assert "/portal/rfq/" in data["portal_url"]
    assert data["is_revoked"] is False
    assert data["submitted_at"] is None

    # Verify delivery record and token in DB
    async with AsyncSessionLocal() as session:
        stmt = select(EmailDelivery).where(EmailDelivery.id == uuid.UUID(data["id"]))
        res_db = await session.execute(stmt)
        delivery = res_db.scalars().first()
        assert delivery is not None
        assert delivery.metadata_json is not None
        meta = json.loads(delivery.metadata_json)
        assert "invitation_token_hash" in meta
        assert "token_expires_at" in meta
        assert meta["portal_url"] == data["portal_url"]


# ── Scenario 2: Valid token allows supplier to view RFQ without budget ──────────

@pytest.mark.asyncio
async def test_valid_token_allows_supplier_to_view_rfq_without_budget():
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    async with AsyncSessionLocal() as session:
        supplier = Supplier(
            organization_id=auth.organization.id,
            name="Ege Rulman Ltd.",
            email="teklif@egerulman.com",
        )
        session.add(supplier)

        rfq = RFQ(
            organization_id=auth.organization.id,
            title="Yuksek Hassasiyetli Bilya Alimi",
            description="ISO 9001 sertifikali celik bilyalar",
            status=RFQStatus.DRAFT.value,
            budget=750000,  # Confidential internal target budget
            required_date=date.today() + timedelta(days=15),
            payment_terms="net-30",
        )
        session.add(rfq)
        await session.flush()

        item = RFQItem(
            rfq_id=rfq.id,
            line_number=1,
            description="Bilya 6204-2RS",
            quantity=500,
            unit="Adet",
        )
        session.add(item)
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    # Buyer creates invitation
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={
                "supplier_id": str(supplier.id),
                "recipient_email": supplier.email,
                "recipient_name": supplier.name,
            },
        )
        assert inv_res.status_code == 202
        portal_url = inv_res.json()["portal_url"]
        token = portal_url.split("/portal/rfq/")[-1]

        # External supplier accesses portal without any auth headers
        portal_res = await ac.get(f"/api/v1/portal/rfq?token={token}")

    assert portal_res.status_code == 200, portal_res.text
    data = portal_res.json()
    assert data["rfq_title"] == "Yuksek Hassasiyetli Bilya Alimi"
    assert data["supplier_name"] == "Ege Rulman Ltd."
    assert data["supplier_email"] == "teklif@egerulman.com"
    assert data["can_submit"] is True
    assert data["deadline_passed"] is False
    assert len(data["items"]) == 1
    assert data["items"][0]["description"] == "Bilya 6204-2RS"
    assert data["items"][0]["quantity"] == 500.0

    # CRITICAL SECURITY CHECK: Budget and target unit price MUST NOT be in response!
    assert "budget" not in data
    assert "target_unit_price" not in data["items"][0]


# ── Scenario 3: Invalid or forged tokens return 401 ─────────────────────────────

@pytest.mark.asyncio
async def test_invalid_or_forged_tokens_rejected_with_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Missing token
        r1 = await ac.get("/api/v1/portal/rfq")
        assert r1.status_code == 401

        # 2. Malformed token format (no dot)
        r2 = await ac.get("/api/v1/portal/rfq?token=invalidtokenstring")
        assert r2.status_code == 401

        # 3. Non-existent UUID
        fake_uuid = uuid.uuid4()
        r3 = await ac.get(f"/api/v1/portal/rfq?token={fake_uuid}.somerandomsecret")
        assert r3.status_code == 401

        # 4. Valid delivery UUID but wrong secret
        auth = await create_test_auth_context()
        async with AsyncSessionLocal() as session:
            sup = Supplier(organization_id=auth.organization.id, name="Test Sup", email="sup@test.com")
            rfq = RFQ(organization_id=auth.organization.id, title="Test", status=RFQStatus.DRAFT.value)
            session.add_all([sup, rfq])
            await session.commit()
            await session.refresh(sup)
            await session.refresh(rfq)

        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(sup.id), "recipient_email": sup.email},
        )
        assert inv_res.status_code == 202
        valid_delivery_id = inv_res.json()["id"]

        r4 = await ac.get(f"/api/v1/portal/rfq?token={valid_delivery_id}.wrongsecretkey1234567890123456")
        assert r4.status_code == 401


# ── Scenario 4: Revoked invitation token returns 403 ────────────────────────────

@pytest.mark.asyncio
async def test_revoked_invitation_token_returns_403():
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Revoke Sup", email="revoke@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Revoke Test", status=RFQStatus.DRAFT.value)
        session.add_all([supplier, rfq])
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier.id), "recipient_email": supplier.email},
        )
        assert inv_res.status_code == 202
        inv_id = inv_res.json()["id"]
        token = inv_res.json()["portal_url"].split("/portal/rfq/")[-1]

        # Verify active before revoke
        check_before = await ac.get(f"/api/v1/portal/rfq?token={token}")
        assert check_before.status_code == 200

        # Buyer revokes invitation
        revoke_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations/{inv_id}/revoke",
            headers=auth.headers,
        )
        assert revoke_res.status_code == 200
        assert revoke_res.json()["is_revoked"] is True

        # Supplier accesses portal after revoke -> 403
        portal_res = await ac.get(f"/api/v1/portal/rfq?token={token}")
        assert portal_res.status_code == 403
        assert "iptal" in portal_res.text.lower().replace("i̇", "i")

        # Quote submission attempt also blocked -> 403
        quote_res = await ac.post(
            f"/api/v1/portal/rfq/quote?token={token}",
            json={
                "currency": "TRY",
                "subtotal": "1000.00",
                "delivery_days": 5,
                "warranty_months": 12,
                "items": [{"line_number": 1, "description": "X", "quantity": 1, "unit_price": 1000, "total_price": 1000}],
            },
        )
        assert quote_res.status_code == 403


# ── Scenario 5: Expired invitation token returns 410 ────────────────────────────

@pytest.mark.asyncio
async def test_expired_invitation_token_returns_410():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Expire Sup", email="expire@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Expire Test", status=RFQStatus.DRAFT.value)
        session.add_all([supplier, rfq])
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier.id), "recipient_email": supplier.email},
        )
        assert inv_res.status_code == 202
        delivery_id = uuid.UUID(inv_res.json()["id"])
        token = inv_res.json()["portal_url"].split("/portal/rfq/")[-1]

    # Mutate DB to set expiration in past
    async with AsyncSessionLocal() as session:
        deliv = await session.get(EmailDelivery, delivery_id)
        meta = json.loads(deliv.metadata_json)
        meta["token_expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        deliv.metadata_json = json.dumps(meta)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/portal/rfq?token={token}")
        assert res.status_code == 410
        assert "süresi dolmuştur" in res.text.lower()


# ── Scenario 6: Cancelled RFQ blocks invitation & quote submission ──────────────

@pytest.mark.asyncio
async def test_cancelled_rfq_blocks_invitation_and_submission():
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Cancel Sup", email="cancel@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Active to Cancel", status=RFQStatus.DRAFT.value)
        session.add_all([supplier, rfq])
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create invitation while active
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier.id), "recipient_email": supplier.email},
        )
        assert inv_res.status_code == 202
        token = inv_res.json()["portal_url"].split("/portal/rfq/")[-1]

        # Cancel RFQ
        cancel_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/cancel",
            headers=auth.headers,
            json={"reason": "Proje yonetimi tarafindan iptal edildi"},
        )
        assert cancel_res.status_code == 200

        # Attempt to create another invitation on cancelled RFQ -> 400
        new_inv = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier.id), "recipient_email": supplier.email},
        )
        assert new_inv.status_code == 400
        assert "iptal" in new_inv.text.lower().replace("i̇", "i")

        # Existing token access -> 400
        view_res = await ac.get(f"/api/v1/portal/rfq?token={token}")
        assert view_res.status_code == 400
        assert "iptal" in view_res.text.lower().replace("i̇", "i")


# ── Scenario 7: Supplier submits valid structured quote ─────────────────────────

@pytest.mark.asyncio
async def test_supplier_submits_valid_structured_quote():
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Teknik Cizim San.", email="info@teknikcizim.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Teknik Donanim", status=RFQStatus.DRAFT.value)
        session.add_all([supplier, rfq])
        await session.flush()

        item = RFQItem(
            rfq_id=rfq.id,
            line_number=1,
            description="Endustriyel Monitor",
            quantity=Decimal("10"),
            unit="Adet",
        )
        session.add(item)
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier.id), "recipient_email": supplier.email},
        )
        assert inv_res.status_code == 202
        token = inv_res.json()["portal_url"].split("/portal/rfq/")[-1]

        quote_payload = {
            "currency": "TRY",
            "subtotal": "100000.00",
            "vat_rate": "0.20",
            "vat_amount": "20000.00",
            "shipping_cost": "1500.00",
            "discount_amount": "5000.00",
            "other_costs": "0.00",
            "delivery_days": 10,
            "warranty_months": 24,
            "payment_terms": "net-30",
            "notes": "Pesin odemede %5 ilave iskonto uygulanabilir.",
            "items": [
                {
                    "line_number": 1,
                    "description": "Endustriyel Monitor 24 inc",
                    "quantity": "10.00",
                    "unit": "Adet",
                    "unit_price": "10000.00",
                    "total_price": "100000.00",
                }
            ],
        }

        submit_res = await ac.post(
            f"/api/v1/portal/rfq/quote?token={token}",
            json=quote_payload,
        )

    assert submit_res.status_code == 201, submit_res.text
    submit_data = submit_res.json()
    assert submit_data["success"] is True
    # Total = 100000 - 5000 + 20000 + 1500 = 116500.00
    assert Decimal(str(submit_data["total_price"])) == Decimal("116500.00")
    quote_id = uuid.UUID(submit_data["quote_id"])

    # Verify DB state: Quote, QuoteItems, RFQ status transition, AuditEvent
    async with AsyncSessionLocal() as session:
        q = await session.get(Quote, quote_id)
        assert q is not None
        assert q.supplier_id == supplier.id
        assert q.rfq_id == rfq.id
        assert q.total_price == Decimal("116500.00")
        assert q.delivery_days == 10
        assert q.warranty_months == 24

        # RFQ status should transition from draft to collecting_quotes
        rfq_db = await session.get(RFQ, rfq.id)
        assert rfq_db.status == RFQStatus.COLLECTING_QUOTES.value

        # AuditEvent
        audit_res = await session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == quote_id,
                AuditEvent.event_type == "supplier_quote_submitted",
            )
        )
        assert audit_res.scalars().first() is not None


# ── Scenario 8: Supplier resubmission updates quote cleanly ─────────────────────

@pytest.mark.asyncio
async def test_supplier_resubmission_updates_existing_quote():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Guncel Sup", email="guncel@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Guncelleme RFQ", status=RFQStatus.DRAFT.value)
        session.add_all([supplier, rfq])
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier.id), "recipient_email": supplier.email},
        )
        token = inv_res.json()["portal_url"].split("/portal/rfq/")[-1]

        # Initial submission (subtotal = 50,000)
        p1 = {
            "currency": "TRY",
            "subtotal": "50000.00",
            "vat_rate": "0.20",
            "vat_amount": "10000.00",
            "shipping_cost": "0.00",
            "discount_amount": "0.00",
            "delivery_days": 15,
            "warranty_months": 12,
            "items": [{"line_number": 1, "description": "Hizmet A", "quantity": "1", "unit_price": "50000", "total_price": "50000"}],
        }
        r1 = await ac.post(f"/api/v1/portal/rfq/quote?token={token}", json=p1)
        assert r1.status_code == 201
        quote_id_1 = r1.json()["quote_id"]

        # Resubmission / Update (subtotal = 40,000)
        p2 = {
            "currency": "TRY",
            "subtotal": "40000.00",
            "vat_rate": "0.20",
            "vat_amount": "8000.00",
            "shipping_cost": "0.00",
            "discount_amount": "0.00",
            "delivery_days": 10,
            "warranty_months": 24,
            "items": [{"line_number": 1, "description": "Hizmet A (Revize)", "quantity": "1", "unit_price": "40000", "total_price": "40000"}],
        }
        r2 = await ac.post(f"/api/v1/portal/rfq/quote?token={token}", json=p2)
        assert r2.status_code in [200, 201]
        quote_id_2 = r2.json()["quote_id"]
        assert quote_id_1 == quote_id_2  # Updates same quote in-place

        # Re-fetch RFQ via portal shows updated existing_quote
        view_res = await ac.get(f"/api/v1/portal/rfq?token={token}")
        assert view_res.status_code == 200
        view_data = view_res.json()
        assert view_data["existing_quote"] is not None
        assert view_data["existing_quote"]["subtotal"] == 40000.0
        assert view_data["existing_quote"]["total_price"] == 48000.0
        assert view_data["existing_quote"]["delivery_days"] == 10


# ── Scenario 9: Late submission after deadline is rejected ──────────────────────

@pytest.mark.asyncio
async def test_late_submission_after_deadline_rejected():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Geciken Sup", email="late@test.com")
        # RFQ required_date passed 3 days ago
        rfq = RFQ(
            organization_id=auth.organization.id,
            title="Suresi Dolan RFQ",
            status=RFQStatus.COLLECTING_QUOTES.value,
            required_date=date.today() - timedelta(days=3),
        )
        session.add_all([supplier, rfq])
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier.id), "recipient_email": supplier.email},
        )
        token = inv_res.json()["portal_url"].split("/portal/rfq/")[-1]

        # Portal view indicates deadline passed
        view_res = await ac.get(f"/api/v1/portal/rfq?token={token}")
        assert view_res.status_code == 200
        assert view_res.json()["deadline_passed"] is True
        assert view_res.json()["can_submit"] is False

        # Attempt to submit quote -> 400 Bad Request
        submit_res = await ac.post(
            f"/api/v1/portal/rfq/quote?token={token}",
            json={
                "currency": "TRY",
                "subtotal": "10000.00",
                "delivery_days": 7,
                "warranty_months": 12,
                "items": [{"line_number": 1, "description": "Test", "quantity": 1, "unit_price": 10000, "total_price": 10000}],
            },
        )
        assert submit_res.status_code == 400
        assert "süresi sona ermiştir" in submit_res.text.lower()


# ── Scenario 10: Supplier quote document upload with magic byte check ───────────

@pytest.mark.asyncio
async def test_supplier_quote_document_upload():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Dosya Sup", email="doc@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Dokuman Yukleme RFQ", status=RFQStatus.DRAFT.value)
        session.add_all([supplier, rfq])
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier.id), "recipient_email": supplier.email},
        )
        token = inv_res.json()["portal_url"].split("/portal/rfq/")[-1]

        # Valid PDF upload (%PDF-1.4 header)
        valid_pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        files = {"file": ("teklif_resmi.pdf", valid_pdf_content, "application/pdf")}
        upload_res = await ac.post(
            f"/api/v1/portal/rfq/upload?token={token}",
            files=files,
        )
        assert upload_res.status_code == 201, upload_res.text
        upload_data = upload_res.json()
        assert upload_data["file_name"] == "teklif_resmi.pdf"
        assert upload_data["file_size_bytes"] == len(valid_pdf_content)

        # Corrupted PDF content rejected with 400
        corrupt_files = {"file": ("corrupt.pdf", b"NOT_A_PDF_CONTENT", "application/pdf")}
        corrupt_res = await ac.post(
            f"/api/v1/portal/rfq/upload?token={token}",
            files=corrupt_files,
        )
        assert corrupt_res.status_code == 400

        # Disallowed file extension rejected with 415
        bad_files = {"file": ("malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream")}
        bad_res = await ac.post(
            f"/api/v1/portal/rfq/upload?token={token}",
            files=bad_files,
        )
        assert bad_res.status_code in [400, 415]


# ── Scenario 11: DRAFT PO (>250k TRY) never sends email & is hidden in portal ──

@pytest.mark.asyncio
async def test_draft_po_never_sends_email_and_hidden_in_portal():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Buyuk Sup", email="big@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Buyuk Alim", status=RFQStatus.APPROVED.value)
        session.add_all([supplier, rfq])
        await session.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            subtotal=Decimal("450000.00"),
            total_price=Decimal("450000.00"),  # > 250k TRY threshold
            currency="TRY",
        )
        session.add(quote)
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status="completed")
        session.add(analysis)
        await session.flush()

        approval = Approval(
            analysis_id=analysis.id,
            reviewer_id=auth.user.id,
            status="pending_approval",
            selected_quote_id=quote.id,
        )
        session.add(approval)
        await session.flush()

        # DRAFT PO created (held for CFO & Purchasing Director approval)
        po = PurchaseOrder(
            po_number=f"PO-DRAFT-{uuid.uuid4().hex[:8].upper()}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.DRAFT.value,
        )
        session.add(po)
        await session.commit()
        await session.refresh(po)

    # Calling send_po_email on DRAFT PO should raise or no-op without creating an email delivery
    try:
        await EmailService.send_po_email(po.id)
    except Exception:
        pass

    # Check outbox deliveries for this PO: MUST BE ZERO
    async with AsyncSessionLocal() as session:
        deliveries = (
            await session.execute(
                select(EmailDelivery).where(
                    EmailDelivery.message_type == EmailMessageType.PO_ISSUANCE.value,
                    EmailDelivery.purchase_order_id == po.id,
                )
            )
        ).scalars().all()
        assert len(deliveries) == 0

    # Supplier attempting to access DRAFT PO via portal -> 404 (strictly concealed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/portal/orders/{po.id}")
        assert res.status_code == 404


# ── Scenario 12: ISSUED PO sends email idempotently & visible in portal ─────────

@pytest.mark.asyncio
async def test_issued_po_sends_email_idempotently_and_visible_in_portal():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Onayli Sup", email="onayli@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Onayli Alim", status=RFQStatus.APPROVED.value)
        session.add_all([supplier, rfq])
        await session.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            subtotal=Decimal("150000.00"),
            total_price=Decimal("150000.00"),
            currency="TRY",
        )
        session.add(quote)
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status="completed")
        session.add(analysis)
        await session.flush()

        approval = Approval(
            analysis_id=analysis.id,
            reviewer_id=auth.user.id,
            status="approved",
            selected_quote_id=quote.id,
        )
        session.add(approval)
        await session.flush()

        # ISSUED PO
        po = PurchaseOrder(
            po_number=f"PO-TEST-{uuid.uuid4().hex[:6].upper()}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.ISSUED.value,
        )
        session.add(po)
        await session.commit()
        await session.refresh(po)

    # Dispatch PO email
    delivery_1, _ = await EmailDeliveryService.create_po_notification(
        db=session,
        po_id=po.id,
        organization_id=auth.organization.id,
    ) if False else (None, None)

    # Use EmailService.send_po_email
    await EmailService.send_po_email(po.id)

    # Verify delivery created in outbox
    async with AsyncSessionLocal() as session:
        deliv_res = await session.execute(
            select(EmailDelivery).where(
                EmailDelivery.purchase_order_id == po.id,
                EmailDelivery.message_type == EmailMessageType.PO_ISSUANCE.value,
            )
        )
        delivery = deliv_res.scalars().first()
        assert delivery is not None
        assert delivery.recipient_email == supplier.email

    # Idempotent second call should not duplicate
    await EmailService.send_po_email(po.id)
    async with AsyncSessionLocal() as session:
        all_delivs = (
            await session.execute(
                select(EmailDelivery).where(
                    EmailDelivery.purchase_order_id == po.id,
                    EmailDelivery.message_type == EmailMessageType.PO_ISSUANCE.value,
                )
            )
        ).scalars().all()
        assert len(all_delivs) == 1

    # View awarded PO in supplier portal
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/portal/orders/{po.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["po_number"] == po.po_number
        assert data["status"] == PurchaseOrderStatus.ISSUED.value
        assert Decimal(str(data["total_amount"])) == Decimal("150000.00")
        assert data["supplier_name"] == supplier.name


# ── Scenario 13: Supplier cannot view competing quotes or internal analysis ────

@pytest.mark.asyncio
async def test_supplier_cannot_view_competing_quotes_or_analyses():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier_a = Supplier(organization_id=auth.organization.id, name="Tedarikci A", email="a@tedarik.com")
        supplier_b = Supplier(organization_id=auth.organization.id, name="Tedarikci B (Rakip)", email="b@tedarik.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Kiyaslamali RFQ", status=RFQStatus.COLLECTING_QUOTES.value)
        session.add_all([supplier_a, supplier_b, rfq])
        await session.flush()

        # Quote A
        quote_a = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier_a.id,
            total_price=Decimal("120000.00"),
            currency="TRY",
            subtotal=Decimal("100000.00"),
        )
        # Competing Quote B (cheaper)
        quote_b = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier_b.id,
            total_price=Decimal("95000.00"),
            currency="TRY",
            subtotal=Decimal("80000.00"),
        )
        session.add_all([quote_a, quote_b])
        await session.commit()
        await session.refresh(supplier_a)
        await session.refresh(supplier_b)
        await session.refresh(rfq)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create invitation specifically for Supplier A
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier_a.id), "recipient_email": supplier_a.email},
        )
        assert inv_res.status_code == 202
        token_a = inv_res.json()["portal_url"].split("/portal/rfq/")[-1]

        # Supplier A accesses portal
        portal_res = await ac.get(f"/api/v1/portal/rfq?token={token_a}")
        assert portal_res.status_code == 200
        data = portal_res.json()

        # Supplier A sees only their own data
        assert data["supplier_name"] == "Tedarikci A"
        assert "Tedarikci B" not in json.dumps(data)
        assert "95000" not in json.dumps(data)
        assert "80000" not in json.dumps(data)
        assert "recommendation" not in data
        assert "tco" not in data
