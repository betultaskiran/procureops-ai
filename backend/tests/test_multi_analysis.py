import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.supplier import Supplier
from app.models.rfq import RFQ, RFQItem, RFQStatus, QuoteDocument, ParseStatus
from app.models.quote import Quote, QuoteItem
from app.models.analysis import Analysis, AnalysisStatus, Approval, ApprovalStatus
from app.models.order import PurchaseOrder
from app.services.agent.schemas import AgentRecommendationSchema
from app.services.agent.service import AgentService


async def create_org_and_suppliers(session):
    unique_suffix = uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Test Org {unique_suffix}",
        slug=f"test-org-{unique_suffix}"
    )
    session.add(org)
    await session.flush()

    sup1 = Supplier(name=f"Supplier Alpha {unique_suffix}", organization_id=org.id)
    sup2 = Supplier(name=f"Supplier Beta {unique_suffix}", organization_id=org.id)
    session.add_all([sup1, sup2])
    await session.commit()
    return org, sup1, sup2


def get_mock_agent_output(recommended_quote_id: uuid.UUID | None = None):
    return AgentRecommendationSchema(
        recommended_quote_id=recommended_quote_id,
        justification="Tüm şartları sağlayan ve maliyet avantajı sunan en uygun teklif [Kaynak 1: Politika].",
        trade_off_analysis="Alpha daha uygun fiyat sunarken teslimat süreleri paraleldir.",
        risk_factors=["Tedarikçi teslimat geçmişi izlenmelidir [Kaynak 2: SQL Geçmişi]"],
        confidence_score=92,
        is_human_review_required=False,
    )


# ── Scenario 1: RFQ rules applied when payload omits rules ────────────────────
@pytest.mark.asyncio
async def test_multi_analysis_rfq_rules_fallback_when_omitted():
    """1. Payload'da rules verilmediğinde RFQ'nun kendi alanları (bütçe, teslimat, garanti, ödeme) uygulanmalı."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Server Procurement",
            budget=Decimal("500000.00"),
            max_delivery_days=10,
            min_warranty_months=24,
            payment_terms="net-30",
        )
        session.add(rfq)
        await session.flush()

        # Quote 1: All compliant
        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            currency="TRY",
            subtotal=Decimal("400000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("80000.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("480000.00"),
            delivery_days=7,
            warranty_months=24,
            payment_terms="net-30",
        )
        # Quote 2: Exceeds RFQ delivery days (15 > 10)
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            currency="TRY",
            subtotal=Decimal("350000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("70000.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("420000.00"),
            delivery_days=15,  # FAIL
            warranty_months=24,
            payment_terms="net-30",
        )
        session.add_all([q1, q2])
        await session.commit()
        rfq_id = str(rfq.id)
        q1_id = q1.id
        q2_id = q2.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(
            AgentService,
            "generate_recommendation",
            new_callable=AsyncMock
        ) as mock_agent:
            from app.models.analysis import Recommendation, VerificationStatus
            async def fake_gen(analysis_id, organization_id):
                rec = Recommendation(
                    analysis_id=analysis_id,
                    recommended_quote_id=q1_id,
                    reasoning="Uygun teklif [Kaynak 1: Politika].",
                    verification_status=VerificationStatus.PENDING,
                )
                session = AsyncSessionLocal()
                async with session:
                    session.add(rec)
                    await session.commit()
                    await session.refresh(rec)
                return rec
            mock_agent.side_effect = fake_gen

            # Request with no rules in payload
            res = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={})
            assert res.status_code == 200, res.text
            data = res.json()

            # Q1 delivery check PASS (7 <= 10)
            q1_checks = [c for c in data["compliance_checks"] if c["quote_id"] == str(q1_id)]
            q1_delivery = next(c for c in q1_checks if c["rule_name"] == "max_delivery_days")
            assert q1_delivery["result"] == "pass"
            assert q1_delivery["required_value"] == "10"

            # Q2 delivery check FAIL (15 > 10)
            q2_checks = [c for c in data["compliance_checks"] if c["quote_id"] == str(q2_id)]
            q2_delivery = next(c for c in q2_checks if c["rule_name"] == "max_delivery_days")
            assert q2_delivery["result"] == "fail"
            assert q2_delivery["actual_value"] == "15"
            assert q2_delivery["required_value"] == "10"


# ── Scenario 2: Independent TCO and compliance per quote ─────────────────────
@pytest.mark.asyncio
async def test_multi_analysis_independent_tco_and_compliance():
    """2. Çoklu analizde her teklif bağımsız TCO ve kural kontrolüne tabi tutulmalı."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Hardware Purchase",
            budget=Decimal("300000.00"),
            max_delivery_days=14,
            min_warranty_months=12,
            payment_terms="net-30",
        )
        session.add(rfq)
        await session.flush()

        # Quote 1: 100k + 20k VAT + 5k ship - 10k disc = 115k
        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            currency="TRY",
            subtotal=Decimal("100000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("20000.00"),
            shipping_cost=Decimal("5000.00"),
            discount_amount=Decimal("10000.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("113000.00"),
            delivery_days=7,
            warranty_months=24,
            payment_terms="net-30",
        )
        # Quote 2: 120k + 24k VAT = 144k
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            currency="TRY",
            subtotal=Decimal("120000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("24000.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("144000.00"),
            delivery_days=10,
            warranty_months=12,
            payment_terms="net-30",
        )
        session.add_all([q1, q2])
        await session.commit()
        rfq_id = str(rfq.id)
        q1_id = str(q1.id)
        q2_id = str(q2.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(
            AgentService,
            "generate_recommendation",
            new_callable=AsyncMock
        ) as mock_agent:
            from app.models.analysis import Recommendation, VerificationStatus
            async def fake_gen(analysis_id, organization_id):
                rec = Recommendation(
                    analysis_id=analysis_id,
                    recommended_quote_id=uuid.UUID(q1_id),
                    reasoning="Uygun teklif [Kaynak 1: Politika].",
                    verification_status=VerificationStatus.PENDING,
                )
                session = AsyncSessionLocal()
                async with session:
                    session.add(rec)
                    await session.commit()
                    await session.refresh(rec)
                return rec
            mock_agent.side_effect = fake_gen

            res = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={})
            assert res.status_code == 200
            data = res.json()

            assert len(data["tco_results"]) == 2
            tco1 = next(t for t in data["tco_results"] if t["quote_id"] == q1_id)
            tco2 = next(t for t in data["tco_results"] if t["quote_id"] == q2_id)

            # TCO 1: (100k - 10k)*1.2 + 5k = 108k + 5k = 113k
            assert tco1["total_tco"] == 113000.0
            # TCO 2: 120k * 1.2 = 144k
            assert tco2["total_tco"] == 144000.0


# ── Scenario 3: Missing financial data marked with warnings ───────────────────
@pytest.mark.asyncio
async def test_multi_analysis_missing_financial_data_marked_with_warnings():
    """3. Eksik finansal veri (KDV, kargo) sessizce sıfır kabul edilmemeli, uyarı üretmeli."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Office Equipment", budget=Decimal("100000.00"))
        session.add(rfq)
        await session.flush()

        # Quote 1: vat_rate and shipping_cost are None
        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            currency="TRY",
            subtotal=Decimal("50000.00"),
            vat_rate=None,  # MISSING
            vat_amount=Decimal("0.00"),
            shipping_cost=None,  # MISSING
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("50000.00"),
            delivery_days=5,
            warranty_months=12,
            payment_terms="net-30",
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            currency="TRY",
            subtotal=Decimal("55000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("11000.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("66000.00"),
            delivery_days=5,
            warranty_months=12,
            payment_terms="net-30",
        )
        session.add_all([q1, q2])
        await session.commit()
        rfq_id = str(rfq.id)
        q1_id = str(q1.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(
            AgentService,
            "generate_recommendation",
            new_callable=AsyncMock
        ) as mock_agent:
            from app.models.analysis import Recommendation, VerificationStatus
            async def fake_gen(analysis_id, organization_id):
                rec = Recommendation(
                    analysis_id=analysis_id,
                    recommended_quote_id=uuid.UUID(q1_id),
                    reasoning="Uygun teklif [Kaynak 1: Politika].",
                    verification_status=VerificationStatus.PENDING,
                )
                session = AsyncSessionLocal()
                async with session:
                    session.add(rec)
                    await session.commit()
                    await session.refresh(rec)
                return rec
            mock_agent.side_effect = fake_gen

            res = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={})
            assert res.status_code == 200
            data = res.json()

            # TCO calculation note contains warning
            tco1 = next(t for t in data["tco_results"] if t["quote_id"] == q1_id)
            assert "[UYARI: EKSİK MALİYET VERİSİ" in tco1["calculation_notes"]
            assert "vat_rate" in tco1["calculation_notes"]
            assert "shipping_cost" in tco1["calculation_notes"]

            # Compliance check has warning for cost_completeness
            q1_checks = [c for c in data["compliance_checks"] if c["quote_id"] == q1_id]
            cost_check = next(c for c in q1_checks if c["rule_name"] == "cost_completeness")
            assert cost_check["result"] == "warning"
            assert "Eksik maliyet kalemleri" in cost_check["notes"]


# ── Scenario 4: Currency mismatch returns 400 error ───────────────────────────
@pytest.mark.asyncio
async def test_multi_analysis_currency_mismatch_returns_400():
    """4. Farklı para birimlerine sahip teklifler doğrudan kıyaslanamaz, 400 dönmeli."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Multi Currency RFQ")
        session.add(rfq)
        await session.flush()

        # Quote 1 in USD, Quote 2 in EUR
        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            currency="USD",
            subtotal=Decimal("10000.00"),
            total_price=Decimal("10000.00"),
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            currency="EUR",
            subtotal=Decimal("9000.00"),
            total_price=Decimal("9000.00"),
        )
        session.add_all([q1, q2])
        await session.commit()
        rfq_id = str(rfq.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={})
        assert res.status_code == 400
        assert "farklı para birimleri" in res.json()["detail"].lower()
        assert "EUR, USD" in res.json()["detail"] or "USD, EUR" in res.json()["detail"]


# ── Scenario 5: Fewer than 2 quotes returns 400 error ─────────────────────────
@pytest.mark.asyncio
async def test_multi_analysis_fewer_than_two_quotes_returns_400():
    """5. Karşılaştırmalı analiz için 2'den az teklif varsa 400 Bad Request dönmeli."""
    async with AsyncSessionLocal() as session:
        org, sup1, _ = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Single Quote RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            currency="TRY",
            subtotal=Decimal("10000.00"),
            total_price=Decimal("10000.00"),
        )
        session.add(q1)
        await session.commit()
        rfq_id = str(rfq.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={})
        assert res.status_code == 400
        assert "en az 2 teklif gereklidir" in res.json()["detail"].lower()


# ── Scenario 6: Low extraction confidence adds warning check ──────────────────
@pytest.mark.asyncio
async def test_multi_analysis_low_extraction_confidence_warning():
    """6. Güven skoru 0.70'in altındaki teklifler için warning check eklenmeli."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Confidence Test RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            currency="TRY",
            subtotal=Decimal("10000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("2000.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("12000.00"),
            extraction_confidence=Decimal("0.65"),  # < 0.70 WARNING
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            currency="TRY",
            subtotal=Decimal("12000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("2400.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("14400.00"),
            extraction_confidence=Decimal("0.95"),
        )
        session.add_all([q1, q2])
        await session.commit()
        rfq_id = str(rfq.id)
        q1_id = str(q1.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(
            AgentService,
            "generate_recommendation",
            new_callable=AsyncMock
        ) as mock_agent:
            from app.models.analysis import Recommendation, VerificationStatus
            async def fake_gen(analysis_id, organization_id):
                rec = Recommendation(
                    analysis_id=analysis_id,
                    recommended_quote_id=uuid.UUID(q1_id),
                    reasoning="Uygun teklif [Kaynak 1: Politika].",
                    verification_status=VerificationStatus.PENDING,
                )
                session = AsyncSessionLocal()
                async with session:
                    session.add(rec)
                    await session.commit()
                    await session.refresh(rec)
                return rec
            mock_agent.side_effect = fake_gen

            res = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={})
            assert res.status_code == 200
            data = res.json()

            q1_checks = [c for c in data["compliance_checks"] if c["quote_id"] == q1_id]
            conf_check = next(c for c in q1_checks if c["rule_name"] == "extraction_confidence")
            assert conf_check["result"] == "warning"
            assert conf_check["actual_value"] == "0.65"
            assert "Düşük güven skoru" in conf_check["notes"]


# ── Scenario 7: Cancelled RFQ cannot be analyzed or reviewed ─────────────────
@pytest.mark.asyncio
async def test_multi_analysis_cancelled_rfq_cannot_be_analyzed_or_reviewed():
    """7. İptal edilmiş bir RFQ üzerinde analiz veya onay işletilemez, 400 dönmeli."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Cancelled RFQ",
            status="cancelled"
        )
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, currency="TRY", subtotal=Decimal("10000.00"), total_price=Decimal("10000.00"))
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, currency="TRY", subtotal=Decimal("12000.00"), total_price=Decimal("12000.00"))
        session.add_all([q1, q2])

        # Analysis belonging to this cancelled RFQ
        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.commit()
        rfq_id = str(rfq.id)
        analysis_id = str(analysis.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Analyze attempt on cancelled RFQ
        res_analyze = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={})
        assert res_analyze.status_code == 400
        detail_analyze = res_analyze.json()["detail"].casefold()
        assert "cancelled" in detail_analyze or "iptal" in detail_analyze

        # Review attempt on cancelled RFQ
        res_review = await client.post(f"/api/v1/analyses/{analysis_id}/review", json={
            "status": "approved"
        })
        assert res_review.status_code == 400
        detail_review = res_review.json()["detail"].casefold()
        assert "cancelled" in detail_review or "iptal" in detail_review


# ── Scenario 8: Cross-tenant analysis and review rejected with 403 ────────────
@pytest.mark.asyncio
async def test_multi_analysis_cross_tenant_rejected_403():
    """8. Farklı organizasyon kimliği ile gelen analiz ve onay talepleri 403 ile reddedilmeli."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)
        different_org = str(uuid.uuid4())

        rfq = RFQ(organization_id=org.id, title="Tenant RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, currency="TRY", subtotal=Decimal("10000.00"), total_price=Decimal("10000.00"))
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, currency="TRY", subtotal=Decimal("12000.00"), total_price=Decimal("12000.00"))
        session.add_all([q1, q2])

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.commit()
        rfq_id = str(rfq.id)
        analysis_id = str(analysis.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Cross-tenant analyze request
        res_analyze = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={
            "organization_id": different_org
        })
        assert res_analyze.status_code == 403
        assert "organizasyona ait olmayan" in res_analyze.json()["detail"]

        # Cross-tenant review request
        res_review = await client.post(f"/api/v1/analyses/{analysis_id}/review", json={
            "status": "approved",
            "organization_id": different_org
        })
        assert res_review.status_code == 403
        assert "organizasyona ait olmayan" in res_review.json()["detail"]


# ── Scenario 9: Repeated approval blocked from creating duplicate PO ──────────
@pytest.mark.asyncio
async def test_multi_analysis_repeated_approval_blocks_duplicate_po():
    """9. Aktif bir PO var iken aynı RFQ için tekrar onay verilmesi engellenmeli (400)."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="PO RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            currency="TRY",
            subtotal=Decimal("10000.00"),
            total_price=Decimal("10000.00"),
            is_compliant=True
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            currency="TRY",
            subtotal=Decimal("12000.00"),
            total_price=Decimal("12000.00"),
            is_compliant=True
        )
        session.add_all([q1, q2])

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.commit()
        analysis_id = str(analysis.id)
        q1_id = str(q1.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1st approval -> creates PO
        res1 = await client.post(f"/api/v1/analyses/{analysis_id}/review", json={
            "status": "approved",
            "selected_quote_id": q1_id
        })
        assert res1.status_code == 201

        # 2nd approval -> must be blocked
        res2 = await client.post(f"/api/v1/analyses/{analysis_id}/review", json={
            "status": "approved",
            "selected_quote_id": q1_id
        })
        assert res2.status_code == 400
        assert "aktif bir sipariş emri" in res2.json()["detail"].lower()


# ── Scenario 10: Running analysis cannot be duplicated (409 Conflict) ─────────
@pytest.mark.asyncio
async def test_multi_analysis_concurrency_lock_returns_409():
    """10. Zaten RUNNING durumunda analizi bulunan bir RFQ için mükerrer analiz 409 dönmeli."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Concurrency Lock RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, currency="TRY", subtotal=Decimal("10000.00"), total_price=Decimal("10000.00"))
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, currency="TRY", subtotal=Decimal("12000.00"), total_price=Decimal("12000.00"))
        session.add_all([q1, q2])

        # An analysis is already in progress
        running_analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.RUNNING.value)
        session.add(running_analysis)
        await session.commit()
        rfq_id = str(rfq.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={})
        assert res.status_code == 409
        assert "devam eden aktif bir analiz" in res.json()["detail"]


# ── Scenario 11: Quote changes mark previous analysis as stale ────────────────
@pytest.mark.asyncio
async def test_multi_analysis_stale_detection_on_quote_change():
    """11. Tekliflerde değişiklik yapıldığında veya yeni teklif eklendiğinde analiz is_stale=True dönmeli."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Staleness RFQ", budget=Decimal("100000.00"))
        session.add(rfq)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            currency="TRY",
            subtotal=Decimal("10000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("2000.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("12000.00"),
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            currency="TRY",
            subtotal=Decimal("12000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("2400.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("14400.00"),
        )
        session.add_all([q1, q2])
        await session.commit()
        rfq_id = str(rfq.id)
        q1_id = q1.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(
            AgentService,
            "generate_recommendation",
            new_callable=AsyncMock
        ) as mock_agent:
            from app.models.analysis import Recommendation, VerificationStatus
            async def fake_gen(analysis_id, organization_id):
                rec = Recommendation(
                    analysis_id=analysis_id,
                    recommended_quote_id=q1_id,
                    reasoning="Uygun teklif [Kaynak 1: Politika].",
                    verification_status=VerificationStatus.PENDING,
                )
                session = AsyncSessionLocal()
                async with session:
                    session.add(rec)
                    await session.commit()
                    await session.refresh(rec)
                return rec
            mock_agent.side_effect = fake_gen

            # Run analysis -> is_stale is False
            res1 = await client.post(f"/api/v1/rfqs/{rfq_id}/analyze", json={})
            assert res1.status_code == 200
            assert res1.json()["is_stale"] is False

            # Verify latest analysis endpoint returns is_stale False
            res_latest1 = await client.get(f"/api/v1/rfqs/{rfq_id}/analysis")
            assert res_latest1.status_code == 200
            assert res_latest1.json()["is_stale"] is False

            # Add a 3rd quote to RFQ (invalidating previous 2-quote analysis)
            async with AsyncSessionLocal() as session:
                sup3 = Supplier(name=f"Supplier Gamma {uuid.uuid4().hex[:6]}", organization_id=org.id)
                session.add(sup3)
                await session.flush()
                q3 = Quote(
                    rfq_id=uuid.UUID(rfq_id),
                    supplier_id=sup3.id,
                    currency="TRY",
                    subtotal=Decimal("8000.00"),
                    total_price=Decimal("8000.00"),
                )
                session.add(q3)
                await session.commit()

            # Now GET latest analysis must report is_stale=True
            res_latest2 = await client.get(f"/api/v1/rfqs/{rfq_id}/analysis")
            assert res_latest2.status_code == 200
            assert res_latest2.json()["is_stale"] is True


# ── Scenario 12: Dynamic RAG query retains RFQ scope & tenant isolation ───────
@pytest.mark.asyncio
async def test_multi_analysis_dynamic_rag_query_and_tenant_scoping():
    """12. Dinamik RAG sorgusu RFQ başlığını, kalemlerini ve şartlarını içermeli; organizasyon id güvenli iletilmeli."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Endüstriyel Sunucu Tedariği",
            budget=Decimal("500000.00"),
            max_delivery_days=21,
            min_warranty_months=36,
            payment_terms="net-45",
        )
        session.add(rfq)
        await session.flush()

        item1 = RFQItem(rfq_id=rfq.id, line_number=1, description="Rack Mount GPU Server", quantity=5, unit="Adet")
        item2 = RFQItem(rfq_id=rfq.id, line_number=2, description="100Gbps Ağ Kartı", quantity=10, unit="Adet")
        session.add_all([item1, item2])

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, currency="TRY", subtotal=Decimal("400000.00"), total_price=Decimal("400000.00"))
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, currency="TRY", subtotal=Decimal("450000.00"), total_price=Decimal("450000.00"))
        session.add_all([q1, q2])
        await session.commit()
        from sqlalchemy.orm import selectinload
        rfq_res = await session.execute(
            select(RFQ).where(RFQ.id == rfq.id).options(selectinload(RFQ.items))
        )
        loaded_rfq = rfq_res.scalars().first()
        rfq_id = rfq.id
        org_id = str(org.id)

    # Test dynamic query builder
    agent_service = AgentService(db=session)
    query = agent_service._build_dynamic_rag_query(loaded_rfq, [q1, q2])
    assert "Endüstriyel Sunucu Tedariği" in query
    assert "Rack Mount GPU Server" in query
    assert "100Gbps Ağ Kartı" in query
    assert "21 gün" in query
    assert "36 ay" in query
    assert "net-45" in query

    # Test tenant-safe retrieval call
    with patch.object(agent_service.rag, "retrieve_context", new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = "İlgili politika maddeleri..."
        with patch.object(agent_service.llm, "extract_structured", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = get_mock_agent_output(q1.id)

            async with AsyncSessionLocal() as session:
                analysis = Analysis(rfq_id=rfq_id, status=AnalysisStatus.RUNNING.value)
                session.add(analysis)
                await session.commit()

                # Call AgentService with tenant org
                agent_service.db = session
                await agent_service.generate_recommendation(analysis.id, organization_id=org_id)

                # Ensure retrieve_context received exact organization_id, NOT "None"
                mock_retrieve.assert_called_once()
                call_kwargs = mock_retrieve.call_args.kwargs
                assert call_kwargs["organization_id"] == org_id
                assert call_kwargs["organization_id"] != "None"
                assert "Endüstriyel Sunucu Tedariği" in call_kwargs["query"]


# ── Scenario 13: Non-compliant quote approval requires exception_approved ─────
@pytest.mark.asyncio
async def test_multi_analysis_non_compliant_quote_approval_safety():
    """13. Deterministik kuralı geçemeyen teklif standart 'approved' ile onaylanamaz; exception_approved ve acknowledge zorunludur."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2 = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Non-Compliant Approval RFQ")
        session.add(rfq)
        await session.flush()

        # Non-compliant quote (is_compliant = False)
        q_fail = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            currency="TRY",
            subtotal=Decimal("10000.00"),
            total_price=Decimal("10000.00"),
            is_compliant=False,  # Failed deterministic rule
        )
        q_pass = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            currency="TRY",
            subtotal=Decimal("12000.00"),
            total_price=Decimal("12000.00"),
            is_compliant=True,
        )
        session.add_all([q_fail, q_pass])

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.commit()
        analysis_id = str(analysis.id)
        fail_id = str(q_fail.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Standard "approved" on non-compliant quote -> 400
        res_fail_std = await client.post(f"/api/v1/analyses/{analysis_id}/review", json={
            "status": "approved",
            "selected_quote_id": fail_id
        })
        assert res_fail_std.status_code == 400
        assert "exception_approved" in res_fail_std.json()["detail"]

        # "exception_approved" without acknowledged_policy_violation -> 400
        res_fail_no_ack = await client.post(f"/api/v1/analyses/{analysis_id}/review", json={
            "status": "exception_approved",
            "selected_quote_id": fail_id,
            "acknowledged_policy_violation": False
        })
        assert res_fail_no_ack.status_code == 400

        # "exception_approved" with acknowledged_policy_violation=True -> succeeds (201)
        res_success = await client.post(f"/api/v1/analyses/{analysis_id}/review", json={
            "status": "exception_approved",
            "selected_quote_id": fail_id,
            "acknowledged_policy_violation": True,
            "comment": "Yönetici onayı ile istisnai satın alma yapıldı."
        })
        assert res_success.status_code == 201
        assert res_success.json()["status"] == "exception_approved"
        assert res_success.json()["acknowledged_policy_violation"] is True
