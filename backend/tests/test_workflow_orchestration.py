"""
backend/tests/test_workflow_orchestration.py

Phase 10: AI Workflow & Agent Orchestration Doğrulama Test Süiti.

Aşağıdaki 12 senaryoyu kapsar:
1. Başarılı uçtan uca analiz (Tüm 5 aşama completed, stage_results izlenebilir)
2. Hard-rule ihlali (Elenen teklif LLM tarafından seçilirse bağımsız doğrulama override eder)
3. Yetersiz RAG kanıtı (insufficient_evidence durumu ve human review gereksinimi)
4. LLM'nin desteklenmeyen iddia üretmesi (Kaynak atıfı uydurma tespiti ve inconclusive durumu)
5. Verification başarısızlığı ve sonuçsuz kalması (passed / failed / inconclusive durum sözleşmeleri)
6. Bozuk veya şema dışı LLM çıktısı (Graceful error handling, 500 dönülür, DB FAILED işaretlenir)
7. LLM provider timeout veya hatası (Timeout/bağlantı hatası güvenle yakalanır)
8. Eksik alanlar ve farklı para birimleri (Currency mismatch 400 ile durdurulur)
9. Stale analysis (Analiz sonrası teklif/RFQ güncellemesi bayatlama yaratır ve onay engellenir)
10. Cross-tenant erişim girişimi (Başka organizasyonun RFQ'su analiz edilemez / incelenemez)
11. Önceki aşama başarısızken sonraki aşamanın engellenmesi (1 teklif varken TCO/RAG/LLM çalışmaz)
12. Verification başarısızken onay veya PO oluşturulamaması (failed analize standart approval 400 verir)
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.supplier import Supplier, SupplierHistory
from app.models.rfq import RFQ, RFQItem, RFQStatus
from app.models.quote import Quote, QuoteItem
from app.models.analysis import Analysis, AnalysisStatus, Approval, ApprovalStatus, TCOResult, Recommendation, VerificationStatus
from app.models.order import PurchaseOrder
from app.models.user import User, UserRole
from app.models.audit import AuditEvent
from app.core.security import hash_password, create_access_token
from app.services.agent.schemas import AgentRecommendationSchema
from app.services.agent.service import AgentService
from app.services.agent.verification import VerificationService
from app.schemas.orchestration import (
    StageName,
    StageStatus,
    VerificationOutcome,
    StageResultResponse,
)


async def create_org_and_suppliers(session):
    unique_suffix = uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Phase10 Org {unique_suffix}",
        slug=f"phase10-org-{unique_suffix}"
    )
    session.add(org)
    await session.flush()

    sup1 = Supplier(name=f"Tedarikci A {unique_suffix}", organization_id=org.id)
    sup2 = Supplier(name=f"Tedarikci B {unique_suffix}", organization_id=org.id)
    session.add_all([sup1, sup2])

    user = User(
        organization_id=org.id,
        email=f"manager_{unique_suffix}@phase10.com",
        full_name="Phase 10 Manager",
        hashed_password=hash_password("Passw0rd123!"),
        role=UserRole.MANAGER.value,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(org)
    await session.refresh(sup1)
    await session.refresh(sup2)
    await session.refresh(user)

    token = create_access_token({"sub": str(user.id), "org_id": str(org.id), "role": "manager"})
    org.headers = {"Authorization": f"Bearer {token}"}
    return org, sup1, sup2, user


def make_agent_output(recommended_quote_id: uuid.UUID | None = None, justification: str = "Tüm kurallara uygun en iyi teklif."):
    return AgentRecommendationSchema(
        recommended_quote_id=recommended_quote_id,
        justification=justification,
        trade_off_analysis="Alternatifler kıyaslandığında maliyet ve teslimat dengesi sağlanmıştır.",
        risk_factors=["Tedarikçi teslimat geçmişi izlenmelidir."],
        confidence_score=95,
        is_human_review_required=False,
    )


# ── 1. Başarılı Uçtan Uca Analiz ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_stage_pipeline_e2e_successful_analysis():
    """Tüm 5 aşamanın başarıyla tamamlanması, aşama sözleşmelerinin ve sürelerin dönmesi."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(
            organization_id=org.id,
            title="E2E Pipeline Test RFQ",
            budget=Decimal("100000.00"),
            max_delivery_days=15,
            min_warranty_months=12,
            payment_terms="net-30",
        )
        session.add(rfq)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            subtotal=Decimal("45000.00"), total_price=Decimal("45000.00"),
            currency="TRY",
            delivery_days=10,
            warranty_months=24,
            payment_terms="net-30",
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            subtotal=Decimal("50000.00"), total_price=Decimal("50000.00"),
            currency="TRY",
            delivery_days=12,
            warranty_months=12,
            payment_terms="net-30",
        )
        session.add_all([q1, q2])
        await session.commit()
        await session.refresh(q1)

        mock_output = make_agent_output(q1.id, "Tedarikci A en düşük maliyet ve 24 ay garanti sunuyor.")

        with patch.object(AgentService, "generate_recommendation", new_callable=AsyncMock) as mock_agent:
            async def fake_gen(analysis_id, organization_id):
                rec = Recommendation(
                    analysis_id=analysis_id,
                    recommended_quote_id=q1.id,
                    reasoning=mock_output.justification,
                    risks="[]",
                    verification_status=VerificationStatus.PENDING.value,
                )
                session.add(rec)
                await session.commit()
                await session.refresh(rec)
                return rec
            mock_agent.side_effect = fake_gen

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/rfqs/{rfq.id}/analyze",
                    json={"rules": {}},
                    headers=org.headers,
                )

        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "completed"
        assert len(data["tco_results"]) == 2
        assert len(data["compliance_checks"]) > 0
        assert data["recommendation"]["verification_status"] == "verified"
        assert data["recommendation"]["recommended_quote_id"] == str(q1.id)

        # Phase 10: 5 Aşama kontrolü
        stage_results = data.get("stage_results", [])
        assert len(stage_results) == 5
        stage_names = [s["stage"] for s in stage_results]
        assert "extraction_validation" in stage_names
        assert "deterministic_evaluation" in stage_names
        assert "policy_compliance" in stage_names
        assert "supplier_recommendation" in stage_names
        assert "independent_verification" in stage_names

        for s in stage_results:
            assert s["status"] in ["completed", "inconclusive"]
            assert s["duration_ms"] >= 0.0


# ── 2. Hard-Rule İhlali ve Overridden ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_stage_hard_rule_violation_and_elimination():
    """Deterministik kuralı ihlal eden bir teklif LLM tarafından önerilse bile bağımsız doğrulama override eder."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Hard Rule Violation Test",
            budget=Decimal("50000.00"),
            max_delivery_days=10,
            min_warranty_months=24, # 24 ay kuralı
        )
        session.add(rfq)
        await session.flush()

        # q1 kurallara uygun
        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            subtotal=Decimal("40000.00"), total_price=Decimal("40000.00"),
            currency="TRY",
            delivery_days=7,
            warranty_months=24,
            payment_terms="net-30",
        )
        # q2 kural ihlali: 12 ay garanti (24 ay gerekli)
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            subtotal=Decimal("30000.00"), total_price=Decimal("30000.00"),
            currency="TRY",
            delivery_days=5,
            warranty_months=12,
            payment_terms="net-30",
        )
        session.add_all([q1, q2])
        await session.commit()
        await session.refresh(q1)
        await session.refresh(q2)

        # LLM hatalı şekilde elenen q2'yi öneriyor
        with patch.object(AgentService, "generate_recommendation", new_callable=AsyncMock) as mock_agent:
            async def fake_gen(analysis_id, organization_id):
                rec = Recommendation(
                    analysis_id=analysis_id,
                    recommended_quote_id=q2.id,
                    reasoning="Tedarikci B daha ucuz olduğu için önerildi.",
                    risks="[]",
                    verification_status=VerificationStatus.PENDING.value,
                )
                session.add(rec)
                await session.commit()
                await session.refresh(rec)
                return rec
            mock_agent.side_effect = fake_gen

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/rfqs/{rfq.id}/analyze",
                    json={"rules": {}},
                    headers=org.headers,
                )

        assert res.status_code == 200
        data = res.json()
        # Bağımsız doğrulama elenen teklifi override etti
        assert data["recommendation"]["verification_status"] == "overridden"
        assert data["recommendation"]["recommended_quote_id"] is None
        assert "SİSTEM UYARISI" in data["recommendation"]["verification_notes"]
        assert "KURAL İHLALİ" in data["recommendation"]["verification_notes"]


# ── 3. Yetersiz RAG Kanıtı (insufficient_evidence) ────────────────────────────
@pytest.mark.asyncio
async def test_stage_policy_compliance_insufficient_evidence():
    """Kurumsal politikada eşleşme bulunamadığında insufficient_evidence bayrağı üretilir."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Exotic Hardware Without Policy",
            budget=Decimal("500000.00"),
        )
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, subtotal=Decimal("100000.00"), total_price=Decimal("100000.00"), currency="TRY")
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, subtotal=Decimal("120000.00"), total_price=Decimal("120000.00"), currency="TRY")
        session.add_all([q1, q2])
        await session.commit()

        from app.services.orchestration.stages import PolicyComplianceStage
        stage_res, output, rag_context, evidence_refs = await PolicyComplianceStage.execute(
            organization_id=str(org.id),
            rfq=rfq,
            quotes=[q1, q2],
        )

        assert output.rag_status == "insufficient_evidence"
        assert output.is_sufficient_evidence is False
        assert output.evidence_count == 0
        assert "politika belgelerinde" in rag_context.lower()
        assert stage_res.status == StageStatus.INCONCLUSIVE


# ── 4. Desteklenmeyen İddia Üretimi (Unsupported Claims) ──────────────────────
@pytest.mark.asyncio
async def test_stage_unsupported_claims_detection():
    """LLM uydurma kaynak veya desteksiz iddia ürettiğinde doğrulama bunu yakalar."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Server RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, subtotal=Decimal("20000.00"), total_price=Decimal("20000.00"), currency="TRY")
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, subtotal=Decimal("25000.00"), total_price=Decimal("25000.00"), currency="TRY")
        session.add_all([q1, q2])
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.RUNNING.value)
        session.add(analysis)
        await session.flush()

        tco1 = TCOResult(analysis_id=analysis.id, quote_id=q1.id, subtotal=Decimal("20000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("20000.00"), currency="TRY")
        tco2 = TCOResult(analysis_id=analysis.id, quote_id=q2.id, subtotal=Decimal("25000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("25000.00"), currency="TRY")

        # LLM hafızada olmayan bir kaynak uyduruyor: [Kaynak 99: Hayali Sozlesme]
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=q1.id,
            reasoning="Tedarikçi şartları sağladı [Kaynak 99: Hayali Sozlesme Maddesi].",
            verification_status=VerificationStatus.PENDING.value,
        )
        session.add_all([tco1, tco2, rec])
        await session.commit()

        verif_service = VerificationService(db=session)
        # Bilinen kaynaklar arasında 'Hayali Sozlesme' yok
        verified_rec = await verif_service.verify_recommendation(
            recommendation_id=rec.id,
            known_sources=["Kaynak 1: Satın Alma Prosedürü Madde 4"]
        )

        assert verified_rec.verification_status == VerificationStatus.INCONCLUSIVE.value
        assert "desteklenmeyen atıflar" in verified_rec.verification_notes.lower()


# ── 5. Verification Durum Sözleşmeleri (passed / failed / inconclusive) ────────
@pytest.mark.asyncio
async def test_stage_verification_failure_and_inconclusive_contracts():
    """Doğrulama sonuçlarının açık ve ayrık durum sözleşmelerine sahip olması."""
    assert VerificationOutcome.PASSED.value == "passed"
    assert VerificationOutcome.FAILED.value == "failed"
    assert VerificationOutcome.INCONCLUSIVE.value == "inconclusive"
    assert VerificationStatus.PASSED.value == "passed"
    assert VerificationStatus.INCONCLUSIVE.value == "inconclusive"


# ── 6. Bozuk veya Şema Dışı LLM Çıktısı ────────────────────────────────────────
@pytest.mark.asyncio
async def test_stage_malformed_or_invalid_schema_llm_output():
    """LLM şemaya uymayan bozuk JSON döndürdüğünde analiz güvenle FAILED yapılır ve 500 dönülür."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Schema Test RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, subtotal=Decimal("10000.00"), total_price=Decimal("10000.00"), currency="TRY")
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, subtotal=Decimal("12000.00"), total_price=Decimal("12000.00"), currency="TRY")
        session.add_all([q1, q2])
        await session.commit()

        # LLM bozuk çıktı üretiyor
        with patch.object(AgentService, "generate_recommendation", new_callable=AsyncMock) as mock_agent:
            mock_agent.side_effect = ValueError("Schema validation failed: Missing required field 'trade_off_analysis'")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/rfqs/{rfq.id}/analyze",
                    json={"rules": {}},
                    headers=org.headers,
                )

        assert res.status_code == 500
        assert "Agent analysis failed" in res.json()["detail"]

        # Veritabanında analizin FAILED olarak işaretlendiğini doğrula
        analysis_res = await session.execute(
            select(Analysis).where(Analysis.rfq_id == rfq.id).order_by(Analysis.created_at.desc())
        )
        saved_analysis = analysis_res.scalars().first()
        assert saved_analysis.status == AnalysisStatus.FAILED.value


# ── 7. LLM Provider Timeout ve Hatası ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_stage_llm_provider_timeout_or_error():
    """LLM API çağrısında TimeoutError oluştuğunda sistem çökmeksizin 500 döner."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Timeout Test RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, subtotal=Decimal("10000.00"), total_price=Decimal("10000.00"), currency="TRY")
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, subtotal=Decimal("12000.00"), total_price=Decimal("12000.00"), currency="TRY")
        session.add_all([q1, q2])
        await session.commit()

        with patch.object(AgentService, "generate_recommendation", new_callable=AsyncMock) as mock_agent:
            mock_agent.side_effect = TimeoutError("Gemini API request timed out after 45 seconds.")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/rfqs/{rfq.id}/analyze",
                    json={"rules": {}},
                    headers=org.headers,
                )

        assert res.status_code == 500
        assert "timed out" in res.json()["detail"]


# ── 8. Eksik Alanlar ve Farklı Para Birimleri ──────────────────────────────────
@pytest.mark.asyncio
async def test_stage_missing_fields_and_currency_mismatch():
    """Farklı para birimlerindeki teklifler Stage 1'de doğrudan 400 ile engellenir."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Currency Mismatch RFQ")
        session.add(rfq)
        await session.flush()

        # Biri TRY diğeri EUR
        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, subtotal=Decimal("50000.00"), total_price=Decimal("50000.00"), currency="TRY")
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, subtotal=Decimal("1500.00"), total_price=Decimal("1500.00"), currency="EUR")
        session.add_all([q1, q2])
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/v1/rfqs/{rfq.id}/analyze",
                json={"rules": {}},
                headers=org.headers,
            )

        assert res.status_code == 400
        assert "farklı para birimleri" in res.json()["detail"].lower()


# ── 9. Stale Analysis Kontrolü ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_stage_stale_analysis_blocking():
    """Analiz tamamlandıktan sonra teklif güncellenirse bayat (stale) kabul edilip onay engellenir."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Stale RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, subtotal=Decimal("20000.00"), total_price=Decimal("20000.00"), currency="TRY", is_compliant=True)
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, subtotal=Decimal("25000.00"), total_price=Decimal("25000.00"), currency="TRY", is_compliant=True)
        session.add_all([q1, q2])
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        tco1 = TCOResult(analysis_id=analysis.id, quote_id=q1.id, subtotal=Decimal("20000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("20000.00"), currency="TRY")
        tco2 = TCOResult(analysis_id=analysis.id, quote_id=q2.id, subtotal=Decimal("25000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("25000.00"), currency="TRY")
        rec = Recommendation(analysis_id=analysis.id, recommended_quote_id=q1.id, reasoning="En uygun teklif", verification_status=VerificationStatus.VERIFIED.value)
        session.add_all([tco1, tco2, rec])
        await session.commit()

        # Teklif fiyatını ve updated_at zaman damgasını analizden sonraya güncelle
        from datetime import datetime, timedelta, timezone
        q1.total_price = Decimal("22000.00")
        q1.updated_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={"status": "approved"},
                headers=org.headers,
            )

        assert res.status_code == 400
        assert "stale" in res.json()["detail"].lower()


# ── 10. Cross-Tenant Erişim İzolasyonu ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_stage_cross_tenant_access_isolation():
    """Farklı organizasyondaki kullanıcının analizi çalıştırması veya onaylaması 404 ile engellenir."""
    async with AsyncSessionLocal() as session:
        org_a, sup1, sup2, user_a = await create_org_and_suppliers(session)
        org_b, _, _, user_b = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org_a.id, title="Org A RFQ")
        session.add(rfq)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Org B, Org A'nın RFQ'sunu analiz etmeye çalışıyor
            res = await client.post(
                f"/api/v1/rfqs/{rfq.id}/analyze",
                json={"rules": {}},
                headers=org_b.headers,
            )

        assert res.status_code == 404
        assert "bulunamadı" in res.json()["detail"].lower()


# ── 11. Önceki Aşama Başarısızken Sonraki Aşamanın Engellenmesi ────────────────
@pytest.mark.asyncio
async def test_stage_failure_prevents_subsequent_stages():
    """En az 2 teklif kuralı sağlanmadığında Stage 1 başarısız olur ve LLM/RAG asla çağrılmaz."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="Single Quote RFQ")
        session.add(rfq)
        await session.flush()

        # Yalnızca 1 teklif var
        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, subtotal=Decimal("10000.00"), total_price=Decimal("10000.00"), currency="TRY")
        session.add(q1)
        await session.commit()

        with patch.object(AgentService, "generate_recommendation", new_callable=AsyncMock) as mock_agent:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/rfqs/{rfq.id}/analyze",
                    json={"rules": {}},
                    headers=org.headers,
                )

            assert res.status_code == 400
            assert "en az 2 teklif" in res.json()["detail"].lower()
            # LLM ajanının asla tetiklenmediğini garanti et
            mock_agent.assert_not_called()


# ── 12. Verification Başarısızken Onay / PO Oluşturulamaması ───────────────────
@pytest.mark.asyncio
async def test_stage_verification_failure_blocks_po_and_approval():
    """Verification durumu failed / overridden olan bir analize standart 'approved' verilmesi 400 ile engellenir ve PO üretilmez."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        rfq = RFQ(organization_id=org.id, title="PO Block Test RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, subtotal=Decimal("30000.00"), total_price=Decimal("30000.00"), currency="TRY", is_compliant=False)
        q2 = Quote(rfq_id=rfq.id, supplier_id=sup2.id, subtotal=Decimal("35000.00"), total_price=Decimal("35000.00"), currency="TRY", is_compliant=True)
        session.add_all([q1, q2])
        await session.flush()

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis)
        await session.flush()

        tco1 = TCOResult(analysis_id=analysis.id, quote_id=q1.id, subtotal=Decimal("30000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("30000.00"), currency="TRY")
        tco2 = TCOResult(analysis_id=analysis.id, quote_id=q2.id, subtotal=Decimal("35000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("35000.00"), currency="TRY")

        # Verification failed olarak işaretlenmiş analiz
        rec = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=None,
            reasoning="Kural ihlali nedeniyle reddedildi.",
            verification_status=VerificationStatus.OVERRIDDEN.value,
            verification_notes="KURAL İHLALİ: Garanti süresi yetersiz."
        )
        session.add_all([tco1, tco2, rec])
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Standart onay denemesi (Reddedilmeli)
            res = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={"status": "approved"},
                headers=org.headers,
            )
            assert res.status_code == 400
            assert "doğrulama aşamasından geçemeyen" in res.json()["detail"].lower()

            # Bu RFQ için hiçbir PO oluşturulmadığını doğrula
            po_count = await session.execute(
                select(func.count(PurchaseOrder.id)).join(Quote).where(Quote.rfq_id == rfq.id)
            )
            assert po_count.scalar() == 0

            # 2. Yetkili yönetici istisna onayı (exception_approved + acknowledged_policy_violation)
            res_exc = await client.post(
                f"/api/v1/analyses/{analysis.id}/review",
                json={
                    "status": "exception_approved",
                    "selected_quote_id": str(q2.id),
                    "acknowledged_policy_violation": True,
                    "comment": "Yönetici inisiyatifi ile alternatif uygun teklif onaylandı."
                },
                headers=org.headers,
            )
            assert res_exc.status_code == 201
            assert res_exc.json()["status"] == "exception_approved"

            # Şimdi PO üretilmiş olmalı
            po_res = await session.execute(
                select(PurchaseOrder).where(PurchaseOrder.quote_id == q2.id)
            )
            created_po = po_res.scalar_one_or_none()
            assert created_po is not None
            assert created_po.status == "issued"


# ── 13. Tüm Doğrulama Durumları Onay Matrisi (passed, failed, overridden, inconclusive) ──
@pytest.mark.asyncio
async def test_stage_verification_all_status_approval_matrix():
    """passed, failed, overridden ve inconclusive durumlarının tüm onay kombinasyonlarını doğrular."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        # 1. TEST CASE A: INCONCLUSIVE (Yetersiz kanıt / desteksiz atıf)
        rfq_a = RFQ(organization_id=org.id, title="Inconclusive Status Test RFQ")
        session.add(rfq_a)
        await session.flush()

        qa1 = Quote(rfq_id=rfq_a.id, supplier_id=sup1.id, subtotal=Decimal("40000.00"), total_price=Decimal("40000.00"), currency="TRY", is_compliant=True)
        qa2 = Quote(rfq_id=rfq_a.id, supplier_id=sup2.id, subtotal=Decimal("42000.00"), total_price=Decimal("42000.00"), currency="TRY", is_compliant=True)
        session.add_all([qa1, qa2])
        await session.flush()

        analysis_a = Analysis(rfq_id=rfq_a.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis_a)
        await session.flush()

        tco_a1 = TCOResult(analysis_id=analysis_a.id, quote_id=qa1.id, subtotal=Decimal("40000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("40000.00"), currency="TRY")
        tco_a2 = TCOResult(analysis_id=analysis_a.id, quote_id=qa2.id, subtotal=Decimal("42000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("42000.00"), currency="TRY")

        rec_a = Recommendation(
            analysis_id=analysis_a.id,
            recommended_quote_id=qa1.id,
            reasoning="Tedarikçi A önerildi [Kaynak 99: Bilinmeyen Sozlesme].",
            verification_status=VerificationStatus.INCONCLUSIVE.value,
            verification_notes="UYARI: Desteklenmeyen atıf tespit edildi."
        )
        session.add_all([tco_a1, tco_a2, rec_a])
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Inconclusive için standart approved denenir -> 400 ile ENGELLENMELİ
            res_std = await client.post(
                f"/api/v1/analyses/{analysis_a.id}/review",
                json={"status": "approved"},
                headers=org.headers,
            )
            assert res_std.status_code == 400
            assert "sonuçsuz kalan (inconclusive)" in res_std.json()["detail"].lower()

            # Hiçbir PO oluşturulmadığını doğrula
            po_count = await session.execute(
                select(func.count(PurchaseOrder.id)).join(Quote).where(Quote.rfq_id == rfq_a.id)
            )
            assert po_count.scalar() == 0

            # Inconclusive için yetkili yönetici exception_approved verir -> 201 BAŞARILI OLMALI
            res_exc = await client.post(
                f"/api/v1/analyses/{analysis_a.id}/review",
                json={
                    "status": "exception_approved",
                    "acknowledged_policy_violation": True,
                    "comment": "Kanıt yetersizliği biliniyor, inisiyatif ile onaylandı."
                },
                headers=org.headers,
            )
            assert res_exc.status_code == 201
            assert res_exc.json()["status"] == "exception_approved"

            # Şimdi PO oluşturulmuş olmalı
            po_a = await session.execute(
                select(PurchaseOrder).where(PurchaseOrder.quote_id == qa1.id)
            )
            assert po_a.scalar_one_or_none() is not None

        # 2. TEST CASE B: PASSED (Tüm kontroller temiz)
        rfq_b = RFQ(organization_id=org.id, title="Passed Status Test RFQ")
        session.add(rfq_b)
        await session.flush()

        qb1 = Quote(rfq_id=rfq_b.id, supplier_id=sup1.id, subtotal=Decimal("15000.00"), total_price=Decimal("15000.00"), currency="TRY", is_compliant=True)
        qb2 = Quote(rfq_id=rfq_b.id, supplier_id=sup2.id, subtotal=Decimal("18000.00"), total_price=Decimal("18000.00"), currency="TRY", is_compliant=True)
        session.add_all([qb1, qb2])
        await session.flush()

        analysis_b = Analysis(rfq_id=rfq_b.id, status=AnalysisStatus.COMPLETED.value)
        session.add(analysis_b)
        await session.flush()

        tco_b1 = TCOResult(analysis_id=analysis_b.id, quote_id=qb1.id, subtotal=Decimal("15000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("15000.00"), currency="TRY")
        tco_b2 = TCOResult(analysis_id=analysis_b.id, quote_id=qb2.id, subtotal=Decimal("18000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("18000.00"), currency="TRY")

        rec_b = Recommendation(
            analysis_id=analysis_b.id,
            recommended_quote_id=qb1.id,
            reasoning="Tedarikçi B1 en düşük maliyeti sağladı.",
            verification_status=VerificationStatus.PASSED.value,
            verification_notes="DOĞRULAMA GEÇTİ: Tüm kontroller sağlandı."
        )
        session.add_all([tco_b1, tco_b2, rec_b])
        await session.commit()

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Passed için standart approved doğrudan 201 BAŞARILI OLMALI
            res_pass = await client.post(
                f"/api/v1/analyses/{analysis_b.id}/review",
                json={"status": "approved", "comment": "Tüm kurallar uyumlu."},
                headers=org.headers,
            )
            assert res_pass.status_code == 201
            assert res_pass.json()["status"] == "approved"

            # PO doğrudan düzenlenmiş olmalı
            po_b = await session.execute(
                select(PurchaseOrder).where(PurchaseOrder.quote_id == qb1.id)
            )
            assert po_b.scalar_one_or_none() is not None


# ── 14. TCO & Belge Kayıt Kimliği Doğrulama Denetimi ────────────────────────────
@pytest.mark.asyncio
async def test_stage_verification_tco_and_record_scoping():
    """TCO kaydının mutlaka mevcut analize ait olması ve aktif politika belgeleriyle eşleşmesi kontrol edilir."""
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user = await create_org_and_suppliers(session)

        # Aktif bir politika belgesi ekle
        from app.models.policy_document import PolicyDocument
        policy_doc = PolicyDocument(
            organization_id=org.id,
            title="Kurumsal Tedarik Politikası 2026",
            file_name="tedarik_politikasi.pdf",
            file_path="/tmp/tedarik.pdf",
            is_active=True
        )
        session.add(policy_doc)

        rfq = RFQ(organization_id=org.id, title="Scoping RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(rfq_id=rfq.id, supplier_id=sup1.id, subtotal=Decimal("50000.00"), total_price=Decimal("50000.00"), currency="TRY")
        session.add(q1)
        await session.flush()

        # Analiz 1
        analysis_1 = Analysis(rfq_id=rfq.id, status=AnalysisStatus.RUNNING.value)
        # Analiz 2
        analysis_2 = Analysis(rfq_id=rfq.id, status=AnalysisStatus.RUNNING.value)
        session.add_all([analysis_1, analysis_2])
        await session.flush()

        # TCO hesabı Analiz 1'e yazıldı, Analiz 2'ye yazılmadı
        tco_1 = TCOResult(analysis_id=analysis_1.id, quote_id=q1.id, subtotal=Decimal("50000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0), total_tco=Decimal("50000.00"), currency="TRY")
        session.add(tco_1)

        # Analiz 2 için öneri: TCO analize ait değil
        rec_2 = Recommendation(
            analysis_id=analysis_2.id,
            recommended_quote_id=q1.id,
            reasoning="Tedarikçi şartları sağladı [Kaynak 1: Kurumsal Tedarik Politikası 2026].",
            verification_status=VerificationStatus.PENDING.value,
        )
        session.add(rec_2)
        await session.commit()

        # Doğrulama servisi Analiz 2'yi doğrulamaya çalışır (TCO hesabı Analiz 2'de yok!)
        verif_service = VerificationService(db=session)
        verified_rec = await verif_service.verify_recommendation(recommendation_id=rec_2.id)

        # TCO başka analize ait olduğu için kural ihlali / override olmalı
        assert verified_rec.verification_status == VerificationStatus.OVERRIDDEN.value
        assert "tco uyumsuzluğu" in verified_rec.verification_notes.lower()
        assert verified_rec.recommended_quote_id is None
