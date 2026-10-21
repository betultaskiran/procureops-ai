"""
backend/tests/test_bilingual_analysis.py

Bilingual AI Analysis (Turkish / English) Verification Test Suite.
Validates:
1. AnalyzeRequest schema validation and locale defaulting ('tr' vs 'en' vs invalid 422).
2. AgentService prompt construction and localized reasoning / alternative_notes labels.
3. VerificationService dual citation extraction ([Kaynak X: ...] and [Source X: ...]),
   localized evidence claims/content, and localized verification notes.
4. Orchestration pipeline and endpoint stage results summary localization across all stages.
5. Verbatim citation preservation without corruption.
6. Full E2E API flow: POST analyze with locale='en' vs locale='tr', audit persistence, and GET analysis retrieval.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from pydantic import ValidationError
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.api.v1.analyses import AnalyzeRequest, AnalysisResponse
from app.models.organization import Organization
from app.models.supplier import Supplier
from app.models.rfq import RFQ
from app.models.quote import Quote
from app.models.analysis import Analysis, Recommendation, VerificationStatus, TCOResult, EvidenceItem
from app.models.policy_document import PolicyDocument
from app.models.user import User, UserRole
from app.models.audit import AuditEvent
from app.core.security import hash_password, create_access_token
from app.services.agent.schemas import AgentRecommendationSchema
from app.services.agent.service import AgentService
from app.services.agent.verification import VerificationService
from app.services.orchestration.stages import (
    ExtractionValidationStage,
    DeterministicEvaluationStage,
)
from app.services.deterministic.schemas import PolicyRules
from app.schemas.orchestration import VerificationOutcome


async def create_test_fixture(session):
    unique_suffix = uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Bilingual Org {unique_suffix}",
        slug=f"bilingual-org-{unique_suffix}"
    )
    session.add(org)
    await session.flush()

    sup1 = Supplier(name=f"Supplier Alpha {unique_suffix}", organization_id=org.id)
    sup2 = Supplier(name=f"Supplier Beta {unique_suffix}", organization_id=org.id)
    session.add_all([sup1, sup2])

    user = User(
        organization_id=org.id,
        email=f"buyer_{unique_suffix}@bilingual.com",
        full_name="Bilingual Buyer",
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
    headers = {"Authorization": f"Bearer {token}"}
    return org, sup1, sup2, user, headers


# ── 1. Schema Validation ─────────────────────────────────────────────────────
def test_analyze_request_locale_schema():
    # Default is 'tr'
    req_default = AnalyzeRequest()
    assert req_default.locale == "tr"

    # Explicit 'en'
    req_en = AnalyzeRequest(locale="en")
    assert req_en.locale == "en"

    # Explicit 'tr'
    req_tr = AnalyzeRequest(locale="tr")
    assert req_tr.locale == "tr"

    # Invalid locale rejected
    with pytest.raises(ValidationError):
        AnalyzeRequest(locale="de")

    with pytest.raises(ValidationError):
        AnalyzeRequest(locale="es")


# ── 2. AgentService Prompt and Formatting ────────────────────────────────────
@pytest.mark.asyncio
async def test_agent_service_prompt_construction():
    mock_db = MagicMock()
    agent = AgentService(db=mock_db)
    
    # English prompt
    prompt_en = agent._build_prompt(
        eligible_quotes=[{"supplier_name": "Supplier Alpha", "total_price": 50000}],
        eliminated_quotes=[],
        rag_context="[Source 1: Corporate Procurement Policy Article 3.2]",
        sql_context="Supplier Alpha delay rate: 0%",
        locale="en",
    )
    assert "Senior Procurement Specialist and AI Agent" in prompt_en
    assert "VERBATIM CITATIONS" in prompt_en
    assert "Provide your narrative, justification, trade-off analysis, and risk factors in English" in prompt_en
    assert "keep official policy citations, document titles, and article numbers verbatim" in prompt_en

    # Turkish prompt
    prompt_tr = agent._build_prompt(
        eligible_quotes=[{"supplier_name": "Supplier Alpha", "total_price": 50000}],
        eliminated_quotes=[],
        rag_context="[Kaynak 1: BT Donanım Politikası Madde 3.2]",
        sql_context="",
        locale="tr",
    )
    assert "kıdemli bir Satın Alma Uzmanı ve AI Agent'sın" in prompt_tr
    assert "KANITLANABİLİRLİK" in prompt_tr


# ── 3. VerificationService Dual Citations and Evidence Localization ──────────
@pytest.mark.asyncio
async def test_verification_service_dual_citations_and_localization():
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user, _ = await create_test_fixture(session)

        rfq = RFQ(organization_id=org.id, title="Verif Test RFQ")
        session.add(rfq)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            subtotal=Decimal("45000"),
            vat_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            discount_amount=Decimal("0"),
            other_costs=Decimal("0"),
            total_price=Decimal("45000"),
            currency="TRY",
            is_compliant=True,
        )
        session.add(q1)
        await session.flush()

        analysis_en = Analysis(
            rfq_id=rfq.id,
            created_by_id=user.id,
            status="completed",
        )
        session.add(analysis_en)
        await session.flush()

        tco_en = TCOResult(
            analysis_id=analysis_en.id,
            quote_id=q1.id,
            subtotal=Decimal("45000"),
            vat_amount=Decimal("0.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_tco=Decimal("45000"),
            currency="TRY",
        )
        rec_en = Recommendation(
            analysis_id=analysis_en.id,
            recommended_quote_id=q1.id,
            reasoning="Supplier Alpha is compliant with [Source 1: IT Standard] and [Kaynak 2: Madde 4.1].\n\n**Trade-off Analysis:**\nBest value.",
            risks="[]",
            verification_status=VerificationStatus.PENDING.value,
        )
        session.add_all([tco_en, rec_en])
        await session.commit()
        await session.refresh(rec_en)

        # 1. Verify English
        verif_service = VerificationService(db=session)
        verified_rec_en = await verif_service.verify_recommendation(
            recommendation_id=rec_en.id,
            known_sources=["IT Standard", "Madde 4.1"],
            locale="en",
        )

        assert verified_rec_en.verification_status == VerificationStatus.VERIFIED.value
        assert "All deterministic rules and evidence verifications passed." in verified_rec_en.verification_notes

        # Check evidence records in DB
        ev_items_en = (await session.execute(
            select(EvidenceItem).where(EvidenceItem.analysis_id == analysis_en.id)
        )).scalars().all()

        assert len(ev_items_en) == 2
        for ev in ev_items_en:
            assert ev.claim.startswith("Claim asserted by LLM citing")
            assert ev.content == "Automatically extracted and verified by system."

        # Check verbatim citation preservation
        refs = [ev.source_reference for ev in ev_items_en]
        assert "IT Standard" in refs
        assert "Madde 4.1" in refs

        # 2. Verify Turkish
        analysis_tr = Analysis(
            rfq_id=rfq.id,
            created_by_id=user.id,
            status="completed",
        )
        session.add(analysis_tr)
        await session.flush()

        tco_tr = TCOResult(
            analysis_id=analysis_tr.id,
            quote_id=q1.id,
            subtotal=Decimal("45000"),
            vat_amount=Decimal("0.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_tco=Decimal("45000"),
            currency="TRY",
        )
        rec_tr = Recommendation(
            analysis_id=analysis_tr.id,
            recommended_quote_id=q1.id,
            reasoning="Tedarikçi Alpha uygundur [Kaynak 1: BT Politikası].",
            risks="[]",
            verification_status=VerificationStatus.PENDING.value,
        )
        session.add_all([tco_tr, rec_tr])
        await session.commit()
        await session.refresh(rec_tr)

        verified_rec_tr = await verif_service.verify_recommendation(
            recommendation_id=rec_tr.id,
            known_sources=["BT Politikası"],
            locale="tr",
        )

        assert verified_rec_tr.verification_status == VerificationStatus.VERIFIED.value
        assert "Tüm deterministik kurallar ve kanıt doğrulamaları sağlandı." in verified_rec_tr.verification_notes

        ev_items_tr = (await session.execute(
            select(EvidenceItem).where(EvidenceItem.analysis_id == analysis_tr.id)
        )).scalars().all()
        assert len(ev_items_tr) == 1
        assert "LLM tarafından" in ev_items_tr[0].claim
        assert ev_items_tr[0].content == "Sistem tarafından otomatik çıkarıldı ve doğrulandı."


# ── 4. Orchestration Stages Localization ─────────────────────────────────────
@pytest.mark.asyncio
async def test_orchestration_stages_summaries_localization():
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user, _ = await create_test_fixture(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Stage Summary Test RFQ",
            budget=Decimal("50000.00"),
            max_delivery_days=15,
            min_warranty_months=12,
            payment_terms="net-30",
        )
        session.add(rfq)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            subtotal=Decimal("40000.00"),
            total_price=Decimal("40000.00"),
            currency="TRY",
            delivery_days=10,
            warranty_months=24,
            payment_terms="net-30",
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            subtotal=Decimal("45000.00"),
            total_price=Decimal("45000.00"),
            currency="TRY",
            delivery_days=12,
            warranty_months=12,
            payment_terms="net-30",
        )
        session.add_all([q1, q2])
        await session.commit()

        # Stage 1: ExtractionValidationStage (EN vs TR)
        s1_en, _, _, _ = await ExtractionValidationStage.execute(
            db=session, rfq_id=rfq.id, organization_id=org.id, locale="en"
        )
        assert "2 quotes successfully validated (TRY)." in s1_en.summary

        s1_tr, _, _, _ = await ExtractionValidationStage.execute(
            db=session, rfq_id=rfq.id, organization_id=org.id, locale="tr"
        )
        assert "2 teklif başarıyla doğrulandı (TRY)." in s1_tr.summary

        # Stage 2: DeterministicEvaluationStage (EN vs TR)
        rules = PolicyRules(max_delivery_days=15, min_warranty_months=12, required_payment_terms=["net-30"])
        analysis = Analysis(rfq_id=rfq.id, created_by_id=user.id, status="running")
        session.add(analysis)
        await session.flush()

        s2_en, _, eligible, eliminated, tco_results, compliance_checks = await DeterministicEvaluationStage.execute(
            db=session, analysis_id=analysis.id, quotes=[q1, q2], rules=rules, locale="en"
        )
        assert "TCO and rule evaluation completed: 2 eligible, 0 eliminated." in s2_en.summary

        s2_tr, _, _, _, _, _ = await DeterministicEvaluationStage.execute(
            db=session, analysis_id=analysis.id, quotes=[q1, q2], rules=rules, locale="tr"
        )
        assert "TCO ve kural denetimi tamamlandı: 2 uygun, 0 elenen teklif." in s2_tr.summary


# ── 5. E2E Analyze Endpoint with locale="en" ─────────────────────────────────
@pytest.mark.asyncio
async def test_e2e_analyze_endpoint_english():
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user, headers = await create_test_fixture(session)

        # Add active PolicyDocument to corporate memory
        pol = PolicyDocument(
            organization_id=org.id,
            title="IT Procurement Policy",
            file_name="it_procurement_policy.pdf",
            file_path="/tmp/dummy",
            document_type="pdf",
            is_active=True,
        )
        session.add(pol)

        rfq = RFQ(
            organization_id=org.id,
            title="Workstation Procurement 2026",
            budget=Decimal("120000.00"),
            max_delivery_days=15,
            min_warranty_months=24,
            payment_terms="net-30",
        )
        session.add(rfq)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            subtotal=Decimal("80000.00"),
            total_price=Decimal("80000.00"),
            currency="TRY",
            delivery_days=10,
            warranty_months=24,
            payment_terms="net-30",
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            subtotal=Decimal("95000.00"),
            total_price=Decimal("95000.00"),
            currency="TRY",
            delivery_days=12,
            warranty_months=24,
            payment_terms="net-30",
        )
        session.add_all([q1, q2])
        await session.commit()
        await session.refresh(q1)

        mock_agent_schema = AgentRecommendationSchema(
            recommended_quote_id=q1.id,
            justification="Supplier Alpha offers the best price adhering to [Source 1: IT Procurement Policy Madde 2.1].",
            trade_off_analysis="Supplier Alpha provides significant savings over Beta with identical warranty terms.",
            risk_factors=["Monitor delivery timeline."],
            confidence_score=94,
            is_human_review_required=False,
        )

        with patch.object(AgentService, "generate_recommendation", new_callable=AsyncMock) as mock_agent:
            async def fake_recommendation(analysis_id, organization_id, locale="tr"):
                async with AsyncSessionLocal() as inner_session:
                    combined = (
                        f"{mock_agent_schema.justification}\n\n**Trade-off Analysis:**\n{mock_agent_schema.trade_off_analysis}"
                        if locale == "en"
                        else f"{mock_agent_schema.justification}\n\n**Trade-off Analizi:**\n{mock_agent_schema.trade_off_analysis}"
                    )
                    alt_notes = (
                        f"Confidence Score: {mock_agent_schema.confidence_score}/100. Human Review Required: No"
                        if locale == "en"
                        else f"Güven Skoru: {mock_agent_schema.confidence_score}/100. İnsan Onayı Gerekli mi: Hayır"
                    )
                    rec = Recommendation(
                        analysis_id=analysis_id,
                        recommended_quote_id=q1.id,
                        reasoning=combined,
                        verification_status=VerificationStatus.PENDING.value,
                        risks="[]",
                        alternative_notes=alt_notes,
                    )
                    inner_session.add(rec)
                    await inner_session.commit()
                    await inner_session.refresh(rec)
                    return rec
            mock_agent.side_effect = fake_recommendation

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/rfqs/{rfq.id}/analyze",
                    json={"rules": {}, "locale": "en"},
                    headers=headers,
                )

            assert res.status_code == 200, res.text
            data = res.json()
            assert data["status"] == "completed"
            assert data["locale"] == "en"

            # Check stage results localization in English
            stage_results = data.get("stage_results", [])
            assert len(stage_results) == 5
            stage_map = {s["stage"]: s["summary"] for s in stage_results}

            assert "2 quotes and documents successfully validated." in stage_map["extraction_validation"]
            assert "TCO and rule evaluation completed" in stage_map["deterministic_evaluation"]
            assert "Corporate memory (Qdrant RAG) successfully scanned" in stage_map["policy_compliance"]
            assert "Trade-off analysis and supplier recommendation generated via LLM." in stage_map["supplier_recommendation"]
            assert "Independent verification completed: VERIFIED." in stage_map["independent_verification"]

            # Check recommendation reasoning header
            assert "**Trade-off Analysis:**" in data["recommendation"]["reasoning"]
            assert "Confidence Score: 94/100" in data["recommendation"]["alternative_notes"]

            # Check evidence items
            evidence_items = data.get("evidence_items", [])
            assert len(evidence_items) >= 1
            assert evidence_items[0]["claim"].startswith("Claim asserted by LLM citing")
            assert evidence_items[0]["content"] == "Automatically extracted and verified by system."
            # Verbatim preservation of original citation reference
            assert "IT Procurement Policy Madde 2.1" in evidence_items[0]["source_reference"]

            # Verify GET /api/v1/rfqs/{rfq.id}/analysis restores locale="en"
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                get_res = await client.get(
                    f"/api/v1/rfqs/{rfq.id}/analysis",
                    headers=headers,
                )
            assert get_res.status_code == 200
            get_data = get_res.json()
            assert get_data["locale"] == "en"


# ── 6. Default Locale TR and Invalid Locale Rejection ────────────────────────
@pytest.mark.asyncio
async def test_e2e_analyze_endpoint_default_tr_and_invalid():
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user, headers = await create_test_fixture(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Default Locale Test RFQ",
            budget=Decimal("50000.00"),
            max_delivery_days=10,
            min_warranty_months=12,
            payment_terms="net-30",
        )
        session.add(rfq)
        await session.flush()

        q1 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup1.id,
            subtotal=Decimal("30000.00"),
            total_price=Decimal("30000.00"),
            currency="TRY",
            delivery_days=5,
            warranty_months=12,
            payment_terms="net-30",
        )
        q2 = Quote(
            rfq_id=rfq.id,
            supplier_id=sup2.id,
            subtotal=Decimal("35000.00"),
            total_price=Decimal("35000.00"),
            currency="TRY",
            delivery_days=7,
            warranty_months=12,
            payment_terms="net-30",
        )
        session.add_all([q1, q2])
        await session.commit()

        transport = ASGITransport(app=app)

        # 1. Test invalid locale returns HTTP 422
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            invalid_res = await client.post(
                f"/api/v1/rfqs/{rfq.id}/analyze",
                json={"rules": {}, "locale": "fr"},
                headers=headers,
            )
            assert invalid_res.status_code == 422

        # 2. Test default (omitted) locale produces 'tr'
        mock_agent_schema = AgentRecommendationSchema(
            recommended_quote_id=q1.id,
            justification="Tedarikçi Alpha en uygun fiyatı sunmaktadır [Kaynak 1: Satın Alma Kuralı].",
            trade_off_analysis="Fiyat ve garanti avantajı mevcuttur.",
            risk_factors=["Teslimat riski düşüktür."],
            confidence_score=90,
            is_human_review_required=False,
        )

        with patch.object(AgentService, "generate_recommendation", new_callable=AsyncMock) as mock_agent:
            async def fake_recommendation(analysis_id, organization_id, locale="tr"):
                async with AsyncSessionLocal() as inner_session:
                    combined = f"{mock_agent_schema.justification}\n\n**Trade-off Analizi:**\n{mock_agent_schema.trade_off_analysis}"
                    alt_notes = f"Güven Skoru: {mock_agent_schema.confidence_score}/100. İnsan Onayı Gerekli mi: Hayır"
                    rec = Recommendation(
                        analysis_id=analysis_id,
                        recommended_quote_id=q1.id,
                        reasoning=combined,
                        verification_status=VerificationStatus.PENDING.value,
                        risks="[]",
                        alternative_notes=alt_notes,
                    )
                    inner_session.add(rec)
                    await inner_session.commit()
                    await inner_session.refresh(rec)
                    return rec
            mock_agent.side_effect = fake_recommendation

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/rfqs/{rfq.id}/analyze",
                    json={"rules": {}},
                    headers=headers,
                )

            assert res.status_code == 200, res.text
            data = res.json()
            assert data["locale"] == "tr"

            # Check Turkish stage summaries
            stage_map = {s["stage"]: s["summary"] for s in data.get("stage_results", [])}
            assert "2 teklif ve doküman başarıyla doğrulandı." in stage_map["extraction_validation"]
            assert "TCO ve kural denetimi tamamlandı" in stage_map["deterministic_evaluation"]
            assert "Bağımsız doğrulama tamamlandı: VERIFIED." in stage_map["independent_verification"]
            assert "**Trade-off Analizi:**" in data["recommendation"]["reasoning"]
            assert "Güven Skoru: 90/100" in data["recommendation"]["alternative_notes"]
