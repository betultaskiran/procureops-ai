"""
backend/tests/test_phase14_production_readiness_security.py

Comprehensive test suite for Phase 14 — Production Readiness, Security Hardening & End-to-End Validation.

Scenarios Verified:
  1. Spending authority threshold fails closed to DRAFT on missing, null, or zero amounts.
  2. Spending authority currency mismatch (non-TRY) fails closed to DRAFT.
  3. Spending authority draft guardrail strictly blocks supplier notification dispatch and portal exposure.
  4. Outbox retry blocks revived send for buyer-revoked invitations (400 Bad Request).
  5. Outbox retry blocks revived send for expired invitation tokens (400 Bad Request).
  6. Outbox retry blocks delivery for cancelled RFQs (400 Bad Request).
  7. Outbox retry blocks duplicate send for already sent or delivered messages.
  8. Supplier portal enforces cross-supplier isolation on PO viewer (403 Forbidden).
  9. Supplier portal enforces cross-RFQ isolation on PO viewer (403 Forbidden).
  10. Supplier portal rejects forged or tampered access tokens on PO viewer (401 Unauthorized).
  11. OWASP-recommended security headers are present on all HTTP API responses.
  12. Deep Excel (.xlsx) validation rejects arbitrary zip archives masquerading as spreadsheets.
  13. Rate limiter throttles excessive requests on public unauthenticated endpoints (429 Too Many Requests).
"""

import io
import json
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.rate_limit import rate_limit
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.analysis import Analysis, Approval
from app.models.email_delivery import EmailDelivery, EmailDeliveryStatus, EmailMessageType
from app.models.order import PurchaseOrder, PurchaseOrderStatus
from app.models.quote import Quote
from app.models.rfq import RFQ, RFQStatus
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services.email.factory import set_email_provider
from app.services.email.mock_provider import MockEmailProvider
from app.services.email.service import EmailDeliveryService
from app.services.workflow.email import EmailService
from app.services.workflow.order import PurchaseOrderService
from tests.auth_helper import create_test_auth_context


@pytest.fixture(autouse=True)
def setup_mock_email():
    """Autouse fixture ensuring mock email provider is used for all tests."""
    mock_prov = MockEmailProvider()
    set_email_provider(mock_prov)
    yield mock_prov
    set_email_provider(None)


# ── Scenario 1: Spending Authority Fails Closed on Missing/Zero Amounts ───────

@pytest.mark.asyncio
async def test_spending_authority_fails_closed_on_missing_or_invalid_amounts():
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Zero Cost Sup", email="zero@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Zero Cost RFQ", status=RFQStatus.COLLECTING_QUOTES.value)
        session.add_all([supplier, rfq])
        await session.flush()

        # Quote with None or zero total
        quote_zero = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            subtotal=Decimal("0.00"),
            total_price=Decimal("0.00"),  # Zero amount must fail closed
            currency="TRY",
        )
        session.add(quote_zero)
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status="completed")
        session.add(analysis)
        await session.flush()

        approval = Approval(
            analysis_id=analysis.id,
            reviewer_id=auth.user.id,
            status="approved",
            selected_quote_id=quote_zero.id,
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)

    # Create PO from approval
    async with AsyncSessionLocal() as session:
        po = await PurchaseOrderService.create_po_from_approval(session, approval)
        assert po is not None
        # Must FAIL CLOSED to DRAFT because amount is 0 / unverified
        assert po.status == PurchaseOrderStatus.DRAFT.value, f"Expected DRAFT but got {po.status}"


# ── Scenario 2: Spending Authority Currency Mismatch Fails Closed ──────────────

@pytest.mark.asyncio
async def test_spending_authority_currency_mismatch_fails_closed_to_draft():
    auth = await create_test_auth_context(role=UserRole.ADMIN)

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Global Tech Inc", email="sales@global.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Server Import RFQ", status=RFQStatus.COLLECTING_QUOTES.value)
        session.add_all([supplier, rfq])
        await session.flush()

        # Non-TRY currency (USD) under the numerical 250,000 threshold (e.g. 10,000 USD)
        quote_usd = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            subtotal=Decimal("10000.00"),
            total_price=Decimal("10000.00"),
            currency="USD",
        )
        session.add(quote_usd)
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status="completed")
        session.add(analysis)
        await session.flush()

        approval = Approval(
            analysis_id=analysis.id,
            reviewer_id=auth.user.id,
            status="approved",
            selected_quote_id=quote_usd.id,
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)

    async with AsyncSessionLocal() as session:
        po = await PurchaseOrderService.create_po_from_approval(session, approval)
        assert po is not None
        # Non-TRY currency cannot be silently compared to TRY threshold -> must fail closed to DRAFT
        assert po.status == PurchaseOrderStatus.DRAFT.value


# ── Scenario 3: DRAFT PO Blocks Supplier Email and Portal View ────────────────

@pytest.mark.asyncio
async def test_spending_authority_draft_guardrail_blocks_email_and_portal():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Mega Sup", email="mega@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Mega RFQ", status=RFQStatus.APPROVED.value)
        session.add_all([supplier, rfq])
        await session.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            subtotal=Decimal("600000.00"),
            total_price=Decimal("600000.00"),
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

        po_draft = PurchaseOrder(
            po_number=f"PO-TEST-{uuid.uuid4().hex[:6].upper()}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.DRAFT.value,
        )
        session.add(po_draft)
        await session.commit()
        await session.refresh(po_draft)

    # 1. Attempting to create outbox notification for DRAFT PO must raise ValueError
    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError, match="status 'draft'"):
            await EmailDeliveryService.create_po_notification(
                db=session,
                po_id=po_draft.id,
                organization_id=auth.organization.id,
            )

    # Calling send_po_email must safely return without marking po.email_sent = True
    await EmailService.send_po_email(po_draft.id)
    async with AsyncSessionLocal() as session:
        po_check = await session.get(PurchaseOrder, po_draft.id)
        assert po_check.email_sent is False

    # 2. Querying portal for DRAFT PO must return 404
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/portal/orders/{po_draft.id}")
        assert res.status_code == 404


# ── Scenario 4: Outbox Retry Blocks Revoked Invitations ───────────────────────

@pytest.mark.asyncio
async def test_retry_delivery_blocks_revoked_invitations():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Revoked Sup", email="revoked@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Revocation Test RFQ", status=RFQStatus.DRAFT.value)
        session.add_all([supplier, rfq])
        await session.commit()
        await session.refresh(supplier)
        await session.refresh(rfq)

    # Send invitation
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        inv_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier.id), "recipient_email": supplier.email},
        )
        assert inv_res.status_code == 202
        inv_id = inv_res.json()["id"]

        # Revoke invitation
        rev_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations/{inv_id}/revoke",
            headers=auth.headers,
        )
        assert rev_res.status_code == 200
        assert rev_res.json()["is_revoked"] is True

        # Now attempt to retry the revoked invitation -> must be rejected with 400 Bad Request
        retry_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations/{inv_id}/retry",
            headers=auth.headers,
        )
        assert retry_res.status_code == 400
        assert "İptal edilmiş" in retry_res.json()["detail"] or "revoked" in retry_res.json()["detail"].lower()


# ── Scenario 5: Outbox Retry Blocks Expired Invitations ───────────────────────

@pytest.mark.asyncio
async def test_retry_delivery_blocks_expired_invitations():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Expired Sup", email="expired@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Expiry Test RFQ", status=RFQStatus.DRAFT.value)
        session.add_all([supplier, rfq])
        await session.flush()

        expired_time = datetime.now(timezone.utc) - timedelta(days=2)
        delivery = EmailDelivery(
            organization_id=auth.organization.id,
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            recipient_email=supplier.email,
            subject="Test Expired",
            message_type=EmailMessageType.RFQ_INVITATION.value,
            idempotency_key=f"test_expired_{uuid.uuid4().hex}",
            status=EmailDeliveryStatus.FAILED.value,
            metadata_json=json.dumps({
                "invitation_token_hash": "dummyhash",
                "token_expires_at": expired_time.isoformat(),
                "is_revoked": False,
            }),
        )
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        retry_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations/{delivery.id}/retry",
            headers=auth.headers,
        )
        assert retry_res.status_code == 400
        assert "Süresi dolmuş" in retry_res.json()["detail"] or "expired" in retry_res.json()["detail"].lower()


# ── Scenario 6: Outbox Retry Blocks Cancelled RFQs ────────────────────────────

@pytest.mark.asyncio
async def test_retry_delivery_blocks_cancelled_rfqs():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Cancelled Sup", email="canc@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Cancelled RFQ", status=RFQStatus.DRAFT.value)
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
        inv_id = inv_res.json()["id"]

        # Cancel the RFQ
        await ac.post(
            f"/api/v1/rfqs/{rfq.id}/cancel",
            headers=auth.headers,
            json={"reason": "Proje iptal edildi."},
        )

        # Retry invitation for cancelled RFQ -> rejected with 400 Bad Request
        retry_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations/{inv_id}/retry",
            headers=auth.headers,
        )
        assert retry_res.status_code == 400
        assert "İptal edilmiş" in retry_res.json()["detail"]


# ── Scenario 7: Outbox Retry Blocks Already Sent/Delivered Deliveries ─────────

@pytest.mark.asyncio
async def test_retry_delivery_blocks_duplicate_sends_for_sent_deliveries():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Sent Sup", email="sent@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Sent Test RFQ", status=RFQStatus.DRAFT.value)
        session.add_all([supplier, rfq])
        await session.flush()

        delivery = EmailDelivery(
            organization_id=auth.organization.id,
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            recipient_email=supplier.email,
            subject="Test Already Sent",
            message_type=EmailMessageType.RFQ_INVITATION.value,
            idempotency_key=f"test_sent_{uuid.uuid4().hex}",
            status=EmailDeliveryStatus.SENT.value,  # Already sent
            sent_at=datetime.now(timezone.utc),
            metadata_json=json.dumps({"is_revoked": False}),
        )
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        retry_res = await ac.post(
            f"/api/v1/rfqs/{rfq.id}/invitations/{delivery.id}/retry",
            headers=auth.headers,
        )
        assert retry_res.status_code == 400
        assert "Zaten başarıyla iletilmiş" in retry_res.json()["detail"]


# ── Scenario 8 & 9 & 10: Cross-Supplier & Cross-RFQ Isolation on PO Viewer ───

@pytest.mark.asyncio
async def test_supplier_portal_token_cross_supplier_and_rfq_isolation():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier_a = Supplier(organization_id=auth.organization.id, name="Supplier A", email="sup_a@test.com")
        supplier_b = Supplier(organization_id=auth.organization.id, name="Supplier B", email="sup_b@test.com")
        rfq_1 = RFQ(organization_id=auth.organization.id, title="RFQ 1", status=RFQStatus.APPROVED.value)
        rfq_2 = RFQ(organization_id=auth.organization.id, title="RFQ 2", status=RFQStatus.APPROVED.value)
        session.add_all([supplier_a, supplier_b, rfq_1, rfq_2])
        await session.flush()

        # Quote & PO for Supplier B on RFQ 1
        quote_b = Quote(rfq_id=rfq_1.id, supplier_id=supplier_b.id, subtotal=Decimal("100000"), total_price=Decimal("100000"), currency="TRY")
        session.add(quote_b)
        await session.flush()

        analysis = Analysis(rfq_id=rfq_1.id, status="completed")
        session.add(analysis)
        await session.flush()

        approval = Approval(analysis_id=analysis.id, reviewer_id=auth.user.id, status="approved", selected_quote_id=quote_b.id)
        session.add(approval)
        await session.flush()

        po_b = PurchaseOrder(po_number=f"PO-B-{uuid.uuid4().hex[:6].upper()}", quote_id=quote_b.id, approval_id=approval.id, status=PurchaseOrderStatus.ISSUED.value)
        session.add(po_b)
        await session.commit()
        await session.refresh(po_b)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create invitation token for Supplier A on RFQ 1
        inv_a = await ac.post(
            f"/api/v1/rfqs/{rfq_1.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier_a.id), "recipient_email": supplier_a.email},
        )
        token_a = inv_a.json()["portal_url"].split("/portal/rfq/")[-1]

        # 8. Supplier A passes their valid token to view Supplier B's PO -> Rejected with 403 Forbidden!
        cross_res = await ac.get(f"/api/v1/portal/orders/{po_b.id}?token={token_a}")
        assert cross_res.status_code == 403
        assert "yetkiniz bulunmamaktadır" in cross_res.json()["detail"]

        # Create invitation token for Supplier B on RFQ 2 (different RFQ)
        inv_b2 = await ac.post(
            f"/api/v1/rfqs/{rfq_2.id}/invitations",
            headers=auth.headers,
            json={"supplier_id": str(supplier_b.id), "recipient_email": supplier_b.email},
        )
        token_b2 = inv_b2.json()["portal_url"].split("/portal/rfq/")[-1]

        # 9. Supplier B passes token for RFQ 2 to view PO for RFQ 1 -> Rejected with 403 Forbidden!
        cross_rfq_res = await ac.get(f"/api/v1/portal/orders/{po_b.id}?token={token_b2}")
        assert cross_rfq_res.status_code == 403

        # 10. Pass completely forged token -> Rejected with 401 Unauthorized!
        forged_res = await ac.get(f"/api/v1/portal/orders/{po_b.id}?token={uuid.uuid4()}.fake_signature_secret")
        assert forged_res.status_code == 401


# ── Scenario 11: Security Headers on API Responses ───────────────────────────

@pytest.mark.asyncio
async def test_security_headers_present_on_api_responses():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/health")
        assert res.status_code == 200
        headers = res.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "X-Correlation-ID" in headers

        # Test API endpoint for Cache-Control
        res_api = await ac.get("/api/v1/suppliers")
        assert "no-store" in res_api.headers.get("Cache-Control", "")


# ── Scenario 12: Deep Excel (.xlsx) Validation Rejects Fake Zip Archives ──────

@pytest.mark.asyncio
async def test_excel_upload_deep_validation_rejects_non_excel_zip():
    auth = await create_test_auth_context()

    async with AsyncSessionLocal() as session:
        supplier = Supplier(organization_id=auth.organization.id, name="Zip Sup", email="zip@test.com")
        rfq = RFQ(organization_id=auth.organization.id, title="Zip RFQ", status=RFQStatus.DRAFT.value)
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

        # Construct a real zip file that starts with PK\x03\x04 but does NOT contain xl/workbook.xml
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("notes.txt", "This is just a text file inside a zip masquerading as xlsx.")
        fake_xlsx_bytes = buf.getvalue()

        assert fake_xlsx_bytes.startswith(b"PK\x03\x04")

        files = {"file": ("fake_spreadsheet.xlsx", fake_xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        upload_res = await ac.post(f"/api/v1/portal/rfq/upload?token={token}", files=files)

        # Must be rejected with 400 Bad Request
        assert upload_res.status_code == 400
        assert "Excel (.xlsx)" in upload_res.json()["detail"]


# ── Scenario 13: Rate Limiter Throttles Excessive Requests ────────────────────

@pytest.mark.asyncio
async def test_rate_limiter_blocks_excessive_unauthenticated_requests():
    # Test rate limiter dependency directly with small threshold
    limiter = rate_limit(max_requests=3, window_seconds=60)

    unique_test_suffix = uuid.uuid4().hex[:8]

    class DummyClient:
        host = f"192.168.200.{uuid.uuid4().int % 250 + 1}"

    class DummyURL:
        path = f"/api/v1/portal/rfq/test_rl_{unique_test_suffix}"

    class DummyRequest:
        client = DummyClient()
        url = DummyURL()
        headers = {}

    req = DummyRequest()

    # Requests 1, 2, 3 succeed
    await limiter(req)
    await limiter(req)
    await limiter(req)

    # 4th request must raise HTTP 429 Too Many Requests
    with pytest.raises(Exception) as exc_info:
        await limiter(req)
    assert "429" in str(exc_info.value)
