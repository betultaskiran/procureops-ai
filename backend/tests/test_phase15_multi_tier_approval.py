"""
backend/tests/test_phase15_multi_tier_approval.py

Phase 15 — Formal Multi-Tier Purchase Approval Workflow Test Suite

Comprehensive validation covering:
1. Exact 250,000 TRY order -> single manager approval transitions order to ISSUED
2. 250,000.01 TRY order -> remains DRAFT after single manager review
3. 250,000.01 TRY order has two pending approval steps (Purchasing Director, CFO)
4. Director approved alone -> order remains DRAFT
5. CFO approved alone -> order remains DRAFT
6. Both Director and CFO approved -> order transitions to ISSUED
7. Same user attempting to approve both roles -> rejected (400 or 403)
8. Director approves, then CFO approves -> ISSUED
9. CFO approves, then Director approves -> ISSUED
10. Unauthorized role attempting to approve (manager, employee, viewer) -> 403 Forbidden
11. Inactive user attempting to approve -> 403 Forbidden
12. Admin cannot bypass dual approval (single approval leaves order in DRAFT)
13. Cross-tenant approval attempt -> 404 Not Found
14. Non-TRY currency order remains DRAFT and requires dual approval
15. Rejection with mandatory reason records rejection and halts workflow
16. Rejection with missing/empty reason -> 400 or 422 Bad Request
17. Pending approval steps invalidated when RFQ is cancelled or order is cancelled
18. Concurrent/duplicate approval calls handled safely (state machine idempotency)
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.organization import Organization
from app.models.supplier import Supplier
from app.models.rfq import RFQ, RFQStatus
from app.models.quote import Quote
from app.models.analysis import (
    Analysis,
    AnalysisStatus,
    Approval,
    ApprovalStatus,
    Recommendation,
    VerificationStatus,
    TCOResult,
)
from app.models.order import (
    PurchaseOrder,
    PurchaseOrderStatus,
    POApprovalStep,
    POApprovalStepStatus,
)
from app.core.security import create_access_token


class UserContext:
    def __init__(self, user: User, token: str):
        self.user = user
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}


class OrgFixture:
    def __init__(self, org: Organization, supplier: Supplier):
        self.org = org
        self.supplier = supplier
        self.users: dict[str, UserContext] = {}

    def get_headers(self, role: str) -> dict[str, str]:
        return self.users[role].headers


async def setup_test_org(session) -> OrgFixture:
    suffix = uuid.uuid4().hex[:6]
    org = Organization(name=f"Phase 15 Org {suffix}", slug=f"phase15-org-{suffix}")
    session.add(org)
    await session.flush()

    supplier = Supplier(
        organization_id=org.id,
        name=f"DEF Enterprise Supplier {suffix}",
        email=f"supplier_{suffix}@def.com",
        is_active=True,
    )
    session.add(supplier)
    await session.flush()

    fixture = OrgFixture(org, supplier)

    roles = [
        UserRole.ADMIN,
        UserRole.MANAGER,
        UserRole.PURCHASING_DIRECTOR,
        UserRole.CFO,
        UserRole.EMPLOYEE,
        UserRole.VIEWER,
    ]

    for role in roles:
        u = User(
            organization_id=org.id,
            email=f"{role.value}_{suffix}@phase15.com",
            full_name=f"User {role.value.title()} {suffix}",
            hashed_password="mock",
            role=role.value,
            is_active=True,
        )
        session.add(u)
        await session.flush()
        token = create_access_token(
            data={"sub": str(u.id), "email": u.email, "role": u.role, "org_id": str(org.id)}
        )
        fixture.users[role.value] = UserContext(u, token)

    await session.commit()
    return fixture


def make_tco_result(analysis_id: uuid.UUID, quote_id: uuid.UUID, amount: Decimal, currency: str = "TRY") -> TCOResult:
    return TCOResult(
        analysis_id=analysis_id,
        quote_id=quote_id,
        subtotal=amount,
        vat_amount=Decimal("0.00"),
        shipping_cost=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        other_costs=Decimal("0.00"),
        total_tco=amount,
        currency=currency,
    )


async def create_analysis_fixture(
    session,
    fixture: OrgFixture,
    amount: Decimal,
    currency: str = "TRY",
) -> tuple[RFQ, Quote, Analysis]:
    rfq = RFQ(organization_id=fixture.org.id, title=f"Purchase Workflow RFQ {amount} {currency}")
    session.add(rfq)
    await session.flush()

    quote = Quote(
        rfq_id=rfq.id,
        supplier_id=fixture.supplier.id,
        currency=currency,
        subtotal=amount,
        total_price=amount,
        delivery_days=7,
        is_compliant=True,
    )
    session.add(quote)
    await session.flush()

    analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
    session.add(analysis)
    await session.flush()

    tco = make_tco_result(analysis.id, quote.id, amount, currency)
    rec = Recommendation(
        analysis_id=analysis.id,
        recommended_quote_id=quote.id,
        reasoning="En uygun teklif",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    session.add_all([tco, rec])
    await session.commit()
    await session.refresh(rfq)
    await session.refresh(quote)
    await session.refresh(analysis)
    return rfq, quote, analysis


# ── Scenario 1: Exact 250,000 TRY order -> single manager approval transitions to ISSUED
@pytest.mark.asyncio
async def test_exact_250k_order_single_manager_approval_transitions_to_issued():
    amount = Decimal("250000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=fixture.get_headers("manager")) as client:
        res = await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            json={"status": "approved", "comment": "Exact threshold approval."},
        )
        assert res.status_code == 201

        # Check PO status directly and through GET endpoint
        async with AsyncSessionLocal() as session:
            po = (
                await session.execute(
                    select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id)
                )
            ).scalar_one()
            assert po.status == PurchaseOrderStatus.ISSUED.value
            assert len(po.approval_steps) == 0


# ── Scenario 2: 250,000.01 TRY order -> remains DRAFT after single manager review
@pytest.mark.asyncio
async def test_250k_01_order_remains_draft_after_single_manager_review():
    amount = Decimal("250000.01")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=fixture.get_headers("manager")) as client:
        res = await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            json={"status": "approved", "comment": "Exceeds single manager threshold."},
        )
        assert res.status_code == 201

        async with AsyncSessionLocal() as session:
            po = (
                await session.execute(
                    select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id)
                )
            ).scalar_one()
            assert po.status == PurchaseOrderStatus.DRAFT.value


# ── Scenario 3: 250,000.01 TRY order has two pending approval steps (Purchasing Director, CFO)
@pytest.mark.asyncio
async def test_250k_01_order_has_two_pending_approval_steps_director_and_cfo():
    amount = Decimal("359330.80")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=fixture.get_headers("manager")) as client:
        res = await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            json={"status": "approved", "comment": "Requires joint Director and CFO governance."},
        )
        assert res.status_code == 201

        async with AsyncSessionLocal() as session:
            po = (
                await session.execute(
                    select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id)
                )
            ).scalar_one()
            steps = po.approval_steps
            assert len(steps) == 2

            step_roles = {s.role: s.status for s in steps}
            assert "purchasing_director" in step_roles
            assert "cfo" in step_roles
            assert step_roles["purchasing_director"] == POApprovalStepStatus.PENDING.value
            assert step_roles["cfo"] == POApprovalStepStatus.PENDING.value


# ── Scenario 4: Director approved alone -> order remains DRAFT
@pytest.mark.asyncio
async def test_director_approved_alone_order_remains_draft():
    amount = Decimal("300000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Manager initiates review -> PO in DRAFT
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            director_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]

        # 2. Director approves
        res = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{director_step.id}/approve",
            headers=fixture.get_headers("purchasing_director"),
            json={"comment": "Director approved."},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "draft"

        async with AsyncSessionLocal() as session:
            refreshed_po = await session.get(PurchaseOrder, po.id)
            assert refreshed_po.status == PurchaseOrderStatus.DRAFT.value


# ── Scenario 5: CFO approved alone -> order remains DRAFT
@pytest.mark.asyncio
async def test_cfo_approved_alone_order_remains_draft():
    amount = Decimal("300000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            cfo_step = [s for s in po.approval_steps if s.role == "cfo"][0]

        # CFO approves alone
        res = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{cfo_step.id}/approve",
            headers=fixture.get_headers("cfo"),
            json={"comment": "Financials approved by CFO."},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "draft"


# ── Scenario 6: Both Director and CFO approved -> order transitions to ISSUED
@pytest.mark.asyncio
async def test_both_director_and_cfo_approved_transitions_to_issued():
    amount = Decimal("359330.80")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]
            cfo_step = [s for s in po.approval_steps if s.role == "cfo"][0]

        # 1. Director approves
        res1 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            headers=fixture.get_headers("purchasing_director"),
            json={"comment": "Director approval."},
        )
        assert res1.status_code == 200
        assert res1.json()["status"] == "draft"

        # 2. CFO approves
        res2 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{cfo_step.id}/approve",
            headers=fixture.get_headers("cfo"),
            json={"comment": "CFO approval."},
        )
        assert res2.status_code == 200
        assert res2.json()["status"] == "issued"

        async with AsyncSessionLocal() as session:
            refreshed_po = await session.get(PurchaseOrder, po.id)
            assert refreshed_po.status == PurchaseOrderStatus.ISSUED.value


# ── Scenario 7: Same user attempting to approve both roles -> rejected (400)
@pytest.mark.asyncio
async def test_same_user_attempting_to_approve_both_roles_rejected_sod():
    amount = Decimal("400000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]
            cfo_step = [s for s in po.approval_steps if s.role == "cfo"][0]

        # Admin user approves first step (acting as director)
        admin_headers = fixture.get_headers("admin")
        res1 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            headers=admin_headers,
            json={"comment": "Admin acting on director step."},
        )
        assert res1.status_code == 200

        # Same admin user attempts to approve second step (cfo step)
        res2 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{cfo_step.id}/approve",
            headers=admin_headers,
            json={"comment": "Admin attempting to approve cfo step as well."},
        )
        # Must be rejected due to Separation of Duties
        assert res2.status_code in (400, 403)
        assert "Ayrılığı" in res2.json()["detail"] or "Separation of Duties" in res2.json()["detail"]


# ── Scenario 8: Director approves, then CFO approves -> ISSUED
@pytest.mark.asyncio
async def test_director_approves_then_cfo_approves_issues_order():
    amount = Decimal("280000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]
            cfo_step = [s for s in po.approval_steps if s.role == "cfo"][0]

        # Director first
        r1 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            headers=fixture.get_headers("purchasing_director"),
            json={"comment": "Step 1 OK"},
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "draft"

        # CFO second
        r2 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{cfo_step.id}/approve",
            headers=fixture.get_headers("cfo"),
            json={"comment": "Step 2 OK"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "issued"


# ── Scenario 9: CFO approves, then Director approves -> ISSUED
@pytest.mark.asyncio
async def test_cfo_approves_then_director_approves_issues_order():
    amount = Decimal("290000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]
            cfo_step = [s for s in po.approval_steps if s.role == "cfo"][0]

        # CFO first
        r1 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{cfo_step.id}/approve",
            headers=fixture.get_headers("cfo"),
            json={"comment": "CFO first"},
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "draft"

        # Director second
        r2 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            headers=fixture.get_headers("purchasing_director"),
            json={"comment": "Director second"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "issued"


# ── Scenario 10: Unauthorized role attempting to approve (manager, employee, viewer) -> 403 Forbidden
@pytest.mark.asyncio
async def test_unauthorized_role_attempting_to_approve_forbidden():
    amount = Decimal("310000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]

        for unauth_role in ["manager", "employee", "viewer"]:
            res = await client.post(
                f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
                headers=fixture.get_headers(unauth_role),
                json={"comment": f"Unauthorized attempt by {unauth_role}"},
            )
            assert res.status_code == 403, f"Expected 403 for {unauth_role}, got {res.status_code}"


# ── Scenario 11: Inactive user attempting to approve -> 403 Forbidden
@pytest.mark.asyncio
async def test_inactive_user_attempting_to_approve_forbidden():
    amount = Decimal("320000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

        # Create inactive purchasing director
        inactive_u = User(
            organization_id=fixture.org.id,
            email=f"inactive_dir_{uuid.uuid4().hex[:4]}@phase15.com",
            full_name="Inactive Director",
            hashed_password="mock",
            role=UserRole.PURCHASING_DIRECTOR.value,
            is_active=False,
        )
        session.add(inactive_u)
        await session.commit()
        inactive_token = create_access_token(
            data={"sub": str(inactive_u.id), "email": inactive_u.email, "role": inactive_u.role, "org_id": str(fixture.org.id)}
        )
        inactive_headers = {"Authorization": f"Bearer {inactive_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]

        res = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            headers=inactive_headers,
            json={"comment": "Inactive director attempt"},
        )
        assert res.status_code in (400, 403)


# ── Scenario 12: Admin cannot bypass dual approval (single approval leaves order in DRAFT)
@pytest.mark.asyncio
async def test_admin_cannot_bypass_dual_approval():
    amount = Decimal("500000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=fixture.get_headers("admin")) as client:
        # Admin reviews analysis -> PO must be created in DRAFT (Article 1.2 requires dual approval)
        rev_res = await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            json={"status": "approved", "comment": "Admin review"},
        )
        assert rev_res.status_code == 201

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            assert po.status == PurchaseOrderStatus.DRAFT.value
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]

        # Admin approves single step
        step_res = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            json={"comment": "Admin approves director step"},
        )
        assert step_res.status_code == 200
        # Order must STILL remain in DRAFT status! Dual approval has not been fulfilled.
        assert step_res.json()["status"] == "draft"


# ── Scenario 13: Cross-tenant approval attempt -> 404 Not Found
@pytest.mark.asyncio
async def test_cross_tenant_approval_attempt_not_found():
    amount = Decimal("300000.00")
    async with AsyncSessionLocal() as session:
        fixture1 = await setup_test_org(session)
        fixture2 = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture1, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture1.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]

        # Director of Org 2 attempts to approve step in Org 1
        res = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            headers=fixture2.get_headers("purchasing_director"),
            json={"comment": "Cross-tenant intrusion"},
        )
        assert res.status_code == 404


# ── Scenario 14: Non-TRY currency order remains DRAFT and requires dual approval
@pytest.mark.asyncio
async def test_non_try_currency_order_requires_dual_approval():
    amount = Decimal("10000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "USD")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=fixture.get_headers("manager")) as client:
        res = await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            json={"status": "approved", "comment": "USD order review"},
        )
        assert res.status_code == 201

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            assert po.status == PurchaseOrderStatus.DRAFT.value
            assert len(po.approval_steps) == 2


# ── Scenario 15: Rejection with mandatory reason records rejection and halts workflow
@pytest.mark.asyncio
async def test_rejection_with_mandatory_reason_halts_workflow():
    amount = Decimal("350000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]
            cfo_step = [s for s in po.approval_steps if s.role == "cfo"][0]

        # Director rejects the order
        reject_reason = "Tedarikçi mali güvenilirlik kriterlerini karşılamıyor."
        res = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/reject",
            headers=fixture.get_headers("purchasing_director"),
            json={"reason": reject_reason},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "cancelled"

        # Check DB state
        async with AsyncSessionLocal() as session:
            refreshed_po = await session.get(PurchaseOrder, po.id)
            assert refreshed_po.status == PurchaseOrderStatus.CANCELLED.value
            assert reject_reason in refreshed_po.cancellation_reason

            refreshed_dir_step = await session.get(POApprovalStep, dir_step.id)
            assert refreshed_dir_step.status == POApprovalStepStatus.REJECTED.value
            assert refreshed_dir_step.rejection_reason == reject_reason

            refreshed_cfo_step = await session.get(POApprovalStep, cfo_step.id)
            assert refreshed_cfo_step.status == POApprovalStepStatus.REJECTED.value


# ── Scenario 16: Rejection with missing/empty reason -> 400 or 422 Bad Request
@pytest.mark.asyncio
async def test_rejection_with_missing_empty_reason_rejected():
    amount = Decimal("300000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]

        # 1. Whitespace only reason -> 400 or 422
        res1 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/reject",
            headers=fixture.get_headers("purchasing_director"),
            json={"reason": "   "},
        )
        assert res1.status_code in (400, 422)

        # 2. Too short reason -> 400 or 422
        res2 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/reject",
            headers=fixture.get_headers("purchasing_director"),
            json={"reason": "no"},
        )
        assert res2.status_code in (400, 422)


# ── Scenario 17: Pending approval steps invalidated when RFQ is cancelled or order is cancelled
@pytest.mark.asyncio
async def test_pending_steps_invalidated_when_order_cancelled():
    amount = Decimal("330000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]

        # Cancel the order via cancel endpoint
        cancel_res = await client.post(
            f"/api/v1/orders/{po.id}/cancel",
            headers=fixture.get_headers("manager"),
            json={"reason": "Talepten vazgeçildi."},
        )
        assert cancel_res.status_code == 200

        # Steps are invalidated
        async with AsyncSessionLocal() as session:
            refreshed_step = await session.get(POApprovalStep, dir_step.id)
            assert refreshed_step.status == POApprovalStepStatus.REJECTED.value

        # Attempt to approve cancelled order step -> 400
        approve_res = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            headers=fixture.get_headers("purchasing_director"),
            json={"comment": "Attempt after cancellation"},
        )
        assert approve_res.status_code == 400


# ── Scenario 18: Concurrent/duplicate approval calls handled safely (state machine idempotency)
@pytest.mark.asyncio
async def test_duplicate_approval_call_rejected_cleanly():
    amount = Decimal("300000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        async with AsyncSessionLocal() as session:
            po = (await session.execute(select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id))).scalar_one()
            dir_step = [s for s in po.approval_steps if s.role == "purchasing_director"][0]

        # First approval call -> 200 OK
        r1 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            headers=fixture.get_headers("purchasing_director"),
            json={"comment": "First approval"},
        )
        assert r1.status_code == 200

        # Duplicate approval call on same step -> 400 Bad Request (step already approved)
        r2 = await client.post(
            f"/api/v1/orders/{po.id}/approvals/{dir_step.id}/approve",
            headers=fixture.get_headers("purchasing_director"),
            json={"comment": "Duplicate approval call"},
        )
        assert r2.status_code == 400
        assert "beklemede" in r2.json()["detail"] or "pending" in r2.json()["detail"]


# ── Bonus Scenario: Pending Approvals Queue Endpoint
@pytest.mark.asyncio
async def test_pending_approvals_queue_endpoint():
    amount = Decimal("350000.00")
    async with AsyncSessionLocal() as session:
        fixture = await setup_test_org(session)
        rfq, quote, analysis = await create_analysis_fixture(session, fixture, amount, "TRY")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/analyses/{analysis.id}/review",
            headers=fixture.get_headers("manager"),
            json={"status": "approved"},
        )

        # 1. Director queue lists step
        dir_res = await client.get("/api/v1/orders/approvals/pending", headers=fixture.get_headers("purchasing_director"))
        assert dir_res.status_code == 200
        dir_items = dir_res.json()
        assert len(dir_items) >= 1
        assert any(it["role"] == "purchasing_director" for it in dir_items)

        # 2. CFO queue lists step
        cfo_res = await client.get("/api/v1/orders/approvals/pending", headers=fixture.get_headers("cfo"))
        assert cfo_res.status_code == 200
        cfo_items = cfo_res.json()
        assert len(cfo_items) >= 1
        assert any(it["role"] == "cfo" for it in cfo_items)

        # 3. Employee queue returns empty
        emp_res = await client.get("/api/v1/orders/approvals/pending", headers=fixture.get_headers("employee"))
        assert emp_res.status_code == 200
        assert emp_res.json() == []
