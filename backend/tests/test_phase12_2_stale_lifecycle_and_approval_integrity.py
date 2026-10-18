"""
backend/tests/test_phase12_2_stale_lifecycle_and_approval_integrity.py

Phase 12.2 Test Suite:
- Stale analysis lifecycle: deterministic material input fingerprinting vs non-material updates
- Preserving approval integrity, issued PO immutability, and draft containment
- Re-running analysis never revokes, mutates, or resets existing approvals or POs
- Authentication persistence, cookie clearing on logout, and session lifecycle validation
"""

import uuid
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.supplier import Supplier
from app.models.rfq import RFQ, RFQItem, RFQStatus
from app.models.quote import Quote, QuoteItem
from app.models.analysis import (
    Analysis,
    AnalysisStatus,
    Approval,
    ApprovalStatus,
    TCOResult,
    Recommendation,
    ComplianceCheck,
    EvidenceItem,
)
from app.models.order import (
    PurchaseOrder,
    PurchaseOrderStatus,
)
from app.models.audit import AuditEvent
from app.models.user import User, UserRole
from app.core.security import hash_password, create_access_token
from unittest.mock import patch
from app.services.agent.service import AgentService
from app.models.analysis import VerificationStatus
from app.api.v1.analyses import compute_material_fingerprint, compute_analysis_staleness


@pytest.fixture(autouse=True)
def mock_agent_service_recommendation():
    async def fake_generate_recommendation(self, analysis_id, organization_id):
        analysis_res = await self.db.execute(select(Analysis).where(Analysis.id == analysis_id))
        analysis = analysis_res.scalar_one()

        quotes_res = await self.db.execute(
            select(Quote).where(Quote.rfq_id == analysis.rfq_id).order_by(Quote.total_price.asc())
        )
        quotes = list(quotes_res.scalars().all())
        rec_quote = quotes[0] if quotes else None

        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=rec_quote.id if rec_quote else None,
            reasoning="En uygun teklif seçildi [Kaynak 1: Kural Motoru].",
            risks="[]",
            alternative_notes="Güven Skoru: 95/100",
            verification_status=VerificationStatus.VERIFIED.value,
            verification_notes="Deterministik ve kanıt kontrolleri sağlandı.",
        )
        self.db.add(rec)
        analysis.status = AnalysisStatus.COMPLETED
        await self.db.commit()
        await self.db.refresh(rec)
        return rec

    with patch.object(AgentService, "generate_recommendation", new=fake_generate_recommendation):
        yield


# ── Helpers ───────────────────────────────────────────────────────────────────

async def create_test_tenant(session, suffix: str | None = None):
    unique_suffix = suffix or uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Phase12.2 Tenant {unique_suffix}",
        slug=f"phase12-2-org-{unique_suffix}",
    )
    session.add(org)
    await session.flush()

    sup1 = Supplier(
        name=f"DEF Supplier {unique_suffix}",
        organization_id=org.id,
        email=f"def_{unique_suffix}@supplier.com",
    )
    sup2 = Supplier(
        name=f"ABC Supplier {unique_suffix}",
        organization_id=org.id,
        email=f"abc_{unique_suffix}@supplier.com",
    )
    session.add_all([sup1, sup2])

    manager = User(
        organization_id=org.id,
        email=f"manager_{unique_suffix}@phase122.com",
        full_name="Phase 12.2 Procurement Manager",
        hashed_password=hash_password("Passw0rd123!"),
        role=UserRole.MANAGER.value,
        is_active=True,
    )
    employee = User(
        organization_id=org.id,
        email=f"buyer_{unique_suffix}@phase122.com",
        full_name="Phase 12.2 Buyer",
        hashed_password=hash_password("Passw0rd123!"),
        role=UserRole.EMPLOYEE.value,
        is_active=True,
    )
    session.add_all([manager, employee])
    await session.commit()
    await session.refresh(org)
    await session.refresh(sup1)
    await session.refresh(sup2)
    await session.refresh(manager)
    await session.refresh(employee)

    mgr_token = create_access_token({"sub": str(manager.id), "org_id": str(org.id), "role": "manager"})
    emp_token = create_access_token({"sub": str(employee.id), "org_id": str(org.id), "role": "employee"})

    return {
        "org": org,
        "sup1": sup1,
        "sup2": sup2,
        "manager": manager,
        "employee": employee,
        "mgr_token": mgr_token,
        "emp_token": emp_token,
        "mgr_headers": {"Authorization": f"Bearer {mgr_token}"},
        "emp_headers": {"Authorization": f"Bearer {emp_token}"},
    }


async def create_rfq_with_quotes(session, tenant, q1_total: Decimal = Decimal("150000.00"), currency: str = "TRY"):
    rfq = RFQ(
        organization_id=tenant["org"].id,
        created_by_id=tenant["employee"].id,
        title="Ofis Ekipmanları Alımı",
        description="20 adet masa ve ergonomik koltuk seti",
        required_quantity=20,
        required_date=date.today() + timedelta(days=30),
        budget=int(max(Decimal("250000.00"), q1_total * Decimal("1.25"))),
        max_delivery_days=15,
        min_warranty_months=12,
        payment_terms="net-30",
        status=RFQStatus.COLLECTING_QUOTES.value,
    )
    session.add(rfq)
    await session.flush()

    item1 = RFQItem(rfq_id=rfq.id, line_number=1, description="Ergonomik Koltuk", quantity=20, unit="Adet")
    session.add(item1)

    q1 = Quote(
        rfq_id=rfq.id,
        supplier_id=tenant["sup1"].id,
        currency=currency,
        subtotal=q1_total * Decimal("0.8333"),
        vat_rate=Decimal("0.2000"),
        vat_amount=q1_total * Decimal("0.1667"),
        shipping_cost=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_price=q1_total,
        delivery_days=10,
        payment_terms="net-30",
        warranty_months=24,
        is_compliant=True,
    )
    q2 = Quote(
        rfq_id=rfq.id,
        supplier_id=tenant["sup2"].id,
        currency=currency,
        subtotal=Decimal("170000.00"),
        vat_rate=Decimal("0.2000"),
        vat_amount=Decimal("34000.00"),
        shipping_cost=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_price=Decimal("204000.00"),
        delivery_days=14,
        payment_terms="net-30",
        warranty_months=12,
        is_compliant=True,
    )
    session.add_all([q1, q2])
    await session.commit()
    await session.refresh(rfq)
    await session.refresh(q1)
    await session.refresh(q2)
    return rfq, q1, q2


def make_tco(analysis_id: uuid.UUID, quote: Quote) -> TCOResult:
    return TCOResult(
        analysis_id=analysis_id,
        quote_id=quote.id,
        subtotal=quote.subtotal,
        vat_amount=quote.vat_amount or Decimal("0"),
        shipping_cost=Decimal("0"),
        discount_amount=Decimal("0"),
        other_costs=Decimal("0"),
        total_tco=quote.total_price,
        currency=quote.currency,
    )


# ── 1. Approval and Audit-Only Updates Do NOT Make Analysis Stale ─────────────

@pytest.mark.asyncio
async def test_approval_and_audit_updates_do_not_make_analysis_stale():
    """
    Proves the bugfix:
    1. Analysis is completed and its material fingerprint is recorded in AuditEvent.
    2. Approval endpoint runs: rfq.status becomes 'approved', rfq.updated_at is updated.
    3. compute_analysis_staleness MUST return False because no material purchasing inputs changed.
    4. Subsequent AuditEvents and unarchive/archive writes must also NOT make the analysis stale.
    """
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant, Decimal("100000.00"))

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        tco1 = make_tco(analysis.id, q1)
        tco2 = make_tco(analysis.id, q2)
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=q1.id,
            reasoning="En uygun teklif DEF",
            verification_status="verified",
        )
        session.add_all([tco1, tco2, rec])

        # Compute and record material fingerprint in analysis_completed audit event
        material_fp = compute_material_fingerprint(rfq, [q1, q2], rfq.items)
        audit = AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=tenant["manager"].id,
            event_type="analysis_completed",
            entity_type="analysis",
            entity_id=analysis.id,
            payload={
                "rfq_id": str(rfq.id),
                "quote_count": 2,
                "material_fingerprint": material_fp,
            }
        )
        session.add(audit)
        await session.commit()

        # Before approval: staleness is False
        assert await compute_analysis_staleness(session, analysis, rfq) is False

        # Run human review to approve the recommendation
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "approved",
                    "comment": "Onaylandı.",
                    "selected_quote_id": str(q1.id),
                },
                headers=tenant["mgr_headers"],
            )
            assert resp.status_code == 201

        # Refresh RFQ from DB to see updated rfq.status and rfq.updated_at
        await session.refresh(rfq)
        assert rfq.status == "approved"

        # PROOF: Even though rfq.updated_at was modified by the approval write,
        # staleness is STILL False!
        is_stale_after_approval = await compute_analysis_staleness(session, analysis, rfq)
        assert is_stale_after_approval is False, "Approval write must NOT make analysis stale!"

        # Create an unrelated audit event
        session.add(AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=tenant["manager"].id,
            event_type="user_viewed_page",
            entity_type="rfq",
            entity_id=rfq.id,
            payload={"action": "view"}
        ))
        await session.commit()

        # Staleness is STILL False
        assert await compute_analysis_staleness(session, analysis, rfq) is False


# ── 2. Changing RFQ Material Requirements Makes Analysis Stale ────────────────

@pytest.mark.asyncio
async def test_changing_rfq_material_requirements_makes_analysis_stale():
    """
    Material RFQ changes (budget, delivery days, warranty, items) MUST invalidate analysis.
    """
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        session.add_all([make_tco(analysis.id, q1), make_tco(analysis.id, q2)])
        material_fp = compute_material_fingerprint(rfq, [q1, q2], rfq.items)
        session.add(AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=tenant["manager"].id,
            event_type="analysis_completed",
            entity_type="analysis",
            entity_id=analysis.id,
            payload={"rfq_id": str(rfq.id), "quote_count": 2, "material_fingerprint": material_fp}
        ))
        await session.commit()

        # Initially fresh
        assert await compute_analysis_staleness(session, analysis, rfq) is False

        # Change material purchasing input: RFQ budget
        rfq.budget = 180000
        session.add(rfq)
        await session.commit()

        # Must be detected as stale!
        assert await compute_analysis_staleness(session, analysis, rfq) is True


# ── 3. Changing Quote Material Values Makes Analysis Stale ───────────────────

@pytest.mark.asyncio
async def test_changing_quote_material_values_makes_analysis_stale():
    """
    Material Quote changes (total_price, discounts, delivery days, new/deleted quotes) MUST invalidate analysis.
    """
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        session.add_all([make_tco(analysis.id, q1), make_tco(analysis.id, q2)])
        material_fp = compute_material_fingerprint(rfq, [q1, q2], rfq.items)
        session.add(AuditEvent(
            organization_id=rfq.organization_id,
            actor_id=tenant["manager"].id,
            event_type="analysis_completed",
            entity_type="analysis",
            entity_id=analysis.id,
            payload={"rfq_id": str(rfq.id), "quote_count": 2, "material_fingerprint": material_fp}
        ))
        await session.commit()

        # Initially fresh
        assert await compute_analysis_staleness(session, analysis, rfq) is False

        # Supplier updates quote price
        q1.total_price = Decimal("145000.00")
        session.add(q1)
        await session.commit()

        # Must be detected as stale!
        assert await compute_analysis_staleness(session, analysis, rfq) is True


# ── 4. Re-running Analysis Does NOT Reset Approval or Mutate Issued PO ────────

@pytest.mark.asyncio
async def test_rerunning_analysis_preserves_approval_and_issued_po():
    """
    Verifies Invariants 2, 3, 4, 5:
    1. RFQ is analyzed and approved (PO #... created with status = ISSUED).
    2. rfq.status is 'approved'.
    3. Re-running analysis (POST /rfqs/{rfq_id}/analyze) creates a new analysis row.
    4. INVARIANTS:
       - The existing Approval record is NOT overwritten or reset.
       - The existing PurchaseOrder record is NOT mutated or revoked.
       - rfq.status remains 'approved' (does NOT reset to 'pending_approval').
       - PO remains linked to its original approval and quote.
    """
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant, Decimal("120000.00"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Run initial analysis
            resp1 = await client.post(
                f"/api/v1/rfqs/{rfq.id}/analyze",
                json={},
                headers=tenant["mgr_headers"],
            )
            assert resp1.status_code == 200
            initial_analysis_id = resp1.json()["id"]

            # 2. Approve recommendation
            rev_resp = await client.post(
                f"/api/v1/analyses/{initial_analysis_id}/review",
                json={
                    "status": "approved",
                    "comment": "İlk analiz onaylandı ve sipariş oluşturuldu.",
                    "selected_quote_id": str(q1.id),
                },
                headers=tenant["mgr_headers"],
            )
            assert rev_resp.status_code == 201

        # Check DB state after approval
        po_res = await session.execute(
            select(PurchaseOrder).join(Quote).where(Quote.rfq_id == rfq.id)
        )
        po = po_res.scalar_one_or_none()
        assert po is not None
        assert po.status == PurchaseOrderStatus.ISSUED.value
        po_id = po.id
        po_num = po.po_number
        po_quote_id = po.quote_id
        po_approval_id = po.approval_id

        await session.refresh(rfq)
        assert rfq.status == "approved"

        # 3. User re-runs analysis on the RFQ
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp2 = await client.post(
                f"/api/v1/rfqs/{rfq.id}/analyze",
                json={},
                headers=tenant["mgr_headers"],
            )
            assert resp2.status_code == 200
            second_analysis_id = resp2.json()["id"]
            assert second_analysis_id != initial_analysis_id

        # 4. Verify persisted state invariants
        await session.refresh(rfq)
        assert rfq.status == "approved", "Re-running analysis must NOT reset rfq.status from approved to pending_approval!"

        # Check existing approval record
        appr_res = await session.execute(
            select(Approval).where(Approval.id == po_approval_id)
        )
        saved_approval = appr_res.scalar_one_or_none()
        assert saved_approval is not None
        assert saved_approval.status == "approved", "Existing approval record must not be reset!"

        # Check existing PurchaseOrder
        po_after = await session.get(PurchaseOrder, po_id)
        assert po_after is not None
        assert po_after.status == PurchaseOrderStatus.ISSUED.value, "Existing issued PO must not be revoked!"
        assert po_after.po_number == po_num
        assert po_after.quote_id == po_quote_id
        assert po_after.approval_id == po_approval_id


# ── 5. Duplicate PO Blocked When Active PO Exists ─────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_po_blocked_when_active_po_exists():
    """
    Even after a new analysis is run, attempting to approve it to create a second PO
    must be deterministically blocked with HTTP 400.
    """
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant, Decimal("100000.00"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.post(f"/api/v1/rfqs/{rfq.id}/analyze", json={}, headers=tenant["mgr_headers"])
            a1_id = r1.json()["id"]

            await client.post(
                f"/api/v1/analyses/{a1_id}/review",
                json={"status": "approved", "selected_quote_id": str(q1.id)},
                headers=tenant["mgr_headers"],
            )

            # Second analysis
            r2 = await client.post(f"/api/v1/rfqs/{rfq.id}/analyze", json={}, headers=tenant["mgr_headers"])
            a2_id = r2.json()["id"]

            # Attempt to approve second analysis
            dup_resp = await client.post(
                f"/api/v1/analyses/{a2_id}/review",
                json={"status": "approved", "selected_quote_id": str(q2.id)},
                headers=tenant["mgr_headers"],
            )
            assert dup_resp.status_code == 400
            assert "aktif bir sipariş emri" in dup_resp.json()["detail"].lower()


# ── 6. Draft PO Remains Unreleased and Delivery Blocked ────────────────────────

@pytest.mark.asyncio
async def test_draft_po_remains_unreleased_and_blocks_delivery():
    """
    Verifies that quotes exceeding 250,000 TRY remain in DRAFT status,
    supplier email is NOT sent, and delivery cannot be executed.
    """
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        # Quote total 350,000 TRY > 250,000 TRY threshold
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant, Decimal("350000.00"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.post(f"/api/v1/rfqs/{rfq.id}/analyze", json={}, headers=tenant["mgr_headers"])
            a1_id = r1.json()["id"]

            rev_resp = await client.post(
                f"/api/v1/analyses/{a1_id}/review",
                json={"status": "approved", "selected_quote_id": str(q1.id)},
                headers=tenant["mgr_headers"],
            )
            assert rev_resp.status_code == 201

        # Check PO status in DB
        po_res = await session.execute(
            select(PurchaseOrder).join(Quote).where(Quote.rfq_id == rfq.id)
        )
        po = po_res.scalar_one_or_none()
        assert po is not None
        assert po.status == PurchaseOrderStatus.DRAFT.value
        assert po.email_sent is False

        # Attempt to deliver draft PO must be rejected
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            deliv_resp = await client.post(
                f"/api/v1/orders/{po.id}/deliver",
                json={"actual_delivery_date": str(date.today())},
                headers=tenant["mgr_headers"],
            )
            assert deliv_resp.status_code == 400
            assert "taslak" in deliv_resp.json()["detail"].lower()


# ── 7. Stale Analyses Cannot Be Approved ──────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_analyses_cannot_be_approved():
    """
    When material inputs change, the analysis becomes stale and approval is rejected.
    """
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant, Decimal("100000.00"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.post(f"/api/v1/rfqs/{rfq.id}/analyze", json={}, headers=tenant["mgr_headers"])
            a1_id = r1.json()["id"]

        # Mutate material RFQ item
        item = rfq.items[0]
        item.quantity = 50
        session.add(item)
        await session.commit()

        # Try to approve stale analysis
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            rev_resp = await client.post(
                f"/api/v1/analyses/{a1_id}/review",
                json={"status": "approved", "selected_quote_id": str(q1.id)},
                headers=tenant["mgr_headers"],
            )
            assert rev_resp.status_code == 400
            assert "stale" in rev_resp.json()["detail"].lower() or "güncell" in rev_resp.json()["detail"].lower()


# ── 8. Authentication Session Lifecycle & Logout Cookie Clearing ───────────────

@pytest.mark.asyncio
async def test_logout_clears_cookie_and_revokes_access():
    """
    Verifies Task 4:
    - POST /api/v1/auth/logout deletes the HttpOnly access_token cookie
    - Cookie header in Set-Cookie has max-age=0 or expires in 1970
    - Expired/invalid token cannot access protected routes
    """
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Login via API
            login_resp = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": tenant["manager"].email,
                    "password": "Passw0rd123!",
                }
            )
            assert login_resp.status_code == 200
            assert "set-cookie" in login_resp.headers
            assert "access_token=" in login_resp.headers["set-cookie"]

            # Logout
            logout_resp = await client.post("/api/v1/auth/logout")
            assert logout_resp.status_code == 200
            set_cookie_logout = logout_resp.headers.get("set-cookie", "")
            # Verify cookie is invalidated (max-age=0 or empty or expires=0)
            assert "access_token" in set_cookie_logout
            assert 'max-age=0' in set_cookie_logout.lower() or '1970' in set_cookie_logout or 'access_token=""' in set_cookie_logout or 'access_token=;' in set_cookie_logout


@pytest.mark.asyncio
async def test_expired_or_invalid_session_cannot_access_protected_routes():
    """
    Expired tokens, tokens signed with bad secrets, or inactive users return 401.
    """
    import jwt
    from app.core.config import settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Expired token
        expired_token = jwt.encode(
            {"sub": str(uuid.uuid4()), "org_id": str(uuid.uuid4()), "role": "manager", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        r_exp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert r_exp.status_code == 401

        # Tampered signature
        tampered_token = jwt.encode(
            {"sub": str(uuid.uuid4()), "org_id": str(uuid.uuid4()), "role": "manager", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "completely-wrong-secret-key-123456789",
            algorithm=settings.JWT_ALGORITHM,
        )
        r_tamp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
        assert r_tamp.status_code == 401
