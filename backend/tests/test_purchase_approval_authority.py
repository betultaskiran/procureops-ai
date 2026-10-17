"""
backend/tests/test_purchase_approval_authority.py

Phase 12.1 — Purchase Approval Authority & Multi-Level Approval Audit Test Suite

Enforces and audits company procurement policy authority matrix:
- Article 1.1: Purchases <= 250,000.00 TRY can be completed by Department Manager (status: issued).
- Article 1.2: Purchases > 250,000.00 TRY require joint Purchasing Director & CFO approval.
- An exception to a technical rule (exception_approved) must NOT bypass financial approval authority.
- Missing required higher-level approvals hold the purchase order in DRAFT status,
  preventing automated supplier issuance and delivery execution.
- Verifies role model and database schema limitations for multi-level approvals.
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
    ComplianceCheck,
    ComplianceResult,
)
from app.models.order import PurchaseOrder, PurchaseOrderStatus
from app.core.security import create_access_token


class OrgContext:
    def __init__(self, org: Organization, user: User, token: str):
        self.org = org
        self.user = user
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}


async def create_test_org(session, role: UserRole = UserRole.MANAGER) -> tuple[OrgContext, Supplier]:
    suffix = uuid.uuid4().hex[:6]
    org = Organization(name=f"Authority Test Org {suffix}", slug=f"authority-test-{suffix}")
    session.add(org)
    await session.flush()

    user = User(
        organization_id=org.id,
        email=f"manager_{suffix}@authority.com",
        full_name=f"Manager {suffix}",
        hashed_password="mock",
        role=role.value,
        is_active=True,
    )
    supplier = Supplier(
        organization_id=org.id,
        name=f"DEF NEW Supplier {suffix}",
        email=f"def_{suffix}@supplier.com",
        is_active=True,
    )
    session.add_all([user, supplier])
    await session.commit()
    await session.refresh(user)

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role, "org_id": str(org.id)}
    )
    return OrgContext(org, user, token), supplier


def make_tco_result(analysis_id: uuid.UUID, quote_id: uuid.UUID, amount: Decimal) -> TCOResult:
    return TCOResult(
        analysis_id=analysis_id,
        quote_id=quote_id,
        subtotal=amount,
        vat_amount=Decimal("0.00"),
        shipping_cost=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        other_costs=Decimal("0.00"),
        total_tco=amount,
        currency="TRY",
    )


# ── Scenario 1: Amount below 250,000 TRY is issued by single manager ──────────
@pytest.mark.asyncio
async def test_spending_authority_below_250k_single_manager_issues_po():
    """
    1. 250.000 TL altındaki satın alımlarda (örn: 150.000 TL) Departman Müdürü
    tek başına onaylayabilir; PO doğrudan ISSUED durumuna geçer ve teslimat aksiyonu açılır.
    """
    amount = Decimal("150000.00")
    async with AsyncSessionLocal() as session:
        ctx, supplier = await create_test_org(session, role=UserRole.MANAGER)

        rfq = RFQ(organization_id=ctx.org.id, title="Sub-250k Purchase RFQ")
        session.add(rfq)
        await session.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="TRY",
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

        tco = make_tco_result(analysis.id, quote.id, amount)
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=quote.id,
            reasoning="Uygun bütçeli alım",
            verification_status=VerificationStatus.VERIFIED.value,
        )
        session.add_all([tco, rec])
        await session.commit()

        analysis_id = str(analysis.id)
        quote_id = str(quote.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ctx.headers) as client:
        res = await client.post(
            f"/api/v1/analyses/{analysis_id}/review",
            json={"status": "approved", "comment": "Bütçe limitleri dahilinde onaylandı."},
        )
        assert res.status_code == 201

        # PO durumunu incele
        async with AsyncSessionLocal() as session:
            po = (
                await session.execute(
                    select(PurchaseOrder).where(PurchaseOrder.quote_id == uuid.UUID(quote_id))
                )
            ).scalar_one()
            assert po.status == PurchaseOrderStatus.ISSUED.value

        # Orders API detayında 'deliver' aksiyonunun açık olduğunu doğrula
        order_res = await client.get(f"/api/v1/orders/{po.id}")
        assert order_res.status_code == 200
        order_data = order_res.json()
        assert order_data["status"] == "issued"
        assert "deliver" in order_data["allowed_actions"]


# ── Scenario 2: Amount exactly equal to 250,000 TRY is issued by single manager ─
@pytest.mark.asyncio
async def test_spending_authority_exact_250k_single_manager_issues_po():
    """
    2. Tam 250.000,00 TL olan satın alımlarda (Madde 1.1: 250.000 TL ve altındaki tüm satın alımlar)
    Departman Müdürü onayıyla PO doğrudan ISSUED durumuna geçer.
    """
    amount = Decimal("250000.00")
    async with AsyncSessionLocal() as session:
        ctx, supplier = await create_test_org(session, role=UserRole.MANAGER)

        rfq = RFQ(organization_id=ctx.org.id, title="Exact 250k Purchase RFQ")
        session.add(rfq)
        await session.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="TRY",
            subtotal=amount,
            total_price=amount,
            delivery_days=10,
            is_compliant=True,
        )
        session.add(quote)
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        tco = make_tco_result(analysis.id, quote.id, amount)
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=quote.id,
            reasoning="Sınır bütçeli alım",
            verification_status=VerificationStatus.VERIFIED.value,
        )
        session.add_all([tco, rec])
        await session.commit()

        analysis_id = str(analysis.id)
        quote_id = str(quote.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ctx.headers) as client:
        res = await client.post(
            f"/api/v1/analyses/{analysis_id}/review",
            json={"status": "approved", "comment": "250.000 TL sınırında standart onay."},
        )
        assert res.status_code == 201

        async with AsyncSessionLocal() as session:
            po = (
                await session.execute(
                    select(PurchaseOrder).where(PurchaseOrder.quote_id == uuid.UUID(quote_id))
                )
            ).scalar_one()
            assert po.status == PurchaseOrderStatus.ISSUED.value


# ── Scenario 3: Amount above 250,000 TRY is held in DRAFT status ───────────────
@pytest.mark.asyncio
async def test_spending_authority_above_250k_single_manager_leaves_po_in_draft():
    """
    3. 250.000 TL üzerindeki alımlarda (örn: DEF NEW 359.330,80 TL) tek bir Departman Müdürü
    onayladığında, Madde 1.2 gereği zorunlu Satın Alma Direktörü ve CFO müşterek ek onayı
    henüz tamamlanmadığı için PO DRAFT (Taslak) durumunda tutulur; ISSUED durumuna GEÇEMEZ.
    """
    amount = Decimal("359330.80")
    async with AsyncSessionLocal() as session:
        ctx, supplier = await create_test_org(session, role=UserRole.MANAGER)

        rfq = RFQ(organization_id=ctx.org.id, title="Target DEF NEW 359k RFQ")
        session.add(rfq)
        await session.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="TRY",
            subtotal=amount,
            total_price=amount,
            delivery_days=7,
            warranty_months=24,
            is_compliant=True,
        )
        session.add(quote)
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        tco = make_tco_result(analysis.id, quote.id, amount)
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=quote.id,
            reasoning="DEF NEW önerisi [Kaynak: BİLGİ TEKNOLOJİLERİ DONANIM VE HİZMET SEVİYESİ POLİTİKASI, Madde 1.2]",
            verification_status=VerificationStatus.VERIFIED.value,
        )
        session.add_all([tco, rec])
        await session.commit()

        analysis_id = str(analysis.id)
        quote_id = str(quote.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ctx.headers) as client:
        res = await client.post(
            f"/api/v1/analyses/{analysis_id}/review",
            json={"status": "approved", "comment": "Yönetici ön onayı verildi."},
        )
        assert res.status_code == 201

        # Veritabanında PO'nun ISSUED değil, DRAFT olarak tutulduğunu doğrula
        async with AsyncSessionLocal() as session:
            po = (
                await session.execute(
                    select(PurchaseOrder).where(PurchaseOrder.quote_id == uuid.UUID(quote_id))
                )
            ).scalar_one()
            assert po.status == PurchaseOrderStatus.DRAFT.value
            assert po.status != PurchaseOrderStatus.ISSUED.value

        # Orders API detayında 'deliver' aksiyonunun OLMADIĞINI, yalnızca 'cancel' olduğunu doğrula
        order_res = await client.get(f"/api/v1/orders/{po.id}")
        assert order_res.status_code == 200
        order_data = order_res.json()
        assert order_data["status"] == "draft"
        assert "deliver" not in order_data["allowed_actions"]
        assert "cancel" in order_data["allowed_actions"]


# ── Scenario 4: Missing required approvals prevent order execution / delivery ──
@pytest.mark.asyncio
async def test_missing_required_approvals_prevent_delivery_execution():
    """
    4. Yüksek tutarlı (359k) sipariş taslakta (DRAFT) kaldığı için, gerekli ek onaylar
    tamamlanmadan tedarikçiye teslimat veya icra aşamasına geçilemez (HTTP 400 döner).
    """
    amount = Decimal("359330.80")
    async with AsyncSessionLocal() as session:
        ctx, supplier = await create_test_org(session, role=UserRole.MANAGER)

        rfq = RFQ(organization_id=ctx.org.id, title="Delivery Block RFQ")
        session.add(rfq)
        await session.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="TRY",
            subtotal=amount,
            total_price=amount,
            is_compliant=True,
        )
        session.add(quote)
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        tco = make_tco_result(analysis.id, quote.id, amount)
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=quote.id,
            reasoning="359k alım",
            verification_status=VerificationStatus.VERIFIED.value,
        )
        session.add_all([tco, rec])
        await session.commit()

        analysis_id = str(analysis.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ctx.headers) as client:
        # 1. Analizi onayla -> PO DRAFT oluşur
        res_review = await client.post(
            f"/api/v1/analyses/{analysis_id}/review",
            json={"status": "approved"},
        )
        assert res_review.status_code == 201

        async with AsyncSessionLocal() as session:
            po = (
                await session.execute(
                    select(PurchaseOrder).where(PurchaseOrder.quote_id == quote.id)
                )
            ).scalar_one()
            po_id = str(po.id)

        # 2. Teslimat endpoint'ini çağır -> DRAFT olduğu için 400 Bad Request dönmeli
        res_deliver = await client.post(
            f"/api/v1/orders/{po_id}/deliver",
            json={"actual_delivery_date": "2026-10-20", "delivery_notes": "Erken teslimat"},
        )
        assert res_deliver.status_code == 400
        assert "taslak" in res_deliver.json()["detail"].lower()


# ── Scenario 5: Technical exception approval cannot bypass spending authority ──
@pytest.mark.asyncio
async def test_technical_exception_approval_cannot_bypass_spending_authority():
    """
    5. Bir teknik kural ihlaline (örn: teslimat süresi aşımı) verilen 'exception_approved'
    onayı, finansal harcama yetki matrisini (250k) ATLATAMAZ. Sipariş tutarı 400.000 TL ise,
    exception_approved verilse dahi PO DRAFT kalır; ISSUED durumuna geçemez.
    """
    amount = Decimal("400000.00")
    async with AsyncSessionLocal() as session:
        ctx, supplier = await create_test_org(session, role=UserRole.MANAGER)

        rfq = RFQ(organization_id=ctx.org.id, title="Exception Spending Authority RFQ")
        session.add(rfq)
        await session.flush()

        # Deterministik kuralı geçemeyen teknik teklif (örn: is_compliant=False)
        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="TRY",
            subtotal=amount,
            total_price=amount,
            is_compliant=False,  # Teknik kural ihlali
        )
        session.add(quote)
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        tco = make_tco_result(analysis.id, quote.id, amount)
        check = ComplianceCheck(
            analysis_id=analysis.id,
            quote_id=quote.id,
            rule_name="max_delivery_days",
            rule_description="Maksimum teslimat süresi kontrolü",
            result=ComplianceResult.FAIL,
            actual_value="25",
            required_value="14",
            notes="Teslimat süresi sınırı aşıyor.",
        )
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=quote.id,
            reasoning="İstisna onay gerektiren teklif",
            verification_status=VerificationStatus.FAILED.value,
        )
        session.add_all([tco, check, rec])
        await session.commit()

        analysis_id = str(analysis.id)
        quote_id = str(quote.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ctx.headers) as client:
        # Teknik istisna onayı gönder
        res_review = await client.post(
            f"/api/v1/analyses/{analysis_id}/review",
            json={
                "status": "exception_approved",
                "acknowledged_policy_violation": True,
                "comment": "Teknik teslimat gecikmesi istisna olarak kabul edildi.",
            },
        )
        assert res_review.status_code == 201

        # Finansal tutar 400k (> 250k) olduğu için teknik exception finansal limiti bypass edemez!
        async with AsyncSessionLocal() as session:
            po = (
                await session.execute(
                    select(PurchaseOrder).where(PurchaseOrder.quote_id == uuid.UUID(quote_id))
                )
            ).scalar_one()
            assert po.status == PurchaseOrderStatus.DRAFT.value
            assert po.status != PurchaseOrderStatus.ISSUED.value


# ── Scenario 6: Role model audit documents absence of CFO and Director roles ───
@pytest.mark.asyncio
async def test_role_model_audit_proves_lack_of_director_and_cfo_roles():
    """
    6. Rol modeli denetimi: UserRole enum'ında yalnızca 'admin', 'manager', 'employee', 'viewer'
    bulunduğunu; ayrı 'cfo', 'purchasing_director' veya 'board' rollerinin bulunmadığını belgeler.
    """
    roles = [r.value for r in UserRole]
    assert "admin" in roles
    assert "manager" in roles
    assert "employee" in roles
    assert "viewer" in roles

    # Mimari Açık: Ayrı CFO ve Satın Alma Direktörü rolleri mevcut sistemde tanımlı değil
    assert "cfo" not in roles
    assert "purchasing_director" not in roles
    assert "director" not in roles


# ── Scenario 7: Approval schema audit documents single-reviewer limitation ─────
@pytest.mark.asyncio
async def test_approval_schema_audit_proves_single_reviewer_limitation():
    """
    7. Veri modeli denetimi: Approval modelinde yalnızca tek bir 'reviewer_id' sütunu bulunduğunu,
    sıralı/müşterek (joint) onay adımları veya onay zinciri (approval tiers) tablosunun bulunmadığını belgeler.
    """
    from sqlalchemy import inspect
    mapper = inspect(Approval)
    columns = [c.key for c in mapper.column_attrs]

    assert "reviewer_id" in columns
    assert "status" in columns
    assert "analysis_id" in columns

    # Mimari Açık: İkincil onaycı, onay kademesi veya müşterek imza alanları tabloda yok
    assert "secondary_reviewer_id" not in columns
    assert "cfo_reviewer_id" not in columns
    assert "tier" not in columns
    assert "required_signatures" not in columns


# ── Scenario 8: Non-TRY currencies cannot be silently compared to TRY threshold ─
@pytest.mark.asyncio
async def test_spending_authority_non_try_currency_held_in_draft():
    """
    8. Döviz Güvenliği: USD veya EUR cinsinden teklifler (örn: 10.000 USD) sessizce
    250.000 TRY eşiğiyle kıyaslanıp doğrudan ISSUED yapılamaz. Kur riski ve bütçe
    yetkisi denetimi için çok kademeli onay gelene kadar PO DRAFT durumunda tutulur.
    """
    amount = Decimal("10000.00")  # 10,000 USD (nominal değeri 250k'dan küçük ama TRY değil)
    async with AsyncSessionLocal() as session:
        ctx, supplier = await create_test_org(session, role=UserRole.MANAGER)

        rfq = RFQ(organization_id=ctx.org.id, title="USD Currency Purchase RFQ")
        session.add(rfq)
        await session.flush()

        quote = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="USD",
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

        tco = TCOResult(
            analysis_id=analysis.id,
            quote_id=quote.id,
            subtotal=amount,
            vat_amount=Decimal("0.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_tco=amount,
            currency="USD",
        )
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=quote.id,
            reasoning="USD dövizli teklif",
            verification_status=VerificationStatus.VERIFIED.value,
        )
        session.add_all([tco, rec])
        await session.commit()

        analysis_id = str(analysis.id)
        quote_id = str(quote.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=ctx.headers) as client:
        res = await client.post(
            f"/api/v1/analyses/{analysis_id}/review",
            json={"status": "approved", "comment": "Dövizli teklif standart onayı."},
        )
        assert res.status_code == 201

        # Non-TRY olduğu için PO DRAFT kalmalı, ISSUED olmamalı
        async with AsyncSessionLocal() as session:
            po = (
                await session.execute(
                    select(PurchaseOrder).where(PurchaseOrder.quote_id == uuid.UUID(quote_id))
                )
            ).scalar_one()
            assert po.status == PurchaseOrderStatus.DRAFT.value
            assert po.status != PurchaseOrderStatus.ISSUED.value
