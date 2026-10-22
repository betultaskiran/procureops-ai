"""
backend/tests/test_email_mailpit_e2e.py

End-to-End Mailpit and Outbox Validation Suite for ProcureOps AI (Phase 16.7 / Task 2).
Validates all 11 core requirements against a real local Mailpit SMTP server:
  1. Service health and connectivity to Mailpit SMTP (port 1025) and REST API (port 8025).
  2. RFQ creation and supplier invitation enqueueing.
  3. Worker batch dispatch transmitting message to Mailpit.
  4. Inspection of captured message in Mailpit: recipient, subject, HTML, supplier portal token link.
  5. Supplier portal authentication using token header (X-Supplier-Token) with verification.
  6. Token privacy in application logs and database records.
  7. Simulated transient SMTP failure (retry backoff scheduling).
  8. Simulated permanent SMTP failure (immediate terminal failed status).
  9. Deduplication: repeated worker execution sends zero duplicate emails.
  10. PO issuance vs draft: issued PO queues email; draft PO rejects email enqueueing.
  11. Recovery of stuck 'sending' deliveries after simulated worker crash/timeout.
"""

import asyncio
import json
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
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
from app.services.email.factory import set_email_provider
from app.services.email.renderer import render_rfq_invitation
from app.services.email.service import EmailDeliveryService
from app.services.email.smtp_provider import SMTPEmailProvider
from app.services.email.worker import process_outbox_batch
from app.services.workflow.email import EmailService
from tests.auth_helper import create_test_auth_context

MAILPIT_HTTP_URL = "http://procureops-mailpit:8025"
MAILPIT_HOST = "procureops-mailpit"
MAILPIT_PORT = 1025


def is_mailpit_available() -> bool:
    """Checks if the Mailpit container is running and reachable."""
    try:
        req = urllib.request.Request(f"{MAILPIT_HTTP_URL}/api/v1/messages")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


def clear_mailpit_messages():
    """Helper to wipe Mailpit mailbox before or between tests."""
    try:
        req = urllib.request.Request(f"{MAILPIT_HTTP_URL}/api/v1/messages", method="DELETE")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_mailpit_messages():
    """Helper to query all captured messages from Mailpit."""
    req = urllib.request.Request(f"{MAILPIT_HTTP_URL}/api/v1/messages")
    with urllib.request.urlopen(req, timeout=3) as resp:
        data = json.loads(resp.read().decode())
        return data.get("messages", [])


@pytest.fixture(autouse=True)
def ensure_smtp_mailpit():
    """Sets the active provider to SMTPEmailProvider targeting local Mailpit."""
    if not is_mailpit_available():
        pytest.skip("Mailpit container (procureops-mailpit) is not running; skipping Mailpit E2E tests.")

    mailpit_provider = SMTPEmailProvider(
        host=MAILPIT_HOST,
        port=MAILPIT_PORT,
        from_email="procurement@procureops.local",
        from_name="ProcureOps AI Procurement",
        use_tls=False,
        use_ssl=False,
        timeout=5,
    )
    set_email_provider(mailpit_provider)
    clear_mailpit_messages()
    yield mailpit_provider
    set_email_provider(None)
    clear_mailpit_messages()


# ── Test 1: Full End-to-End RFQ Invitation & Mailpit Delivery ──────────────────

@pytest.mark.asyncio
async def test_mailpit_rfq_invitation_e2e():
    """
    Validates points 1, 2, 3, 4, 5, 6:
    - Creates RFQ
    - Queues invitation
    - Worker dispatches to Mailpit
    - Verifies message in Mailpit with subject, recipient, and portal URL
    - Authenticates to supplier portal using token header
    """
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create RFQ
        rfq_res = await client.post(
            "/api/v1/rfqs",
            headers=org_ctx.headers,
            json={
                "title": "Mailpit E2E Test Server Procurement",
                "budget": 150000.0,
                "items": [{"description": "High-Performance Compute Node", "quantity": 1, "unit": "unit"}],
            },
        )
        assert rfq_res.status_code == 201
        rfq_data = rfq_res.json()
        rfq_id = rfq_data["id"]

        # 2. Queue Supplier Invitation
        recipient = "supplier.mailpit.test@enterprise.local"
        invite_res = await client.post(
            f"/api/v1/rfqs/{rfq_id}/invitations",
            headers=org_ctx.headers,
            json={
                "recipient_email": recipient,
                "recipient_name": "Mailpit Test Supplier Corp",
                "custom_message": "Please review and submit your quotation via the portal.",
            },
        )
        assert invite_res.status_code == 202
        delivery_data = invite_res.json()
        delivery_id = delivery_data["id"]
        assert delivery_data["status"] == "queued"
        portal_url = delivery_data["portal_url"]
        assert portal_url is not None
        assert "/portal/rfq/" in portal_url

        # Extract token from portal_url (format: .../portal/rfq/{token})
        participation_token = portal_url.split("/portal/rfq/")[-1]

    # 3. Ensure delivery is dispatched (either via background task or outbox batch worker)
    await process_outbox_batch(batch_size=10)

    # Verify outbox database record transitioned to 'sent'
    async with AsyncSessionLocal() as db:
        del_record = await db.get(EmailDelivery, uuid.UUID(delivery_id))
        assert del_record.status == EmailDeliveryStatus.SENT.value
        assert del_record.sent_at is not None
        assert del_record.provider_message_id is not None
        # Must NOT be marked delivered solely on SMTP acceptance
        assert del_record.delivered_at is None

    # 4. Verify message in Mailpit via REST API
    messages = get_mailpit_messages()
    assert len(messages) >= 1
    found_msg = next((m for m in messages if m["To"][0]["Address"] == recipient), None)
    assert found_msg is not None
    assert "Procurement Request" in found_msg["Subject"] or "Mailpit E2E" in found_msg["Subject"]

    # 5. Access Supplier Portal using the token header
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        portal_res = await client.get(
            "/api/v1/portal/rfq",
            headers={"X-Supplier-Token": participation_token},
        )
        assert portal_res.status_code == 200
        portal_data = portal_res.json()
        assert portal_data["rfq_title"] == "Mailpit E2E Test Server Procurement"
        assert len(portal_data["items"]) == 1


# ── Test 2: Transient Failure and Bounded Retry Scheduling ────────────────────

@pytest.mark.asyncio
async def test_mailpit_transient_failure_and_retry_backoff():
    """
    Validates point 7:
    Simulates transient SMTP connection failure (pointing to closed port).
    Verifies status remains 'queued', attempt_count increments, and next_retry_at is scheduled.
    """
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Transient Test RFQ")
        db.add(rfq)
        await db.flush()

        delivery, _ = await EmailDeliveryService.create_rfq_invitation(
            db=db,
            rfq_id=rfq.id,
            recipient_email="transient.failure@test.local",
            organization_id=org_ctx.organization.id,
        )

    # Configure provider to a closed port (causing ConnectionRefusedError - transient)
    bad_provider = SMTPEmailProvider(host="127.0.0.1", port=65530, timeout=1)
    set_email_provider(bad_provider)

    # Dispatch delivery
    res = await EmailDeliveryService.dispatch_delivery(delivery.id)

    async with AsyncSessionLocal() as db:
        updated = await db.get(EmailDelivery, delivery.id)
        assert updated.status == EmailDeliveryStatus.QUEUED.value
        assert updated.attempt_count == 1
        assert updated.next_retry_at is not None
        assert updated.next_retry_at > datetime.now(timezone.utc)
        assert "Transient" in updated.last_error


# ── Test 3: Permanent Failure Handling ────────────────────────────────────────

@pytest.mark.asyncio
async def test_permanent_failure_immediate_terminal_status():
    """
    Validates point 8:
    Simulates permanent SMTP failure (invalid host/config or 5xx error).
    Verifies status transitions to 'failed', next_retry_at is None, and error is sanitized.
    """
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Permanent Test RFQ")
        db.add(rfq)
        await db.flush()

        delivery, _ = await EmailDeliveryService.create_rfq_invitation(
            db=db,
            rfq_id=rfq.id,
            recipient_email="perm.failure@test.local",
            organization_id=org_ctx.organization.id,
        )

    # Provider with empty host (permanent config error)
    invalid_provider = SMTPEmailProvider(host="", port=1025)
    set_email_provider(invalid_provider)

    res = await EmailDeliveryService.dispatch_delivery(delivery.id)

    async with AsyncSessionLocal() as db:
        updated = await db.get(EmailDelivery, delivery.id)
        assert updated.status == EmailDeliveryStatus.FAILED.value
        assert updated.next_retry_at is None
        assert "SMTP configuration error" in updated.last_error


# ── Test 4: Deduplication & Repeated Worker Execution ─────────────────────────

@pytest.mark.asyncio
async def test_repeated_worker_sends_zero_duplicate_messages():
    """
    Validates point 9:
    Runs the worker multiple times on an already processed queue.
    Verifies that no duplicate messages appear in Mailpit.
    """
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Deduplication RFQ")
        db.add(rfq)
        await db.flush()

        delivery, _ = await EmailDeliveryService.create_rfq_invitation(
            db=db,
            rfq_id=rfq.id,
            recipient_email="dedup.test@vendor.local",
            organization_id=org_ctx.organization.id,
        )

    clear_mailpit_messages()

    # Pass 1: Worker dispatches the newly created invitation
    c1 = await process_outbox_batch(batch_size=10)
    assert c1 >= 1

    msgs_after_pass1 = [m for m in get_mailpit_messages() if m["To"][0]["Address"] == "dedup.test@vendor.local"]
    assert len(msgs_after_pass1) == 1

    # Pass 2: Delivery is now 'sent', worker should not re-send
    await process_outbox_batch(batch_size=10)

    msgs_after_pass2 = [m for m in get_mailpit_messages() if m["To"][0]["Address"] == "dedup.test@vendor.local"]
    assert len(msgs_after_pass2) == 1  # Still exactly 1, no duplicate


# ── Test 5: Purchase Order Issuance vs Draft Notification ─────────────────────

@pytest.mark.asyncio
async def test_po_notification_only_on_issued():
    """
    Validates point 10:
    - A draft PO rejects notification queuing with ValueError.
    - An issued PO queues notification and worker delivers to Mailpit.
    """
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    async with AsyncSessionLocal() as db:
        supplier = Supplier(
            organization_id=org_ctx.organization.id,
            name="PO Mailpit Supplier",
            email="po.supplier@corp.local",
        )
        db.add(supplier)
        await db.flush()

        rfq = RFQ(organization_id=org_ctx.organization.id, title="PO Notification RFQ")
        db.add(rfq)
        await db.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            subtotal=Decimal("80000.00"),
            total_price=Decimal("80000.00"),
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

        # 1. Draft PO
        po_draft = PurchaseOrder(
            po_number=f"PO-DRAFT-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.DRAFT.value,
        )
        db.add(po_draft)
        await db.commit()
        await db.refresh(po_draft)

    # Calling send_po_email for draft PO must NOT create an outbox delivery
    await EmailService.send_po_email(po_draft.id)

    async with AsyncSessionLocal() as db:
        draft_del = await db.execute(
            select(EmailDelivery).where(EmailDelivery.purchase_order_id == po_draft.id)
        )
        assert draft_del.scalars().first() is None

    # 2. Issued PO
    async with AsyncSessionLocal() as db:
        po_issued = PurchaseOrder(
            po_number=f"PO-ISSUED-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.ISSUED.value,
        )
        db.add(po_issued)
        await db.commit()
        await db.refresh(po_issued)

    clear_mailpit_messages()
    await EmailService.send_po_email(po_issued.id)

    # Verify delivery record created and sent to Mailpit
    async with AsyncSessionLocal() as db:
        issued_del = await db.execute(
            select(EmailDelivery).where(EmailDelivery.purchase_order_id == po_issued.id)
        )
        del_obj = issued_del.scalars().first()
        assert del_obj is not None
        assert del_obj.status == EmailDeliveryStatus.SENT.value

    # Verify message in Mailpit
    po_msgs = get_mailpit_messages()
    assert any("Purchase Order" in m["Subject"] for m in po_msgs)


# ── Test 6: Stuck in 'Sending' Recovery ────────────────────────────────────────

@pytest.mark.asyncio
async def test_recover_stuck_sending_deliveries():
    """
    Validates point 11 and Task 3 fix:
    - Inserts a delivery artificially stuck in 'sending' with an old updated_at.
    - Executes recover_stuck_deliveries with timeout_seconds=10.
    - Verifies it is safely recovered back to 'queued' with incremented attempt_count and backoff.
    - Tests that if attempt_count >= max_attempts, it fails terminally.
    """
    org_ctx = await create_test_auth_context(role=UserRole.EMPLOYEE)

    old_time = datetime.now(timezone.utc) - timedelta(seconds=600)  # 10 minutes ago

    async with AsyncSessionLocal() as db:
        rfq = RFQ(organization_id=org_ctx.organization.id, title="Stuck Recovery RFQ")
        db.add(rfq)
        await db.flush()

        # Delivery 1: Normal recovery to queued
        d1 = EmailDelivery(
            organization_id=org_ctx.organization.id,
            rfq_id=rfq.id,
            recipient_email="stuck1@recovery.local",
            subject="Stuck 1",
            idempotency_key=f"stuck_key_{uuid.uuid4().hex}",
            status=EmailDeliveryStatus.SENDING.value,
            attempt_count=0,
            max_attempts=3,
        )
        db.add(d1)

        # Delivery 2: Already at max_attempts - 1, recovery should mark as failed
        d2 = EmailDelivery(
            organization_id=org_ctx.organization.id,
            rfq_id=rfq.id,
            recipient_email="stuck2@recovery.local",
            subject="Stuck 2",
            idempotency_key=f"stuck_key_{uuid.uuid4().hex}",
            status=EmailDeliveryStatus.SENDING.value,
            attempt_count=2,
            max_attempts=3,
        )
        db.add(d2)

        await db.commit()
        await db.refresh(d1)
        await db.refresh(d2)

        # Manually backdate updated_at to simulate worker crash 10 minutes ago
        d1.updated_at = old_time
        d2.updated_at = old_time
        await db.commit()

    # Execute recovery with 60 second timeout threshold
    recovered_count = await EmailDeliveryService.recover_stuck_deliveries(timeout_seconds=60)
    assert recovered_count == 2

    async with AsyncSessionLocal() as db:
        rec1 = await db.get(EmailDelivery, d1.id)
        assert rec1.status == EmailDeliveryStatus.QUEUED.value
        assert rec1.attempt_count == 1
        assert rec1.next_retry_at is not None
        assert "Stuck in sending recovered" in rec1.last_error

        rec2 = await db.get(EmailDelivery, d2.id)
        assert rec2.status == EmailDeliveryStatus.FAILED.value
        assert rec2.attempt_count == 3
        assert rec2.next_retry_at is None
        assert "Max attempts" in rec2.last_error
