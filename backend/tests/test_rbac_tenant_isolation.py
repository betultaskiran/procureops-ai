"""
backend/tests/test_rbac_tenant_isolation.py

Comprehensive test suite verifying:
1. Complete unauthenticated request rejection (401 Unauthorized across all endpoints).
2. Strict RBAC role enforcement (Viewer, Employee, Manager, Admin matrix).
3. Organization-level multi-tenant isolation across RFQs, Quotes, Suppliers, Analyses, Dashboard.
4. Non-disclosing 404 responses for cross-tenant resource access attempts (preventing ID enumeration).
5. Immunity against query parameter and request body tenant spoofing.
"""

from decimal import Decimal
from unittest.mock import patch
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.analysis import Analysis, AnalysisStatus, ApprovalStatus
from app.models.order import PurchaseOrder
from app.models.quote import Quote, QuoteItem
from app.models.rfq import RFQ, RFQItem, RFQStatus
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services.agent.schemas import AgentRecommendationSchema
from app.services.agent.service import AgentService
from tests.auth_helper import create_test_auth_context


def get_mock_agent_output(recommended_quote_id: uuid.UUID | None = None):
    return AgentRecommendationSchema(
        recommended_quote_id=recommended_quote_id,
        justification="En uygun teklif şartları sağlamaktadır.",
        trade_off_analysis="Fiyat ve teslimat dengesi optimaldir.",
        risk_factors=["Tedarikçi geçmişi temizdir."],
        confidence_score=95,
        is_human_review_required=False,
    )


# ── 1. Unauthenticated Request Rejection ───────────────────────────────────────

@pytest.mark.asyncio
async def test_unauthenticated_requests_fail_with_401():
    """Verify that all protected endpoints require valid bearer tokens and return 401."""
    transport = ASGITransport(app=app)
    fake_id = uuid.uuid4()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # RFQs
        assert (await client.get("/api/v1/rfqs")).status_code == 401
        assert (await client.post("/api/v1/rfqs", json={"title": "Test"})).status_code == 401
        assert (await client.get(f"/api/v1/rfqs/{fake_id}")).status_code == 401
        assert (await client.delete(f"/api/v1/rfqs/{fake_id}")).status_code == 401
        assert (await client.post(f"/api/v1/rfqs/{fake_id}/cancel", json={"reason": "Cancel"})).status_code == 401

        # Suppliers
        assert (await client.get("/api/v1/suppliers")).status_code == 401
        assert (await client.post("/api/v1/suppliers", json={"name": "Test Sup"})).status_code == 401
        assert (await client.get(f"/api/v1/suppliers/{fake_id}/performance")).status_code == 401
        assert (await client.get(f"/api/v1/suppliers/{fake_id}/history")).status_code == 401

        # Policies
        assert (await client.get("/api/v1/policies")).status_code == 401

        # Analyses
        assert (await client.post(f"/api/v1/rfqs/{fake_id}/analyze", json={})).status_code == 401
        assert (await client.get(f"/api/v1/rfqs/{fake_id}/analysis")).status_code == 401
        assert (await client.post(f"/api/v1/analyses/{fake_id}/review", json={"status": "approved"})).status_code == 401

        # Dashboard
        assert (await client.get("/api/v1/dashboard/recent-rfqs")).status_code == 401


# ── 2. RBAC Role Matrix: Viewer ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_viewer_role_permissions():
    """
    Viewer role:
    - Allowed: Read-only operations (list RFQs, get RFQ, list suppliers, view dashboard).
    - Denied (403): Any mutation, creation, analysis, deletion, approval.
    """
    admin_ctx = await create_test_auth_context(role=UserRole.ADMIN, org_name="Viewer Test Org")
    viewer_ctx = await create_test_auth_context(
        role=UserRole.VIEWER,
        org_id=admin_ctx.organization.id,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Admin creates an RFQ for the organization
        rfq_res = await client.post(
            "/api/v1/rfqs",
            json={"title": "Viewer Accessible RFQ", "budget": 10000},
            headers=admin_ctx.headers,
        )
        assert rfq_res.status_code == 201
        rfq_id = rfq_res.json()["id"]

        # Viewer can read RFQs
        list_res = await client.get("/api/v1/rfqs", headers=viewer_ctx.headers)
        assert list_res.status_code == 200
        assert any(item["id"] == rfq_id for item in list_res.json()["items"])

        detail_res = await client.get(f"/api/v1/rfqs/{rfq_id}", headers=viewer_ctx.headers)
        assert detail_res.status_code == 200

        dash_res = await client.get("/api/v1/dashboard/recent-rfqs", headers=viewer_ctx.headers)
        assert dash_res.status_code == 200

        # Viewer CANNOT create RFQ (403)
        rfq_create_denied = await client.post(
            "/api/v1/rfqs",
            json={"title": "Viewer Denied RFQ"},
            headers=viewer_ctx.headers,
        )
        assert rfq_create_denied.status_code == 403

        # Viewer CANNOT create Supplier (403)
        sup_create_denied = await client.post(
            "/api/v1/suppliers",
            json={"name": "Viewer Denied Supplier"},
            headers=viewer_ctx.headers,
        )
        assert sup_create_denied.status_code == 403

        # Viewer CANNOT delete RFQ (403)
        rfq_del_denied = await client.delete(f"/api/v1/rfqs/{rfq_id}", headers=viewer_ctx.headers)
        assert rfq_del_denied.status_code == 403

        # Viewer CANNOT cancel RFQ (403)
        rfq_cancel_denied = await client.post(
            f"/api/v1/rfqs/{rfq_id}/cancel",
            json={"reason": "Viewer attempting cancel"},
            headers=viewer_ctx.headers,
        )
        assert rfq_cancel_denied.status_code == 403

        # Viewer CANNOT run analysis (403)
        analysis_denied = await client.post(
            f"/api/v1/rfqs/{rfq_id}/analyze",
            json={},
            headers=viewer_ctx.headers,
        )
        assert analysis_denied.status_code == 403


# ── 3. RBAC Role Matrix: Employee ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_employee_role_permissions():
    """
    Employee role:
    - Allowed: Create RFQs, create suppliers, upload quotes, run analysis.
    - Denied (403): RFQ cancellation, RFQ deletion, Analysis review/approval, Policy management.
    """
    admin_ctx = await create_test_auth_context(role=UserRole.ADMIN, org_name="Employee Test Org")
    emp_ctx = await create_test_auth_context(
        role=UserRole.EMPLOYEE,
        org_id=admin_ctx.organization.id,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Employee CAN create RFQ (201)
        rfq_res = await client.post(
            "/api/v1/rfqs",
            json={
                "title": "Employee Created RFQ",
                "budget": 50000,
                "items": [{"description": "Laptop", "quantity": 5}],
            },
            headers=emp_ctx.headers,
        )
        assert rfq_res.status_code == 201
        rfq_id = rfq_res.json()["id"]

        # Employee CAN create Supplier (201)
        sup_res = await client.post(
            "/api/v1/suppliers",
            json={"name": "Employee Created Supplier"},
            headers=emp_ctx.headers,
        )
        assert sup_res.status_code == 201
        sup_id = sup_res.json()["id"]

        # Employee CAN archive/unarchive RFQ (200)
        arc_res = await client.post(f"/api/v1/rfqs/{rfq_id}/archive", headers=emp_ctx.headers)
        assert arc_res.status_code == 200
        unarc_res = await client.post(f"/api/v1/rfqs/{rfq_id}/unarchive", headers=emp_ctx.headers)
        assert unarc_res.status_code == 200

        # Employee CANNOT cancel RFQ (403)
        cancel_denied = await client.post(
            f"/api/v1/rfqs/{rfq_id}/cancel",
            json={"reason": "Employee attempting cancel"},
            headers=emp_ctx.headers,
        )
        assert cancel_denied.status_code == 403

        # Employee CANNOT delete RFQ (403)
        delete_denied = await client.delete(f"/api/v1/rfqs/{rfq_id}", headers=emp_ctx.headers)
        assert delete_denied.status_code == 403

        # Employee CANNOT review/approve analysis (403)
        review_denied = await client.post(
            f"/api/v1/analyses/{uuid.uuid4()}/review",
            json={"status": "approved"},
            headers=emp_ctx.headers,
        )
        assert review_denied.status_code == 403

        # Employee CANNOT upload policy (403)
        policy_denied = await client.post(
            "/api/v1/policies/upload",
            files={"file": ("policy.txt", b"Test policy content", "text/plain")},
            headers=emp_ctx.headers,
        )
        assert policy_denied.status_code == 403


# ── 4. RBAC Role Matrix: Manager ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manager_role_permissions():
    """
    Manager role:
    - Allowed: Create RFQ, cancel RFQ, delete RFQ, approve analysis.
    - Denied (403): Policy management (upload/delete/reindex is Admin only).
    """
    admin_ctx = await create_test_auth_context(role=UserRole.ADMIN, org_name="Manager Test Org")
    mgr_ctx = await create_test_auth_context(
        role=UserRole.MANAGER,
        org_id=admin_ctx.organization.id,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Manager CAN create RFQ
        rfq_res = await client.post(
            "/api/v1/rfqs",
            json={"title": "Manager RFQ to Cancel", "budget": 20000},
            headers=mgr_ctx.headers,
        )
        assert rfq_res.status_code == 201
        rfq_id = rfq_res.json()["id"]

        # Manager CAN cancel RFQ
        cancel_res = await client.post(
            f"/api/v1/rfqs/{rfq_id}/cancel",
            json={"reason": "Budget cut approved by manager"},
            headers=mgr_ctx.headers,
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == RFQStatus.CANCELLED.value

        # Manager CAN create another RFQ and delete it (can_delete=True)
        rfq2_res = await client.post(
            "/api/v1/rfqs",
            json={"title": "Manager RFQ to Delete", "budget": 15000},
            headers=mgr_ctx.headers,
        )
        rfq2_id = rfq2_res.json()["id"]
        del_res = await client.delete(f"/api/v1/rfqs/{rfq2_id}", headers=mgr_ctx.headers)
        assert del_res.status_code == 200

        # Manager CANNOT upload policy documents (403)
        policy_denied = await client.post(
            "/api/v1/policies/upload",
            files={"file": ("policy.txt", b"Manager policy", "text/plain")},
            headers=mgr_ctx.headers,
        )
        assert policy_denied.status_code == 403


# ── 5. Multi-Tenant Cross-Access Isolation (Non-Disclosing 404s) ───────────────

@pytest.mark.asyncio
async def test_cross_tenant_rfq_isolation():
    """
    Verify that an authenticated user from Organization B cannot access, cancel, or delete
    an RFQ belonging to Organization A.
    Must return HTTP 404 Not Found (non-disclosing, not 403).
    """
    org_a = await create_test_auth_context(role=UserRole.ADMIN, org_name="Tenant Alpha")
    org_b = await create_test_auth_context(role=UserRole.ADMIN, org_name="Tenant Beta")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Org A creates an RFQ
        rfq_a_res = await client.post(
            "/api/v1/rfqs",
            json={"title": "Confidential Alpha RFQ", "budget": 100000},
            headers=org_a.headers,
        )
        assert rfq_a_res.status_code == 201
        rfq_a_id = rfq_a_res.json()["id"]

        # Org B Admin attempts to GET Org A's RFQ -> 404
        get_res = await client.get(f"/api/v1/rfqs/{rfq_a_id}", headers=org_b.headers)
        assert get_res.status_code == 404

        # Org B Admin attempts to cancel Org A's RFQ -> 404
        cancel_res = await client.post(
            f"/api/v1/rfqs/{rfq_a_id}/cancel",
            json={"reason": "Cross-tenant intrusion attempt"},
            headers=org_b.headers,
        )
        assert cancel_res.status_code == 404

        # Org B Admin attempts to delete Org A's RFQ -> 404
        del_res = await client.delete(f"/api/v1/rfqs/{rfq_a_id}", headers=org_b.headers)
        assert del_res.status_code == 404

        # Org B Admin attempts to get POs for Org A's RFQ -> 404
        pos_res = await client.get(f"/api/v1/rfqs/{rfq_a_id}/purchase-orders", headers=org_b.headers)
        assert pos_res.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_supplier_isolation():
    """
    Verify that an authenticated user from Organization B cannot view performance or history
    for a Supplier belonging to Organization A.
    Must return HTTP 404 Not Found.
    """
    org_a = await create_test_auth_context(role=UserRole.ADMIN, org_name="Supplier Iso Alpha")
    org_b = await create_test_auth_context(role=UserRole.ADMIN, org_name="Supplier Iso Beta")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create supplier under Org A
        sup_a_res = await client.post(
            "/api/v1/suppliers",
            json={"name": "Alpha Vendor Ltd", "email": "contact@alphavendor.com"},
            headers=org_a.headers,
        )
        assert sup_a_res.status_code == 201
        sup_a_id = sup_a_res.json()["id"]

        # Org B attempts to access Org A's supplier performance -> 404
        perf_res = await client.get(f"/api/v1/suppliers/{sup_a_id}/performance", headers=org_b.headers)
        assert perf_res.status_code == 404

        # Org B attempts to access Org A's supplier history -> 404
        hist_res = await client.get(f"/api/v1/suppliers/{sup_a_id}/history", headers=org_b.headers)
        assert hist_res.status_code == 404

        # Org B lists suppliers -> Alpha Vendor Ltd must NOT appear
        list_b = await client.get("/api/v1/suppliers", headers=org_b.headers)
        assert list_b.status_code == 200
        assert all(s["id"] != sup_a_id for s in list_b.json())


@pytest.mark.asyncio
async def test_cross_tenant_quote_and_analysis_isolation():
    """
    Verify cross-tenant isolation for Quotes, Analyses, and Reviews:
    Org B cannot see, modify, analyze, or approve Org A's resources.
    """
    org_a = await create_test_auth_context(role=UserRole.ADMIN, org_name="Quote Iso Alpha")
    org_b = await create_test_auth_context(role=UserRole.ADMIN, org_name="Quote Iso Beta")

    async with AsyncSessionLocal() as session:
        # Setup RFQ, Supplier, Quote, Analysis in DB directly under Org A
        rfq_a = RFQ(organization_id=org_a.organization.id, title="Alpha Quote RFQ", status="draft")
        sup_a = Supplier(organization_id=org_a.organization.id, name="Alpha Quote Supplier", is_active=True)
        session.add_all([rfq_a, sup_a])
        await session.flush()

        quote_a = Quote(
            rfq_id=rfq_a.id,
            supplier_id=sup_a.id,
            currency="USD",
            subtotal=1000.0,
            total_price=1000.0,
        )
        session.add(quote_a)
        await session.flush()

        analysis_a = Analysis(
            rfq_id=rfq_a.id,
            status=AnalysisStatus.COMPLETED.value,
        )
        session.add(analysis_a)
        await session.commit()
        await session.refresh(rfq_a)
        await session.refresh(quote_a)
        await session.refresh(analysis_a)

        rfq_a_id = rfq_a.id
        quote_a_id = quote_a.id
        analysis_a_id = analysis_a.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Org B lists quotes for Org A's RFQ -> 404
        list_quotes_res = await client.get(f"/api/v1/rfqs/{rfq_a_id}/quotes", headers=org_b.headers)
        assert list_quotes_res.status_code == 404

        # Org B gets Org A's quote directly -> 404
        get_quote_res = await client.get(f"/api/v1/quotes/{quote_a_id}", headers=org_b.headers)
        assert get_quote_res.status_code == 404

        # Org B deletes Org A's quote -> 404
        del_quote_res = await client.delete(f"/api/v1/quotes/{quote_a_id}", headers=org_b.headers)
        assert del_quote_res.status_code == 404

        # Org B runs analysis on Org A's RFQ -> 404
        analyze_res = await client.post(f"/api/v1/rfqs/{rfq_a_id}/analyze", json={}, headers=org_b.headers)
        assert analyze_res.status_code == 404

        # Org B gets analysis for Org A's RFQ -> 404
        get_analysis_res = await client.get(f"/api/v1/rfqs/{rfq_a_id}/analysis", headers=org_b.headers)
        assert get_analysis_res.status_code == 404

        # Org B reviews/approves Org A's analysis -> 404
        review_res = await client.post(
            f"/api/v1/analyses/{analysis_a_id}/review",
            json={"status": "approved"},
            headers=org_b.headers,
        )
        assert review_res.status_code == 404


# ── 6. Client Parameter Tenant Spoofing Resistance ─────────────────────────────

@pytest.mark.asyncio
async def test_tenant_spoofing_resistance():
    """
    Verify that passing ?organization_id=<other_org> or JSON body organization_id
    is completely ignored and cannot cause data leakage or privilege escalation.
    """
    org_a = await create_test_auth_context(role=UserRole.ADMIN, org_name="Victim Org A")
    org_b = await create_test_auth_context(role=UserRole.ADMIN, org_name="Attacker Org B")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Org A creates an RFQ
        res_a = await client.post(
            "/api/v1/rfqs",
            json={"title": "Victim Org Secret RFQ"},
            headers=org_a.headers,
        )
        rfq_a_id = res_a.json()["id"]

        # Attacker B queries list with ?organization_id=<Org A ID>
        spoofed_list = await client.get(
            f"/api/v1/rfqs?organization_id={org_a.organization.id}",
            headers=org_b.headers,
        )
        assert spoofed_list.status_code == 200
        # Attacker B MUST NOT see Org A's RFQ
        assert all(item["id"] != rfq_a_id for item in spoofed_list.json()["items"])

        # Attacker B sends POST /api/v1/rfqs with organization_id = Org A ID
        spoofed_create = await client.post(
            "/api/v1/rfqs",
            json={
                "title": "Attacker Injected RFQ",
                "organization_id": str(org_a.organization.id),
            },
            headers=org_b.headers,
        )
        assert spoofed_create.status_code == 201
        created_rfq = spoofed_create.json()
        # The created RFQ MUST belong to Org B, NOT Org A
        assert created_rfq["organization_id"] == str(org_b.organization.id)
        assert created_rfq["organization_id"] != str(org_a.organization.id)


# ── 7. Dashboard Isolation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_recent_rfqs_tenant_isolation():
    """Verify GET /dashboard/recent-rfqs only returns RFQs of the authenticated organization."""
    org_a = await create_test_auth_context(role=UserRole.ADMIN, org_name="Dash Org A")
    org_b = await create_test_auth_context(role=UserRole.ADMIN, org_name="Dash Org B")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Org A creates 2 RFQs
        r_a1 = await client.post("/api/v1/rfqs", json={"title": "Org A RFQ 1"}, headers=org_a.headers)
        r_a2 = await client.post("/api/v1/rfqs", json={"title": "Org A RFQ 2"}, headers=org_a.headers)
        id_a1, id_a2 = r_a1.json()["id"], r_a2.json()["id"]

        # Org B creates 1 RFQ
        r_b1 = await client.post("/api/v1/rfqs", json={"title": "Org B RFQ 1"}, headers=org_b.headers)
        id_b1 = r_b1.json()["id"]

        # Check Org A dashboard
        dash_a = await client.get("/api/v1/dashboard/recent-rfqs", headers=org_a.headers)
        assert dash_a.status_code == 200
        items_a = dash_a.json()
        item_a_ids = [item["id"] for item in items_a]
        assert id_a1 in item_a_ids
        assert id_a2 in item_a_ids
        assert id_b1 not in item_a_ids

        # Check Org B dashboard
        dash_b = await client.get("/api/v1/dashboard/recent-rfqs", headers=org_b.headers)
        assert dash_b.status_code == 200
        items_b = dash_b.json()
        item_b_ids = [item["id"] for item in items_b]
        assert id_b1 in item_b_ids
        assert id_a1 not in item_b_ids
        assert id_a2 not in item_b_ids
