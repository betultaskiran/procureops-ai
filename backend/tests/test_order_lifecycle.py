import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.analysis import Analysis, Approval
from app.models.audit import AuditEvent
from app.models.order import (
    IssueSeverity,
    IssueType,
    POQualityIssue,
    PurchaseOrder,
    PurchaseOrderStatus,
    QualityIssueStatus,
)
from app.models.quote import Quote
from app.models.rfq import RFQ
from app.models.supplier import Supplier, SupplierHistory
from app.models.user import UserRole
from app.services.supplier.performance import SupplierPerformanceService
from tests.auth_helper import create_test_auth_context


async def _create_test_order_fixture(
    session,
    org_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    initial_status: str = "issued",
    delivery_days: int = 10,
    quote_amount: Decimal = Decimal("25000.00"),
    currency: str = "TRY",
) -> tuple[PurchaseOrder, Quote, RFQ, Supplier]:
    """Helper to set up an isolated RFQ, Supplier, Quote, Approval, and PO."""
    supplier = Supplier(
        organization_id=org_id,
        name=f"Test Lifecycle Supplier {uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    session.add(supplier)
    await session.flush()

    rfq = RFQ(
        organization_id=org_id,
        title=f"Test Lifecycle RFQ {uuid.uuid4().hex[:6]}",
    )
    session.add(rfq)
    await session.flush()

    quote = Quote(
        rfq_id=rfq.id,
        supplier_id=supplier.id,
        subtotal=quote_amount,
        total_price=quote_amount,
        currency=currency,
        delivery_days=delivery_days,
    )
    session.add(quote)
    await session.flush()

    analysis = Analysis(rfq_id=rfq.id, status="completed")
    session.add(analysis)
    await session.flush()

    approval = Approval(
        analysis_id=analysis.id,
        reviewer_id=reviewer_id,
        status="approved",
        selected_quote_id=quote.id,
    )
    session.add(approval)
    await session.flush()

    expected_delivery = date.today() + timedelta(days=delivery_days)
    po = PurchaseOrder(
        po_number=f"PO-TEST-{uuid.uuid4().hex[:8].upper()}",
        quote_id=quote.id,
        approval_id=approval.id,
        status=initial_status,
        expected_delivery_date=expected_delivery,
    )
    session.add(po)
    await session.commit()
    await session.refresh(po)
    return po, quote, rfq, supplier


@pytest.mark.asyncio
async def test_po_get_detail_and_allowed_actions():
    """1. Test GET /api/v1/orders/{po_id} returns enriched details and dynamic allowed_actions."""
    mgr_auth = await create_test_auth_context(role=UserRole.MANAGER)

    async with AsyncSessionLocal() as session:
        po, quote, rfq, supplier = await _create_test_order_fixture(
            session, mgr_auth.organization.id, mgr_auth.user.id, initial_status="issued"
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=mgr_auth.headers) as client:
        res = await client.get(f"/api/v1/orders/{po.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(po.id)
        assert data["po_number"] == po.po_number
        assert data["status"] == "issued"
        assert data["rfq_title"] == rfq.title
        assert data["supplier_name"] == supplier.name
        assert data["currency"] == "TRY"
        assert Decimal(str(data["quoted_amount"])) == Decimal("25000.00")
        assert "deliver" in data["allowed_actions"]
        assert "cancel" in data["allowed_actions"]
        assert "add_quality_issue" in data["allowed_actions"]


@pytest.mark.asyncio
async def test_po_delivery_transition_success():
    """2. Test valid transition from 'issued' to 'delivered' and check SupplierHistory sync & audit."""
    mgr_auth = await create_test_auth_context(role=UserRole.MANAGER)

    async with AsyncSessionLocal() as session:
        po, quote, rfq, supplier = await _create_test_order_fixture(
            session, mgr_auth.organization.id, mgr_auth.user.id, initial_status="issued"
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=mgr_auth.headers) as client:
        delivery_date = str(date.today() + timedelta(days=2))
        res = await client.post(
            f"/api/v1/orders/{po.id}/deliver",
            json={
                "actual_delivery_date": delivery_date,
                "delivery_notes": "Delivered to warehouse dock 3 in good condition.",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "delivered"
        assert data["actual_delivery_date"] == delivery_date
        assert "Teslimat Notu" in data["delivery_notes"]
        assert "complete" in data["allowed_actions"]
        assert "deliver" not in data["allowed_actions"]

    # Verify SupplierHistory and AuditEvent in DB
    async with AsyncSessionLocal() as session:
        sh_res = await session.execute(select(SupplierHistory).where(SupplierHistory.purchase_order_id == po.id))
        sh = sh_res.scalar_one_or_none()
        assert sh is not None
        assert str(sh.delivered_date) == delivery_date
        assert sh.delay_days is not None

        audit_res = await session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == po.id,
                AuditEvent.event_type == "po_delivered",
            )
        )
        audit = audit_res.scalar_one_or_none()
        assert audit is not None
        assert audit.actor_id == mgr_auth.user.id


@pytest.mark.asyncio
async def test_po_complete_transition_success():
    """3. Test valid transition from 'delivered' to 'completed' with final amount and SupplierHistory sync."""
    mgr_auth = await create_test_auth_context(role=UserRole.MANAGER)

    async with AsyncSessionLocal() as session:
        po, quote, rfq, supplier = await _create_test_order_fixture(
            session, mgr_auth.organization.id, mgr_auth.user.id, initial_status="issued"
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=mgr_auth.headers) as client:
        # First deliver
        await client.post(f"/api/v1/orders/{po.id}/deliver", json={"actual_delivery_date": str(date.today())})

        # Then complete with final invoice amount
        res = await client.post(
            f"/api/v1/orders/{po.id}/complete",
            json={
                "final_amount": 24200.50,
                "completion_notes": "Invoice matched PO and quality inspection passed.",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert Decimal(str(data["final_amount"])) == Decimal("24200.50")
        assert "add_quality_issue" in data["allowed_actions"]
        assert "complete" not in data["allowed_actions"]
        assert "cancel" not in data["allowed_actions"]

    # Verify SupplierHistory updated in DB
    async with AsyncSessionLocal() as session:
        sh_res = await session.execute(select(SupplierHistory).where(SupplierHistory.purchase_order_id == po.id))
        sh = sh_res.scalar_one_or_none()
        assert sh is not None
        assert Decimal(str(sh.total_amount)) == Decimal("24200.50")

        audit_res = await session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == po.id,
                AuditEvent.event_type == "po_completed",
            )
        )
        audit = audit_res.scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_po_invalid_state_transitions():
    """4. Test strict state machine guards: invalid transitions return HTTP 400 Bad Request."""
    mgr_auth = await create_test_auth_context(role=UserRole.MANAGER)

    async with AsyncSessionLocal() as session:
        po, quote, rfq, supplier = await _create_test_order_fixture(
            session, mgr_auth.organization.id, mgr_auth.user.id, initial_status="issued"
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=mgr_auth.headers) as client:
        # 1. Attempting to complete directly from 'issued' (before delivery) must fail
        complete_invalid = await client.post(f"/api/v1/orders/{po.id}/complete", json={"final_amount": 20000})
        assert complete_invalid.status_code == 400
        assert "teslim edilmiş" in complete_invalid.json()["detail"].lower()

        # 2. Deliver the order
        await client.post(f"/api/v1/orders/{po.id}/deliver", json={})

        # 3. Delivering an already delivered order must fail
        deliver_again = await client.post(f"/api/v1/orders/{po.id}/deliver", json={})
        assert deliver_again.status_code == 400

        # 4. Attempting to complete with negative final amount must fail
        neg_amount = await client.post(f"/api/v1/orders/{po.id}/complete", json={"final_amount": -100})
        assert neg_amount.status_code in (400, 422)

        # 5. Complete order legitimately
        comp_res = await client.post(f"/api/v1/orders/{po.id}/complete", json={"final_amount": 25000})
        assert comp_res.status_code == 200

        # 6. Attempting to deliver a completed order must fail
        deliv_completed = await client.post(f"/api/v1/orders/{po.id}/deliver", json={})
        assert deliv_completed.status_code == 400

        # 7. Attempting to cancel a completed order must fail
        cancel_completed = await client.post(f"/api/v1/orders/{po.id}/cancel", json={"reason": "Late regret"})
        assert cancel_completed.status_code == 400
        assert "tamamlanmış" in cancel_completed.json()["detail"].lower()


@pytest.mark.asyncio
async def test_po_cancellation_flow():
    """5. Test cancellation from 'issued' and 'delivered' states."""
    mgr_auth = await create_test_auth_context(role=UserRole.MANAGER)

    # Cancel from issued
    async with AsyncSessionLocal() as session:
        po1, _, _, _ = await _create_test_order_fixture(
            session, mgr_auth.organization.id, mgr_auth.user.id, initial_status="issued"
        )
        po2, _, _, _ = await _create_test_order_fixture(
            session, mgr_auth.organization.id, mgr_auth.user.id, initial_status="issued"
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=mgr_auth.headers) as client:
        # Cancel po1 from issued
        res1 = await client.post(
            f"/api/v1/orders/{po1.id}/cancel",
            json={"reason": "Project scope changed by procurement committee."},
        )
        assert res1.status_code == 200
        assert res1.json()["status"] == "cancelled"
        assert res1.json()["cancellation_reason"] == "Project scope changed by procurement committee."

        # Cancelling an already cancelled PO must fail
        res1_repeat = await client.post(f"/api/v1/orders/{po1.id}/cancel", json={"reason": "Second cancel"})
        assert res1_repeat.status_code == 400

        # Deliver po2, then cancel from delivered
        await client.post(f"/api/v1/orders/{po2.id}/deliver", json={})
        res2 = await client.post(
            f"/api/v1/orders/{po2.id}/cancel",
            json={"reason": "Items arrived severely damaged beyond repair."},
        )
        assert res2.status_code == 200
        assert res2.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_po_quality_issues_logging_and_supplier_sync():
    """6. Test logging quality issues and verifying their reflection in SupplierPerformanceService."""
    mgr_auth = await create_test_auth_context(role=UserRole.MANAGER)

    async with AsyncSessionLocal() as session:
        po, quote, rfq, supplier = await _create_test_order_fixture(
            session, mgr_auth.organization.id, mgr_auth.user.id, initial_status="issued"
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=mgr_auth.headers) as client:
        # 1. Add quality issue
        issue_res = await client.post(
            f"/api/v1/orders/{po.id}/quality-issues",
            json={
                "issue_type": "defect",
                "severity": "critical",
                "rejection_count": 3,
                "description": "3 units had cracked casing upon inspection.",
            },
        )
        assert issue_res.status_code == 200
        issue_data = issue_res.json()
        assert issue_data["issue_type"] == "defect"
        assert issue_data["severity"] == "critical"
        assert issue_data["rejection_count"] == 3
        assert issue_data["reported_by_name"] == mgr_auth.user.full_name

        # 2. Add second issue (late delivery note)
        issue2_res = await client.post(
            f"/api/v1/orders/{po.id}/quality-issues",
            json={
                "issue_type": "missing_items",
                "severity": "medium",
                "rejection_count": 1,
                "description": "1 package of accessories missing from delivery.",
            },
        )
        assert issue2_res.status_code == 200

        # 3. List quality issues
        list_res = await client.get(f"/api/v1/orders/{po.id}/quality-issues")
        assert list_res.status_code == 200
        issues_list = list_res.json()
        assert len(issues_list) == 2

        # 4. Invalid issue type returns 400
        bad_type = await client.post(
            f"/api/v1/orders/{po.id}/quality-issues",
            json={"issue_type": "unknown_type", "severity": "low", "description": "test", "rejection_count": 0},
        )
        assert bad_type.status_code == 400

        # 5. Invalid severity returns 400
        bad_sev = await client.post(
            f"/api/v1/orders/{po.id}/quality-issues",
            json={"issue_type": "defect", "severity": "super_critical", "description": "test", "rejection_count": 0},
        )
        assert bad_sev.status_code == 400

    # 6. Verify SupplierPerformanceService reflects the live PO quality issues
    async with AsyncSessionLocal() as session:
        perf_service = SupplierPerformanceService(session)
        perf = await perf_service.get_supplier_performance(supplier)

        assert perf.quality_metrics.is_tracked is True
        assert perf.quality_metrics.total_quality_issues == 2
        assert perf.quality_metrics.total_rejections == 4

        # Check get_supplier_history
        history = await perf_service.get_supplier_history(supplier)
        assert len(history.items) >= 1
        po_item = next(it for it in history.items if it.order_reference == po.po_number)
        assert po_item.quality_issues == 2
        assert po_item.rejection_count == 4


@pytest.mark.asyncio
async def test_po_rbac_enforcement():
    """7. Test RBAC: Employees cannot mutate orders; Managers and Admins can."""
    emp_auth = await create_test_auth_context(role=UserRole.EMPLOYEE)
    mgr_auth = await create_test_auth_context(role=UserRole.MANAGER, org_id=emp_auth.organization.id)

    async with AsyncSessionLocal() as session:
        po, _, _, _ = await _create_test_order_fixture(
            session, emp_auth.organization.id, mgr_auth.user.id, initial_status="issued"
        )

    transport = ASGITransport(app=app)
    # Employee attempts
    async with AsyncClient(transport=transport, base_url="http://test", headers=emp_auth.headers) as client:
        # GET is allowed for authenticated employee
        get_res = await client.get(f"/api/v1/orders/{po.id}")
        assert get_res.status_code == 200
        assert get_res.json()["allowed_actions"] == []  # No mutation allowed for employee

        # Deliver forbidden
        deliv_res = await client.post(f"/api/v1/orders/{po.id}/deliver", json={})
        assert deliv_res.status_code == 403

        # Complete forbidden
        comp_res = await client.post(f"/api/v1/orders/{po.id}/complete", json={})
        assert comp_res.status_code == 403

        # Cancel forbidden
        canc_res = await client.post(f"/api/v1/orders/{po.id}/cancel", json={"reason": "No rights"})
        assert canc_res.status_code == 403

        # Quality issue forbidden
        qi_res = await client.post(
            f"/api/v1/orders/{po.id}/quality-issues",
            json={"issue_type": "defect", "description": "Denied issue", "rejection_count": 0},
        )
        assert qi_res.status_code == 403

    # Unauthenticated caller
    async with AsyncClient(transport=transport, base_url="http://test") as unauth_client:
        unauth_res = await unauth_client.get(f"/api/v1/orders/{po.id}")
        assert unauth_res.status_code == 401


@pytest.mark.asyncio
async def test_po_tenant_isolation():
    """8. Test tenant isolation: cross-tenant order access/mutations return 404 Not Found."""
    org_a_mgr = await create_test_auth_context(role=UserRole.MANAGER)
    org_b_mgr = await create_test_auth_context(role=UserRole.MANAGER)

    async with AsyncSessionLocal() as session:
        po_a, _, _, _ = await _create_test_order_fixture(
            session, org_a_mgr.organization.id, org_a_mgr.user.id, initial_status="issued"
        )

    transport = ASGITransport(app=app)
    # Org B manager attempts to interact with Org A's purchase order
    async with AsyncClient(transport=transport, base_url="http://test", headers=org_b_mgr.headers) as client:
        # Cross-tenant GET -> 404
        assert (await client.get(f"/api/v1/orders/{po_a.id}")).status_code == 404

        # Cross-tenant Deliver -> 404
        assert (await client.post(f"/api/v1/orders/{po_a.id}/deliver", json={})).status_code == 404

        # Cross-tenant Complete -> 404
        assert (await client.post(f"/api/v1/orders/{po_a.id}/complete", json={})).status_code == 404

        # Cross-tenant Cancel -> 404
        assert (await client.post(f"/api/v1/orders/{po_a.id}/cancel", json={"reason": "Cross-tenant"})).status_code == 404

        # Cross-tenant Quality issue create -> 404
        assert (await client.post(
            f"/api/v1/orders/{po_a.id}/quality-issues",
            json={"issue_type": "defect", "description": "Hacked", "rejection_count": 0},
        )).status_code == 404

        # Cross-tenant Quality issue list -> 404
        assert (await client.get(f"/api/v1/orders/{po_a.id}/quality-issues")).status_code == 404


@pytest.mark.asyncio
async def test_po_quality_issue_resolution_and_e2e_lifecycle():
    """
    9. Complete E2E PO Lifecycle with Quality Issue Resolution:
       - Deliver order.
       - Log critical quality issue with rejections.
       - Verify completion is BLOCKED while critical issue is open.
       - Resolve the critical issue via PATCH.
       - Log and dismiss a non-critical issue via PATCH.
       - Complete order with final amount.
       - Verify SupplierPerformanceService reflects only non-dismissed issues.
    """
    mgr_auth = await create_test_auth_context(role=UserRole.MANAGER)

    async with AsyncSessionLocal() as session:
        po, quote, rfq, supplier = await _create_test_order_fixture(
            session,
            mgr_auth.organization.id,
            mgr_auth.user.id,
            initial_status="issued",
            delivery_days=7,
            quote_amount=Decimal("30000.00"),
            currency="TRY",
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=mgr_auth.headers) as client:
        # Step 1: Record delivery (1 day late)
        actual_deliv = str(date.today() + timedelta(days=8))
        deliv_res = await client.post(
            f"/api/v1/orders/{po.id}/deliver",
            json={
                "actual_delivery_date": actual_deliv,
                "delivery_notes": "Delivered with minor physical packaging wear.",
            },
        )
        assert deliv_res.status_code == 200
        assert deliv_res.json()["status"] == "delivered"

        # Step 2: Record a critical quality issue (3 defective units)
        crit_res = await client.post(
            f"/api/v1/orders/{po.id}/quality-issues",
            json={
                "issue_type": "defect",
                "severity": "critical",
                "rejection_count": 3,
                "description": "3 units arrived completely defective and non-functional.",
            },
        )
        assert crit_res.status_code == 200
        crit_issue = crit_res.json()
        assert crit_issue["status"] == "open"
        assert crit_issue["severity"] == "critical"

        # Step 3: Record a medium quality issue (1 damaged box)
        med_res = await client.post(
            f"/api/v1/orders/{po.id}/quality-issues",
            json={
                "issue_type": "damaged",
                "severity": "medium",
                "rejection_count": 1,
                "description": "Outer carton torn; contents inspected.",
            },
        )
        assert med_res.status_code == 200
        med_issue = med_res.json()

        # Step 4: Attempt to complete PO while critical issue is OPEN -> MUST FAIL with 400
        blocked_comp = await client.post(
            f"/api/v1/orders/{po.id}/complete",
            json={"final_amount": 29000.00, "completion_notes": "Premature attempt"},
        )
        assert blocked_comp.status_code == 400
        assert "kritik kalite sorunu" in blocked_comp.json()["detail"].lower()

        # Step 5: Resolve the critical issue via PATCH
        resolve_res = await client.patch(
            f"/api/v1/orders/{po.id}/quality-issues/{crit_issue['id']}",
            json={
                "status": "resolved",
                "resolution_notes": "Supplier supplied 3 tested replacement units under warranty on next day.",
            },
        )
        assert resolve_res.status_code == 200
        resolved_data = resolve_res.json()
        assert resolved_data["status"] == "resolved"
        assert resolved_data["resolved_at"] is not None
        assert "replacement units" in resolved_data["resolution_notes"]

        # Step 6: Dismiss the medium issue via PATCH (e.g. false alarm / carrier issue)
        dismiss_res = await client.patch(
            f"/api/v1/orders/{po.id}/quality-issues/{med_issue['id']}",
            json={
                "status": "dismissed",
                "resolution_notes": "Inspection confirmed items inside were fully intact.",
            },
        )
        assert dismiss_res.status_code == 200
        dismissed_data = dismiss_res.json()
        assert dismissed_data["status"] == "dismissed"

        # Step 7: Now complete the PO -> MUST SUCCEED
        final_comp = await client.post(
            f"/api/v1/orders/{po.id}/complete",
            json={
                "final_amount": 29500.00,
                "completion_notes": "Final invoice verified and signed off.",
            },
        )
        assert final_comp.status_code == 200
        po_data = final_comp.json()
        assert po_data["status"] == "completed"
        assert Decimal(str(po_data["final_amount"])) == Decimal("29500.00")

    # Step 8: Verify SupplierPerformanceService metrics
    async with AsyncSessionLocal() as session:
        perf_service = SupplierPerformanceService(session)
        perf = await perf_service.get_supplier_performance(supplier)

        # Order counts
        assert perf.order_summary.completed_orders_count == 1
        assert perf.order_summary.total_orders_count == 1

        # Financial summary: matches final_amount
        assert "TRY" in perf.financial_summary
        fin = perf.financial_summary["TRY"]
        assert fin.total_spend == Decimal("29500.00")
        assert fin.final_amount_orders_count == 1

        # Quality metrics:
        # Dismissed issue is EXCLUDED!
        # Only the resolved critical issue is counted: total_issues=1, total_rejections=3
        assert perf.quality_metrics.is_tracked is True
        assert perf.quality_metrics.total_quality_issues == 1
        assert perf.quality_metrics.total_rejections == 3


@pytest.mark.asyncio
async def test_po_quality_issue_patch_rbac_and_tenant_isolation():
    """10. Test RBAC and Tenant Isolation for PATCH /quality-issues/{issue_id}."""
    emp_auth = await create_test_auth_context(role=UserRole.EMPLOYEE)
    mgr_a = await create_test_auth_context(role=UserRole.MANAGER, org_id=emp_auth.organization.id)
    mgr_b = await create_test_auth_context(role=UserRole.MANAGER)

    async with AsyncSessionLocal() as session:
        po, _, _, supplier = await _create_test_order_fixture(
            session, mgr_a.organization.id, mgr_a.user.id, initial_status="issued"
        )
        issue = POQualityIssue(
            organization_id=mgr_a.organization.id,
            purchase_order_id=po.id,
            supplier_id=supplier.id,
            reported_by_id=mgr_a.user.id,
            issue_type="defect",
            severity="medium",
            description="Test issue",
            rejection_count=1,
        )
        session.add(issue)
        await session.commit()
        await session.refresh(issue)

    transport = ASGITransport(app=app)

    # 1. Employee cannot PATCH (HTTP 403)
    async with AsyncClient(transport=transport, base_url="http://test", headers=emp_auth.headers) as emp_client:
        res = await emp_client.patch(
            f"/api/v1/orders/{po.id}/quality-issues/{issue.id}",
            json={"status": "resolved"},
        )
        assert res.status_code == 403

    # 2. Org B Manager cannot PATCH Org A's issue (HTTP 404)
    async with AsyncClient(transport=transport, base_url="http://test", headers=mgr_b.headers) as b_client:
        res = await b_client.patch(
            f"/api/v1/orders/{po.id}/quality-issues/{issue.id}",
            json={"status": "resolved"},
        )
        assert res.status_code == 404

    # 3. Org A Manager with invalid status gets 400
    async with AsyncClient(transport=transport, base_url="http://test", headers=mgr_a.headers) as a_client:
        res = await a_client.patch(
            f"/api/v1/orders/{po.id}/quality-issues/{issue.id}",
            json={"status": "invalid_status_xyz"},
        )
        assert res.status_code == 400

