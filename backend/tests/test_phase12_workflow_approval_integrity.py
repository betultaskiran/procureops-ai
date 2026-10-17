"""
backend/tests/test_phase12_workflow_approval_integrity.py

Phase 12: End-to-End Procurement Workflow Validation & AI Recommendation Approval Integrity.

Scenarios Covered:
1. Deterministic Verification & Standard Approval:
   - Verified recommendation allows standard approval (HTTP 201).
   - Generates Purchase Order (PO) in 'issued' status with correct totals and metadata.
2. Inconclusive Recommendation Blocks Standard Approval:
   - When verification_status is 'inconclusive' (e.g. ungrounded policy citations), standard approval is rejected with HTTP 400.
3. Inconclusive Recommendation Exception Flow:
   - Exception approval requires explicit acknowledgement (acknowledged_policy_violation=True).
   - When acknowledged, succeeds (HTTP 201) and issues PO.
4. Non-Compliant Quote Blocks Standard Approval:
   - Quotes failing deterministic budget or delivery rules cannot receive standard approval (HTTP 400).
5. Stale Analysis Protection:
   - When analysis is stale (quotes or RFQ changed), both standard and exception approvals are strictly rejected with HTTP 400.
6. RBAC Enforcement on Review:
   - User with EMPLOYEE role is rejected with HTTP 403 Forbidden.
7. Multi-Tenant Isolation on Review:
   - Manager from Org B cannot review/approve Org A analysis (HTTP 404 Not Found).
8. Duplicate Approval Idempotency Protection:
   - Repeated approval on an already approved analysis is rejected with HTTP 400 (prevents duplicate PO creation).
9. Full Purchase Order Lifecycle Progression:
   - PO transitions from 'issued' -> 'delivered' -> 'completed'.
   - Quality issues (defects, delivery delays) recorded and tracked.
10. RAG Query Grounding & Verifier Source Recognition:
    - Verifies that internal calculation and rule citations (Kural Motoru, TCO) do not trigger false-positive inconclusive status.
"""

from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import uuid
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
    VerificationStatus,
    ComplianceCheck,
    EvidenceItem,
)
from app.models.order import (
    PurchaseOrder,
    PurchaseOrderStatus,
    POQualityIssue,
    IssueType,
    IssueSeverity,
)
from app.models.user import User, UserRole
from app.core.security import hash_password, create_access_token
from app.services.agent.verification import VerificationService


# ── Test Setup Helpers ─────────────────────────────────────────────────────────

async def create_test_tenant(session, suffix: str | None = None):
    unique_suffix = suffix or uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Phase12 Tenant {unique_suffix}",
        slug=f"phase12-org-{unique_suffix}",
    )
    session.add(org)
    await session.flush()

    sup1 = Supplier(name=f"DEF NEW {unique_suffix}", organization_id=org.id)
    sup2 = Supplier(name=f"DEF Elektronik {unique_suffix}", organization_id=org.id)
    session.add_all([sup1, sup2])

    manager = User(
        organization_id=org.id,
        email=f"manager_{unique_suffix}@phase12.com",
        full_name="Phase 12 Procurement Manager",
        hashed_password=hash_password("Passw0rd123!"),
        role=UserRole.MANAGER.value,
        is_active=True,
    )
    employee = User(
        organization_id=org.id,
        email=f"employee_{unique_suffix}@phase12.com",
        full_name="Phase 12 Junior Buyer",
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
        "mgr_headers": {"Authorization": f"Bearer {mgr_token}"},
        "emp_headers": {"Authorization": f"Bearer {emp_token}"},
    }


async def create_rfq_with_quotes(session, tenant):
    org = tenant["org"]
    sup1 = tenant["sup1"]
    sup2 = tenant["sup2"]

    rfq = RFQ(
        organization_id=org.id,
        title="Kurumsal Donanım Alımı Phase 12",
        budget=Decimal("200000.00"),
        max_delivery_days=14,
        min_warranty_months=24,
        payment_terms="net-30",
        status=RFQStatus.COLLECTING_QUOTES.value,
    )
    session.add(rfq)
    await session.flush()

    item1 = RFQItem(
        rfq_id=rfq.id,
        line_number=1,
        description="Kurumsal Laptop Intel Ultra 5 16GB",
        quantity=10,
        unit="Adet",
    )
    session.add(item1)
    await session.flush()

    # Quote 1: DEF NEW (Compliant: 180,000 <= 200,000 budget & <= 250,000 authority threshold)
    q1 = Quote(
        rfq_id=rfq.id,
        supplier_id=sup1.id,
        subtotal=Decimal("180000.00"),
        total_price=Decimal("180000.00"),
        currency="TRY",
        delivery_days=7,
        warranty_months=24,
        payment_terms="net-30",
        is_compliant=True,
    )
    # Quote 2: DEF Elektronik (Non-compliant: budget 220,000 > 200,000)
    q2 = Quote(
        rfq_id=rfq.id,
        supplier_id=sup2.id,
        subtotal=Decimal("220000.00"),
        total_price=Decimal("220000.00"),
        currency="TRY",
        delivery_days=10,
        warranty_months=24,
        payment_terms="net-30",
        is_compliant=False,
    )
    session.add_all([q1, q2])
    await session.flush()

    # Add quote line item for q1
    q1_item = QuoteItem(
        quote_id=q1.id,
        line_number=1,
        description="Kurumsal Laptop Intel Ultra 5 16GB",
        quantity=Decimal("10"),
        unit="Adet",
        unit_price=Decimal("18000.00"),
        total_price=Decimal("180000.00"),
    )
    session.add(q1_item)
    await session.commit()
    await session.refresh(rfq)
    await session.refresh(q1)
    await session.refresh(q2)

    return rfq, q1, q2


def make_tco(analysis_id: uuid.UUID, quote: Quote, total_tco: Decimal | None = None) -> TCOResult:
    amount = total_tco if total_tco is not None else quote.total_price
    return TCOResult(
        analysis_id=analysis_id,
        quote_id=quote.id,
        subtotal=amount,
        vat_amount=Decimal("0.00"),
        shipping_cost=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        other_costs=Decimal("0.00"),
        total_tco=amount,
        currency="TRY",
    )


def make_compliance_check(analysis_id: uuid.UUID, quote_id: uuid.UUID, rule_name: str = "Bütçe Uyumu", result: str = "pass") -> ComplianceCheck:
    return ComplianceCheck(
        analysis_id=analysis_id,
        quote_id=quote_id,
        rule_name=rule_name,
        rule_description=f"{rule_name} kuralı doğrulaması",
        result=result,
        actual_value="10",
        required_value="10",
    )


# ── 1. Verified Recommendation Allows Standard Approval & Creates PO ───────────

@pytest.mark.asyncio
async def test_verified_recommendation_standard_approval_creates_po():
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        # Create completed, verified analysis
        analysis = Analysis(
            rfq_id=rfq.id,
            status=AnalysisStatus.COMPLETED.value,
        )
        session.add(analysis)
        await session.flush()

        tco1 = make_tco(analysis.id, q1)
        tco2 = make_tco(analysis.id, q2)
        chk1 = make_compliance_check(analysis.id, q1.id, "Bütçe Uyumu", "pass")
        chk2 = make_compliance_check(analysis.id, q2.id, "Bütçe Uyumu", "fail")
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=q1.id,
            reasoning="DEF NEW en ekonomik ve kurala tam uygun tekliftir [Kaynak 1: Kural Motoru].",
            verification_status="verified",
            verification_notes="Tüm deterministik kurallar ve kanıt doğrulamaları sağlandı.",
        )
        session.add_all([tco1, tco2, chk1, chk2, rec])
        await session.commit()

        # Execute Standard Approval via API
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "approved",
                    "comment": "Tüm şartlar uygun görüldü, onaylandı.",
                    "selected_quote_id": str(q1.id),
                    "acknowledged_policy_violation": False,
                },
                headers=tenant["mgr_headers"],
            )

        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["status"] == "approved"
        assert data["selected_quote_id"] == str(q1.id)

        # Verify DB: Purchase Order created in 'issued' status
        po_res = await session.execute(
            select(PurchaseOrder).join(Quote).where(Quote.rfq_id == rfq.id)
        )
        po = po_res.scalar_one_or_none()
        assert po is not None, "Purchase Order was not created in DB"
        assert po.status == PurchaseOrderStatus.ISSUED.value
        assert po.quote_id == q1.id
        assert po.po_number.startswith("PO-")


# ── 2. Inconclusive Recommendation Blocks Standard Approval ────────────────────

@pytest.mark.asyncio
async def test_inconclusive_recommendation_blocks_standard_approval():
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(
            rfq_id=rfq.id,
            status=AnalysisStatus.COMPLETED.value,
        )
        session.add(analysis)
        await session.flush()

        tco1 = make_tco(analysis.id, q1)
        tco2 = make_tco(analysis.id, q2)
        chk1 = make_compliance_check(analysis.id, q1.id, "Bütçe Uyumu", "pass")
        chk2 = make_compliance_check(analysis.id, q2.id, "Bütçe Uyumu", "fail")
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=q1.id,
            reasoning="DEF NEW önerilmektedir ancak dayanak kanıt tam doğrulanamadı.",
            verification_status="inconclusive",
            verification_notes="Desteklenmeyen alıntılar tespit edildi.",
        )
        session.add_all([tco1, tco2, chk1, chk2, rec])
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "approved",
                    "comment": "Standart onayla geçmeye çalışıyorum.",
                    "selected_quote_id": str(q1.id),
                    "acknowledged_policy_violation": False,
                },
                headers=tenant["mgr_headers"],
            )

        assert resp.status_code == 400
        assert "inconclusive" in resp.json()["detail"].lower()

        # Verify NO PO was created
        po_res = await session.execute(
            select(PurchaseOrder).join(Quote).where(Quote.rfq_id == rfq.id)
        )
        assert po_res.scalar_one_or_none() is None


# ── 3. Inconclusive Recommendation Exception Approval Flow ─────────────────────

@pytest.mark.asyncio
async def test_inconclusive_recommendation_exception_approval_lifecycle():
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(
            rfq_id=rfq.id,
            status=AnalysisStatus.COMPLETED.value,
        )
        session.add(analysis)
        await session.flush()

        tco1 = make_tco(analysis.id, q1)
        tco2 = make_tco(analysis.id, q2)
        chk1 = make_compliance_check(analysis.id, q1.id, "Bütçe Uyumu", "pass")
        chk2 = make_compliance_check(analysis.id, q2.id, "Bütçe Uyumu", "fail")
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=q1.id,
            reasoning="DEF NEW önerilmektedir ancak politika belirsizliği var.",
            verification_status="inconclusive",
            verification_notes="Kurumsal politika RAG eşleşmesi eksik.",
        )
        session.add_all([tco1, tco2, chk1, chk2, rec])
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Exception approval without acknowledgement -> must fail with 400
            unack_resp = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "exception_approved",
                    "comment": "İstisna onayı ama onay kutusunu işaretlemedim.",
                    "selected_quote_id": str(q1.id),
                    "acknowledged_policy_violation": False,
                },
                headers=tenant["mgr_headers"],
            )
            assert unack_resp.status_code == 400

            # 2. Exception approval with acknowledgement -> must succeed with 201
            ack_resp = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "exception_approved",
                    "comment": "Yönetici riski üstlenerek istisna onayını onaylıyor.",
                    "selected_quote_id": str(q1.id),
                    "acknowledged_policy_violation": True,
                },
                headers=tenant["mgr_headers"],
            )
            assert ack_resp.status_code in [200, 201]
            data = ack_resp.json()
            assert data["status"] == "exception_approved"
            assert data["acknowledged_policy_violation"] is True

        # Verify PO created
        po_res = await session.execute(
            select(PurchaseOrder).join(Quote).where(Quote.rfq_id == rfq.id)
        )
        po = po_res.scalar_one_or_none()
        assert po is not None
        assert po.status == PurchaseOrderStatus.ISSUED.value


# ── 4. Non-Compliant Quote Blocks Standard Approval ─────────────────────────────

@pytest.mark.asyncio
async def test_non_compliant_quote_blocks_standard_approval():
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(
            rfq_id=rfq.id,
            status=AnalysisStatus.COMPLETED.value,
        )
        session.add(analysis)
        await session.flush()

        tco1 = make_tco(analysis.id, q1)
        tco2 = make_tco(analysis.id, q2)
        chk1 = make_compliance_check(analysis.id, q1.id, "Bütçe Uyumu", "pass")
        chk2 = make_compliance_check(analysis.id, q2.id, "Bütçe Aşımı", "fail")
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=q1.id,
            reasoning="Öneri",
            verification_status="verified",
        )
        session.add_all([tco1, tco2, chk1, chk2, rec])
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "approved",
                    "comment": "Uyumsuz q2'yi standart onaylamaya çalışıyorum.",
                    "selected_quote_id": str(q2.id),
                    "acknowledged_policy_violation": False,
                },
                headers=tenant["mgr_headers"],
            )

        assert resp.status_code == 400
        assert "uyumsuz" in resp.json()["detail"].lower() or "kural ihlali" in resp.json()["detail"].lower()


# ── 5. Stale Analysis Blocks All Approvals ───────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_analysis_blocks_all_approvals():
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(
            rfq_id=rfq.id,
            status=AnalysisStatus.COMPLETED.value,
        )
        session.add(analysis)
        await session.flush()

        tco1 = make_tco(analysis.id, q1)
        tco2 = make_tco(analysis.id, q2)
        session.add_all([tco1, tco2])
        await session.commit()

        # Update RFQ after analysis was created to trigger dynamic staleness
        rfq.updated_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        session.add(rfq)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Standard approval blocked
            resp1 = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "approved",
                    "comment": "Bayat analizi onaylama denemesi.",
                    "selected_quote_id": str(q1.id),
                },
                headers=tenant["mgr_headers"],
            )
            assert resp1.status_code == 400
            assert "stale" in resp1.json()["detail"].lower() or "güncel" in resp1.json()["detail"].lower()

            # Exception approval also blocked
            resp2 = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "exception_approved",
                    "comment": "Bayat analizi istisna ile onaylama denemesi.",
                    "selected_quote_id": str(q1.id),
                    "acknowledged_policy_violation": True,
                },
                headers=tenant["mgr_headers"],
            )
            assert resp2.status_code == 400
            assert "stale" in resp2.json()["detail"].lower() or "güncel" in resp2.json()["detail"].lower()


# ── 6. RBAC: Unauthorized Employee Rejected with 403 ────────────────────────────

@pytest.mark.asyncio
async def test_unauthorized_employee_rejected_with_403():
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "approved",
                    "comment": "Çalışan olarak onaylamaya çalışıyorum.",
                    "selected_quote_id": str(q1.id),
                },
                headers=tenant["emp_headers"],  # Employee role!
            )

        assert resp.status_code == 403, f"Expected 403 Forbidden, got {resp.status_code}: {resp.text}"


# ── 7. Multi-Tenant Isolation on Review: Cross-tenant 404 ───────────────────────

@pytest.mark.asyncio
async def test_cross_tenant_manager_cannot_review_other_org():
    async with AsyncSessionLocal() as session:
        tenant_a = await create_test_tenant(session, suffix=f"a_{uuid.uuid4().hex[:6]}")
        tenant_b = await create_test_tenant(session, suffix=f"b_{uuid.uuid4().hex[:6]}")
        rfq_a, q1_a, q2_a = await create_rfq_with_quotes(session, tenant_a)

        analysis_a = Analysis(rfq_id=rfq_a.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis_a)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/analyses/{analysis_a.id}/review",
                json={
                    "status": "approved",
                    "comment": "Tenant B yöneticisi Tenant A'yı onaylayamaz.",
                    "selected_quote_id": str(q1_a.id),
                },
                headers=tenant_b["mgr_headers"],  # Org B manager!
            )

        assert resp.status_code == 404, f"Expected 404 Not Found for cross-tenant, got {resp.status_code}: {resp.text}"


# ── 8. Duplicate Approval Idempotency Protection ────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_approval_prevention_idempotency():
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        tco1 = make_tco(analysis.id, q1)
        tco2 = make_tco(analysis.id, q2)
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=q1.id,
            reasoning="Uygun teklif.",
            verification_status="verified",
        )
        session.add_all([tco1, tco2, rec])
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. First approval succeeds
            resp1 = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={"status": "approved", "selected_quote_id": str(q1.id)},
                headers=tenant["mgr_headers"],
            )
            assert resp1.status_code in [200, 201]

            # 2. Second approval on same analysis rejected
            resp2 = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={"status": "approved", "selected_quote_id": str(q1.id)},
                headers=tenant["mgr_headers"],
            )
            assert resp2.status_code == 400
            assert "zaten" in resp2.json()["detail"].lower() or "düzenlenmiş" in resp2.json()["detail"].lower()

        # Verify exactly 1 PO was generated
        po_res = await session.execute(
            select(PurchaseOrder).join(Quote).where(Quote.rfq_id == rfq.id)
        )
        pos = po_res.scalars().all()
        assert len(pos) == 1


# ── 9. Full Purchase Order Lifecycle Progression ────────────────────────────────

@pytest.mark.asyncio
async def test_purchase_order_lifecycle_progression():
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        approval = Approval(
            analysis_id=analysis.id,
            reviewer_id=tenant["manager"].id,
            status=ApprovalStatus.APPROVED.value,
            selected_quote_id=q1.id,
        )
        session.add(approval)
        await session.flush()

        expected_delivery = date.today() + timedelta(days=7)
        po = PurchaseOrder(
            po_number=f"PO-TEST-{uuid.uuid4().hex[:8].upper()}",
            quote_id=q1.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.ISSUED.value,
            expected_delivery_date=expected_delivery,
        )
        session.add(po)
        await session.commit()
        await session.refresh(po)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Step A: Mark Delivered
            deliv_resp = await client.post(
                f"/api/v1/orders/{po.id}/deliver",
                json={
                    "actual_delivery_date": "2026-10-17",
                    "delivery_notes": "Ürünler eksiksiz teslim alındı.",
                },
                headers=tenant["mgr_headers"],
            )
            assert deliv_resp.status_code == 200
            assert deliv_resp.json()["status"] == PurchaseOrderStatus.DELIVERED.value

            # Step B: Record Quality Issue
            qi_resp = await client.post(
                f"/api/v1/orders/{po.id}/quality-issues",
                json={
                    "issue_type": "defect",
                    "severity": "medium",
                    "description": "1 adet monitörün kutusunda ezilme tespit edildi.",
                    "rejection_count": 1,
                },
                headers=tenant["mgr_headers"],
            )
            assert qi_resp.status_code == 200
            assert qi_resp.json()["issue_type"] == "defect"

            # Step C: Complete Order with final adjusted amount
            comp_resp = await client.post(
                f"/api/v1/orders/{po.id}/complete",
                json={
                    "final_amount": 355000.00,
                    "completion_notes": "Kusurlu ürün tenzilatı yapılarak fatura kesinleşti.",
                },
                headers=tenant["mgr_headers"],
            )
            assert comp_resp.status_code == 200
            data = comp_resp.json()
            assert data["status"] == PurchaseOrderStatus.COMPLETED.value
            assert float(data["final_amount"]) == 355000.00

        # Verify DB state
        await session.refresh(po)
        assert po.status == PurchaseOrderStatus.COMPLETED.value
        assert float(po.final_amount) == 355000.00


# ── 10. RAG Query Grounding & Verification Internal Rule Safety ─────────────────

@pytest.mark.asyncio
async def test_verification_service_recognizes_internal_rule_citations():
    """
    Doğrulama motorunun 'Kural Motoru', 'TCO' gibi iç deterministik hesaplama
    atıflarını dış kaynak sanıp unsupported_citations olarak inconclusive üretmesini önlediğini test eder.
    """
    async with AsyncSessionLocal() as session:
        tenant = await create_test_tenant(session)
        rfq, q1, q2 = await create_rfq_with_quotes(session, tenant)

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        tco1 = make_tco(analysis.id, q1)
        tco2 = make_tco(analysis.id, q2)
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=q1.id,
            reasoning="DEF NEW en ekonomik tekliftir [Kaynak 1: Kural Motoru] ve TCO hesaplaması uygundur [Kaynak 2: TCO Hesaplama].",
            verification_status="pending",
        )
        session.add_all([tco1, tco2, rec])
        await session.commit()
        await session.refresh(rec)

        verif_service = VerificationService(db=session)
        result = await verif_service.verify_recommendation(rec.id)

        # Must NOT be downgraded to inconclusive due to internal citation!
        assert result.verification_status in ["verified", "passed"]
        assert "unsupported_citations" not in (result.verification_notes or "")
