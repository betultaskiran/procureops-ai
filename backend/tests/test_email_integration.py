"""
backend/tests/test_email_integration.py

Comprehensive test suite for Phase 9 — Reliable Email Integration & Outbox Workflow.
Verifies all 13 core requirements:
  1. Correct email rendering and recipient validation (CRLF injection rejection, email regex).
  2. SMTP/provider success using a mocked transport.
  3. Missing or invalid production configuration (fail-closed settings).
  4. Transient failure and bounded retry/backoff.
  5. Permanent failure handling.
  6. Idempotent duplicate requests.
  7. Concurrent duplicate requests where practical (uniqueness constraint).
  8. Worker restart / recovery of pending jobs.
  9. Tenant isolation and role enforcement.
  10. RFQ-not-found and supplier-not-found behavior.
  11. No false `delivered` status when only SMTP acceptance is known.
  12. Safe handling of provider errors without leaking credentials.
  13. Existing RFQ, approval, PO lifecycle integration.
"""

import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, DEV_JWT_SECRET
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.analysis import Analysis, Approval
from app.models.email_delivery import EmailDelivery, EmailDeliveryStatus, EmailMessageType
from app.models.order import PurchaseOrder, PurchaseOrderStatus
from app.models.organization import Organization
from app.models.quote import Quote
from app.models.rfq import RFQ
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services.email.base import EmailMessage
from app.services.email.factory import get_email_provider, set_email_provider
from app.services.email.mock_provider import MockEmailProvider
from app.services.email.renderer import (
    validate_email_address,
    EmailValidationError,
    render_rfq_invitation,
    render_po_notification,
)
from app.services.email.service import EmailDeliveryService
from app.services.email.smtp_provider import SMTPEmailProvider
from app.services.email.worker import process_outbox_batch
from app.services.workflow.email import EmailService
from tests.auth_helper import create_test_auth_context


@pytest.fixture(autouse=True)
def setup_mock_email():
    """Autouse fixture ensuring mock email provider is used for all tests."""
    mock_prov = MockEmailProvider()
    set_email_provider(mock_prov)
    yield mock_prov
    set_email_provider(None)


# ── Scenario 1: Rendering & Validation ──────────────────────────────────────────

def test_email_rendering_and_validation():
    # 1. Valid emails pass
    valid = validate_email_address("procurement.officer@enterprise-corp.com")
    assert valid == "procurement.officer@enterprise-corp.com"

    # 2. Reject empty
    with pytest.raises(EmailValidationError, match="cannot be empty"):
        validate_email_address("")

    # 3. Reject CRLF / Header Injection
    with pytest.raises(EmailValidationError, match="prohibited newline"):
        validate_email_address("supplier@vendor.com\r\nBcc: evil@hacker.com")

    with pytest.raises(EmailValidationError, match="prohibited newline"):
        validate_email_address("supplier@vendor.com%0aBcc:evil@hacker.com")

    # 4. Reject invalid syntax
    with pytest.raises(EmailValidationError, match="Invalid email address"):
        validate_email_address("not-an-email-at-all")

    # 5. Render RFQ Invitation
    rfq_id = uuid.uuid4()
    subject, text_body, html_body = render_rfq_invitation(
        rfq_id=rfq_id,
        rfq_title="50x Enterprise Laptops",
        rfq_description="Intel i7, 32GB RAM, 1TB SSD",
        required_quantity=50,
        required_date=date(2026, 12, 1),
        supplier_name="Acme Tech",
        recipient_name="John Doe",
        organization_name="Global Procurement Corp",
        app_base_url="https://app.procureops.com",
        custom_message="Please include 3-year warranty in price.",
    )

    assert "Request for Quotation: 50x Enterprise Laptops" in subject
    assert "Global Procurement Corp" in subject
    assert "Dear John Doe," in text_body
    assert "https://app.procureops.com/dashboard/rfq/" in text_body
    assert "50" in text_body
    assert "Please include 3-year warranty" in text_body
    assert "<html>" in html_body


# ── Scenario 2: Provider Success using Mock Transport ─────────────────────────

@pytest.mark.asyncio
async def test_provider_success_using_mock_transport(setup_mock_email):
    mock_provider = setup_mock_email
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Test Success RFQ")
        db.add(rfq)
        await db.commit()
        await db.refresh(rfq)

        delivery, is_new = await EmailDeliveryService.create_rfq_invitation(
            db=db,
            rfq_id=rfq.id,
            recipient_email="supplier.contact@acme.com",
            organization_id=org_ctx.organization.id,
            recipient_name="Jane Contact",
        )
        assert is_new is True
        assert delivery.status == EmailDeliveryStatus.QUEUED.value

    # Dispatch delivery
    dispatched = await EmailDeliveryService.dispatch_delivery(delivery.id)
    assert dispatched is not None
    assert dispatched.status == EmailDeliveryStatus.SENT.value
    assert dispatched.sent_at is not None
    assert dispatched.provider_message_id is not None
    assert dispatched.provider_message_id.startswith("<mock-")
    assert len(mock_provider.sent_messages) == 1
    assert mock_provider.sent_messages[0].recipient_email == "supplier.contact@acme.com"


# ── Scenario 3: Missing or Invalid Production Configuration ────────────────────

def test_missing_or_invalid_production_configuration():
    # Production forbids localhost SMTP when backend is smtp
    with pytest.raises(ValueError, match="SMTP_HOST cannot be localhost"):
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            POSTGRES_USER="puser",
            POSTGRES_PASSWORD="strong_random_password_12345",
            POSTGRES_DB="pdb",
            GEMINI_API_KEY="test_gemini_key",
            JWT_SECRET_KEY="super_long_unique_production_jwt_secret_key_32_chars",
            EMAIL_BACKEND="smtp",
            SMTP_HOST="localhost",
            SMTP_FROM_EMAIL="valid@company.com",
        )

    # Production forbids dev domain @procureops.local
    with pytest.raises(ValueError, match="cannot use development domain"):
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            POSTGRES_USER="puser",
            POSTGRES_PASSWORD="strong_random_password_12345",
            POSTGRES_DB="pdb",
            GEMINI_API_KEY="test_gemini_key",
            JWT_SECRET_KEY="super_long_unique_production_jwt_secret_key_32_chars",
            EMAIL_BACKEND="smtp",
            SMTP_HOST="smtp.sendgrid.net",
            SMTP_FROM_EMAIL="admin@procureops.local",
        )

    # Production requires SMTP_PASSWORD if SMTP_USER is set
    with pytest.raises(ValueError, match="SMTP_PASSWORD is required"):
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            POSTGRES_USER="puser",
            POSTGRES_PASSWORD="strong_random_password_12345",
            POSTGRES_DB="pdb",
            GEMINI_API_KEY="test_gemini_key",
            JWT_SECRET_KEY="super_long_unique_production_jwt_secret_key_32_chars",
            EMAIL_BACKEND="smtp",
            SMTP_HOST="smtp.sendgrid.net",
            SMTP_USER="apikey",
            SMTP_PASSWORD=None,
            SMTP_FROM_EMAIL="procurement@mycompany.com",
        )


# ── Scenario 4: Transient Failure and Bounded Retry/Backoff ────────────────────

@pytest.mark.asyncio
async def test_transient_failure_and_bounded_retry_backoff(setup_mock_email):
    mock_provider = setup_mock_email
    mock_provider.force_transient_failure = True
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Test Retry RFQ")
        db.add(rfq)
        await db.commit()
        await db.refresh(rfq)

        delivery, _ = await EmailDeliveryService.create_rfq_invitation(
            db=db,
            rfq_id=rfq.id,
            recipient_email="retry.vendor@acme.com",
            organization_id=org_ctx.organization.id,
        )

    # Attempt 1 -> transient fail, re-queued
    d1 = await EmailDeliveryService.dispatch_delivery(delivery.id)
    assert d1.status == EmailDeliveryStatus.QUEUED.value
    assert d1.attempt_count == 1
    assert d1.next_retry_at is not None
    assert "[Transient - Retry 1/3]" in d1.last_error

    # Attempt 2 -> transient fail, re-queued
    d2 = await EmailDeliveryService.dispatch_delivery(delivery.id)
    assert d2.status == EmailDeliveryStatus.QUEUED.value
    assert d2.attempt_count == 2
    assert d2.next_retry_at is not None
    assert "[Transient - Retry 2/3]" in d2.last_error

    # Attempt 3 -> max attempts (3) exceeded, marked failed
    d3 = await EmailDeliveryService.dispatch_delivery(delivery.id)
    assert d3.status == EmailDeliveryStatus.FAILED.value
    assert d3.attempt_count == 3
    assert d3.next_retry_at is None
    assert "[Max attempts (3) exceeded]" in d3.last_error


# ── Scenario 5: Permanent Failure Handling ─────────────────────────────────────

@pytest.mark.asyncio
async def test_permanent_failure_handling(setup_mock_email):
    mock_provider = setup_mock_email
    mock_provider.force_permanent_failure = True
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Test Permanent Fail RFQ")
        db.add(rfq)
        await db.commit()
        await db.refresh(rfq)

        delivery, _ = await EmailDeliveryService.create_rfq_invitation(
            db=db,
            rfq_id=rfq.id,
            recipient_email="invalid.mailbox@acme.com",
            organization_id=org_ctx.organization.id,
        )

    # Dispatch: should immediately transition to FAILED without backoff retry
    dispatched = await EmailDeliveryService.dispatch_delivery(delivery.id)
    assert dispatched.status == EmailDeliveryStatus.FAILED.value
    assert dispatched.attempt_count == 1
    assert dispatched.next_retry_at is None
    assert "[Permanent failure]" in dispatched.last_error


# ── Scenario 6: Idempotent Duplicate Requests ──────────────────────────────────

@pytest.mark.asyncio
async def test_idempotent_duplicate_requests(setup_mock_email):
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Test Idempotency RFQ")
        db.add(rfq)
        await db.commit()
        await db.refresh(rfq)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request 1
        res1 = await client.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=org_ctx.headers,
            json={
                "recipient_email": "partner@vendor.com",
                "recipient_name": "Partner",
                "custom_message": "Initial invitation",
            },
        )
        assert res1.status_code == 202
        data1 = res1.json()
        assert data1["status"] in ("queued", "sent")
        first_delivery_id = data1["id"]

        # Request 2 with identical payload
        res2 = await client.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=org_ctx.headers,
            json={
                "recipient_email": "partner@vendor.com",
                "recipient_name": "Partner",
                "custom_message": "Repeated click",
            },
        )
        assert res2.status_code == 202
        data2 = res2.json()
        # Returns the same delivery record
        assert data2["id"] == first_delivery_id

    # Verify database has exactly 1 outbox record, not 2
    async with AsyncSessionLocal() as db:
        count_res = await db.execute(
            select(EmailDelivery).where(EmailDelivery.rfq_id == rfq.id)
        )
        deliveries = count_res.scalars().all()
        assert len(deliveries) == 1


# ── Scenario 7: Concurrent Duplicate Requests Uniqueness Constraint ───────────

@pytest.mark.asyncio
async def test_concurrent_duplicate_requests_uniqueness_constraint():
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)
    unique_key = f"concurrent_key_{uuid.uuid4().hex}"

    async with AsyncSessionLocal() as db:
        d1 = EmailDelivery(
            organization_id=org_ctx.organization.id,
            recipient_email="test1@domain.com",
            subject="Test 1",
            idempotency_key=unique_key,
            status=EmailDeliveryStatus.QUEUED.value,
        )
        db.add(d1)
        await db.commit()

        # Second insert with identical idempotency_key must violate unique constraint
        d2 = EmailDelivery(
            organization_id=org_ctx.organization.id,
            recipient_email="test2@domain.com",
            subject="Test 2",
            idempotency_key=unique_key,
            status=EmailDeliveryStatus.QUEUED.value,
        )
        db.add(d2)
        with pytest.raises(IntegrityError):
            await db.commit()


# ── Scenario 8: Worker Restart / Recovery of Pending Jobs ──────────────────────

@pytest.mark.asyncio
async def test_outbox_worker_batch_and_restart_recovery(setup_mock_email):
    mock_provider = setup_mock_email
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    # Insert 3 pending deliveries directly (simulating work queued before a server restart)
    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Test Recovery RFQ")
        db.add(rfq)
        await db.flush()

        for i in range(3):
            d = EmailDelivery(
                organization_id=org_ctx.organization.id,
                rfq_id=rfq.id,
                recipient_email=f"recovered_{i}@vendor.com",
                subject=f"Recovery Test {i}",
                idempotency_key=f"recovery_key_{uuid.uuid4().hex}",
                status=EmailDeliveryStatus.QUEUED.value,
            )
            db.add(d)
        await db.commit()

    # Worker executes a batch
    processed_count = await process_outbox_batch(batch_size=10)
    assert processed_count >= 3
    assert len(mock_provider.sent_messages) >= 3


# ── Scenario 9: Tenant Isolation and Role Enforcement ─────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_and_role_enforcement():
    org_a = await create_test_auth_context(role=UserRole.EMPLOYEE)
    org_b = await create_test_auth_context(role=UserRole.EMPLOYEE)
    viewer_a = await create_test_auth_context(role=UserRole.VIEWER, org_id=org_a.organization.id)

    async with AsyncSessionLocal() as db:
        rfq_a = RFQ(organization_id=org_a.organization.id, title="Org A RFQ")
        db.add(rfq_a)
        await db.commit()
        await db.refresh(rfq_a)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Org B user cannot send invitation for Org A's RFQ (404)
        res_cross = await client.post(
            f"/api/v1/rfqs/{rfq_a.id}/invitations",
            headers=org_b.headers,
            json={"recipient_email": "attacker@vendor.com"},
        )
        assert res_cross.status_code == 404

        # 2. Org A viewer cannot send invitation (403 Forbidden)
        res_viewer = await client.post(
            f"/api/v1/rfqs/{rfq_a.id}/invitations",
            headers=viewer_a.headers,
            json={"recipient_email": "viewer_test@vendor.com"},
        )
        assert res_viewer.status_code == 403

        # 3. Org A employee can send (202 Accepted)
        res_ok = await client.post(
            f"/api/v1/rfqs/{rfq_a.id}/invitations",
            headers=org_a.headers,
            json={"recipient_email": "authorized@vendor.com"},
        )
        assert res_ok.status_code == 202


# ── Scenario 10: RFQ Not Found and Supplier Not Found ─────────────────────────

@pytest.mark.asyncio
async def test_rfq_not_found_and_supplier_not_found():
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Non-existent RFQ
        res_rfq = await client.post(
            f"/api/v1/rfqs/{uuid.uuid4()}/invitations",
            headers=org_ctx.headers,
            json={"recipient_email": "supplier@test.com"},
        )
        assert res_rfq.status_code == 404

        # Existing RFQ but non-existent supplier
        async with AsyncSessionLocal() as db:
            rfq = RFQ(organization_id=org_ctx.organization.id, title="Test Exists RFQ")
            db.add(rfq)
            await db.commit()
            await db.refresh(rfq)

        res_sup = await client.post(
            f"/api/v1/rfqs/{rfq.id}/invitations",
            headers=org_ctx.headers,
            json={
                "recipient_email": "supplier@test.com",
                "supplier_id": str(uuid.uuid4()),
            },
        )
        assert res_sup.status_code == 404


# ── Scenario 11: No False Delivered Status on SMTP Acceptance ──────────────────

@pytest.mark.asyncio
async def test_no_false_delivered_status_on_smtp_acceptance():
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Test Delivery Status RFQ")
        db.add(rfq)
        await db.commit()
        await db.refresh(rfq)

        delivery, _ = await EmailDeliveryService.create_rfq_invitation(
            db=db,
            rfq_id=rfq.id,
            recipient_email="delivered.check@vendor.com",
            organization_id=org_ctx.organization.id,
        )

    dispatched = await EmailDeliveryService.dispatch_delivery(delivery.id)
    # Critical invariant: SMTP acceptance sets 'sent', never 'delivered'
    assert dispatched.status == EmailDeliveryStatus.SENT.value
    assert dispatched.status != EmailDeliveryStatus.DELIVERED.value
    assert dispatched.delivered_at is None
    assert dispatched.sent_at is not None


# ── Scenario 12: Safe Handling of Errors Without Credential Leaks ─────────────

def test_safe_handling_of_provider_errors_without_credential_leaks():
    secret_pass = "SuperSecretP@ssword999!"
    secret_user = "confidential_username"

    provider = SMTPEmailProvider(
        host="nonexistent.smtp.server.local",
        port=587,
        username=secret_user,
        password=secret_pass,
        timeout=1,
    )

    raw_err = f"Failed to authenticate user {secret_user} with pass {secret_pass} on server"
    sanitized = provider._sanitize_error(raw_err)

    assert secret_pass not in sanitized
    assert secret_user not in sanitized
    assert "[REDACTED]" in sanitized
    assert "[REDACTED_USER]" in sanitized


# ── Scenario 13: Existing Workflow & PO Issuance Integration ──────────────────

@pytest.mark.asyncio
async def test_existing_workflow_and_po_issuance_integration():
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        supplier = Supplier(
            organization_id=org_ctx.organization.id,
            name="Awarded Supplier",
            email="awarded.vendor@corp.com",
        )
        db.add(supplier)
        await db.flush()

        rfq = RFQ(organization_id=org_ctx.organization.id, title="Awarded RFQ")
        db.add(rfq)
        await db.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            subtotal=Decimal("45000.00"),
            total_price=Decimal("45000.00"),
            currency="TRY",
        )
        db.add(quote)
        await db.flush()

        analysis = Analysis(rfq_id=rfq.id, status="completed")
        db.add(analysis)
        await db.flush()

        approval = Approval(
            analysis_id=analysis.id,
            reviewer_id=org_ctx.user.id,
            status="approved",
            selected_quote_id=quote.id,
        )
        db.add(approval)
        await db.flush()

        po = PurchaseOrder(
            po_number=f"PO-TEST-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.ISSUED.value,
        )
        db.add(po)
        await db.commit()
        await db.refresh(po)

    # Call EmailService.send_po_email
    await EmailService.send_po_email(po.id)

    # Verify PO was updated
    async with AsyncSessionLocal() as db:
        po_res = await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po.id))
        po_updated = po_res.scalars().first()
        assert po_updated.email_sent is True
        assert po_updated.email_sent_at is not None

        # Verify an outbox delivery record was created
        del_res = await db.execute(
            select(EmailDelivery).where(EmailDelivery.purchase_order_id == po.id)
        )
        delivery = del_res.scalars().first()
        assert delivery is not None
        assert delivery.recipient_email == "awarded.vendor@corp.com"
        assert delivery.message_type == EmailMessageType.PO_ISSUANCE.value
        assert delivery.status == EmailDeliveryStatus.SENT.value
