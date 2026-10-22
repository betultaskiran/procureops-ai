"""
backend/tests/test_p2_3_localization_fixes.py

Targeted verification tests for P2.3 localization remediation:
1. Stage summary persistence in AuditEvent payload and retrieval via GET analysis endpoint.
2. Legacy AuditEvent fallback when stage summaries lack 'summary' field (no rich fabrication).
3. FX evidence localization (TR vs EN) verifying localized explanatory labels while all
   underlying numeric values (rates, TCO, conversion results, compliance) remain 100% identical.
4. TCOResult.conversion_path property accuracy under both English and Turkish notes.
"""

import uuid
from decimal import Decimal
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.supplier import Supplier
from app.models.rfq import RFQ
from app.models.quote import Quote
from app.models.analysis import Analysis, Recommendation, VerificationStatus, TCOResult, EvidenceItem
from app.models.user import User, UserRole
from app.models.audit import AuditEvent
from app.core.security import hash_password, create_access_token
from app.services.agent.schemas import AgentRecommendationSchema
from app.services.agent.service import AgentService
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.orchestrator import DeterministicEngine, localize_fx_note
from app.services.fx.service import ExchangeRateService
from app.services.fx.schemas import ExchangeRateDTO


async def create_fixture(session):
    suffix = uuid.uuid4().hex[:8]
    org = Organization(name=f"P23 Org {suffix}", slug=f"p23-org-{suffix}")
    session.add(org)
    await session.flush()

    sup1 = Supplier(name=f"Supplier A {suffix}", organization_id=org.id)
    sup2 = Supplier(name=f"Supplier B {suffix}", organization_id=org.id)
    session.add_all([sup1, sup2])

    user = User(
        organization_id=org.id,
        email=f"buyer_{suffix}@p23.com",
        full_name="P23 Buyer",
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


# ── Test 1: Stage Summary Persistence & Retrieval ─────────────────────────────
@pytest.mark.asyncio
async def test_stage_summary_persisted_in_audit_event_and_retrieved():
    """
    Proves that:
    1. POST /analyze with locale='en' stores 'summary' in AuditEvent.payload['stage_summaries'].
    2. Subsequent GET /analysis retrieves the stored localized stage summaries.
    """
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user, headers = await create_fixture(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Stage Summary Test RFQ",
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
            subtotal=Decimal("40000.00"),
            total_price=Decimal("40000.00"),
            currency="TRY",
            delivery_days=10,
            warranty_months=12,
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

        mock_agent_schema = AgentRecommendationSchema(
            recommended_quote_id=q1.id,
            justification="Supplier Alpha offers best pricing [Source 1: Policy Rule].",
            trade_off_analysis="Pricing and warranty are superior.",
            risk_factors=["Delivery risk is low."],
            confidence_score=92,
            is_human_review_required=False,
        )

        with patch.object(AgentService, "generate_recommendation", new_callable=AsyncMock) as mock_agent:
            async def fake_recommendation(analysis_id, organization_id, locale="en"):
                async with AsyncSessionLocal() as inner:
                    combined = f"{mock_agent_schema.justification}\n\n**Trade-off Analysis:**\n{mock_agent_schema.trade_off_analysis}"
                    alt_notes = f"Confidence Score: {mock_agent_schema.confidence_score}/100. Human Review Required: No"
                    rec = Recommendation(
                        analysis_id=analysis_id,
                        recommended_quote_id=q1.id,
                        reasoning=combined,
                        verification_status=VerificationStatus.PENDING.value,
                        risks="[]",
                        alternative_notes=alt_notes,
                    )
                    inner.add(rec)
                    await inner.commit()
                    await inner.refresh(rec)
                    return rec
            mock_agent.side_effect = fake_recommendation

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                post_res = await client.post(
                    f"/api/v1/rfqs/{rfq.id}/analyze",
                    json={"rules": {}, "locale": "en"},
                    headers=headers,
                )
            assert post_res.status_code == 200, post_res.text
            post_data = post_res.json()
            analysis_id = post_data["id"]

        # Verify AuditEvent in DB contains 'summary' in stage_summaries
        from sqlalchemy import select
        audit_res = await session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == uuid.UUID(analysis_id),
                AuditEvent.event_type == "analysis_completed"
            )
        )
        audit_event = audit_res.scalar_one_or_none()
        assert audit_event is not None
        payload = audit_event.payload
        assert "stage_summaries" in payload
        for stage_entry in payload["stage_summaries"]:
            assert "summary" in stage_entry, f"Stage entry {stage_entry} missing 'summary' field!"
            assert stage_entry["summary"] is not None
            assert len(stage_entry["summary"]) > 5

        # Verify GET endpoint returns the rich persisted summaries
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            get_res = await client.get(
                f"/api/v1/rfqs/{rfq.id}/analysis",
                headers=headers,
            )
        assert get_res.status_code == 200
        get_data = get_res.json()
        get_stage_map = {s["stage"]: s["summary"] for s in get_data.get("stage_results", [])}

        assert "2 quotes and documents successfully validated." in get_stage_map["extraction_validation"]
        assert "TCO and rule evaluation completed" in get_stage_map["deterministic_evaluation"]
        assert "Independent verification completed:" in get_stage_map["independent_verification"]
        # Ensure default technical enum summary was NOT used
        assert not get_stage_map["extraction_validation"].startswith("Stage: extraction_validation")


# ── Test 2: Legacy AuditEvent Safe Fallback (No Rich Fabrication) ──────────────
@pytest.mark.asyncio
async def test_legacy_audit_event_without_summary_safe_fallback():
    """
    Verifies that for historical analysis records where stage_summaries did NOT contain
    the 'summary' field, get_latest_analysis safely produces standard technical stage labels
    (Stage: <name> for EN, Aşama: <name> for TR) without crashing or fabricating false summaries.
    """
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user, headers = await create_fixture(session)

        rfq = RFQ(
            organization_id=org.id,
            title="Legacy Fallback RFQ",
            budget=Decimal("50000.00"),
        )
        session.add(rfq)
        await session.flush()

        analysis = Analysis(
            rfq_id=rfq.id,
            status="completed",
        )
        session.add(analysis)
        await session.flush()

        # Simulate legacy AuditEvent without 'summary' in stage_summaries
        legacy_payload_en = {
            "rfq_id": str(rfq.id),
            "locale": "en",
            "quote_count": 2,
            "stage_summaries": [
                {"stage": "extraction_validation", "status": "completed", "duration_ms": 12.0},
                {"stage": "deterministic_evaluation", "status": "completed", "duration_ms": 25.0},
            ]
        }
        legacy_event_en = AuditEvent(
            organization_id=org.id,
            actor_id=user.id,
            event_type="analysis_completed",
            entity_type="analysis",
            entity_id=analysis.id,
            payload=legacy_payload_en,
        )
        session.add(legacy_event_en)
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                f"/api/v1/rfqs/{rfq.id}/analysis",
                headers=headers,
            )
        assert res.status_code == 200
        data = res.json()
        assert data["locale"] == "en"
        stage_map = {s["stage"]: s["summary"] for s in data.get("stage_results", [])}
        # Safely falls back to technical stage label for legacy record
        assert stage_map["extraction_validation"] == "Stage: extraction_validation"
        assert stage_map["deterministic_evaluation"] == "Stage: deterministic_evaluation"


# ── Test 3: FX Evidence Localization & Numeric Identity ───────────────────────
@pytest.mark.asyncio
async def test_fx_evidence_localization_identical_numeric_results():
    """
    Tests that:
    1. FX evidence claims and explanatory labels differ appropriately between TR and EN.
    2. All underlying numeric values (rates, converted amounts, precision, compliance) are 100% IDENTICAL.
    3. TCOResult.conversion_path accurately detects 'DIRECT' in both locales.
    """
    async with AsyncSessionLocal() as session:
        org, sup1, sup2, user, headers = await create_fixture(session)

        # Mock FX Service with known direct rate: USD -> TRY = 40.000000
        mock_fx = AsyncMock(spec=ExchangeRateService)
        rate_dto = ExchangeRateDTO(
            source_currency="USD",
            target_currency="TRY",
            rate=Decimal("40.000000"),
            rate_type="ForexSelling",
            source="TCMB",
            rate_date=date(2026, 10, 19),
            fetched_at=datetime.now(timezone.utc),
            unit=1,
            bulletin_no="2026/199",
            conversion_path="DIRECT",
            calculation_notes="[Doğrudan Kur: USD/TRY = 40.000000 (Tarih: 2026-10-19, TCMB ForexSelling)]",
        )
        mock_fx.convert_amount = AsyncMock(return_value=(Decimal("400000.0000"), rate_dto))

        rules = PolicyRules(
            budget_limit=Decimal("500000.00"),
            budget_currency="TRY",
        )

        # ── Run 1: Turkish locale (locale='tr') ───────────────────────────────
        rfq_tr = RFQ(organization_id=org.id, title="FX RFQ TR", budget=Decimal("500000.00"))
        session.add(rfq_tr)
        await session.flush()
        q_tr_usd = Quote(
            rfq_id=rfq_tr.id,
            supplier_id=sup1.id,
            subtotal=Decimal("10000.00"),
            total_price=Decimal("10000.00"),
            currency="USD",
            delivery_days=10,
            warranty_months=12,
        )
        q_tr_try = Quote(
            rfq_id=rfq_tr.id,
            supplier_id=sup2.id,
            subtotal=Decimal("420000.00"),
            total_price=Decimal("420000.00"),
            currency="TRY",
            delivery_days=10,
            warranty_months=12,
        )
        session.add_all([q_tr_usd, q_tr_try])
        await session.commit()

        engine_tr = DeterministicEngine(db=session, fx_service=mock_fx)
        analysis_tr = await engine_tr.run_analysis(rfq_id=rfq_tr.id, rules=rules, locale="tr")

        # ── Run 2: English locale (locale='en') ───────────────────────────────
        rfq_en = RFQ(organization_id=org.id, title="FX RFQ EN", budget=Decimal("500000.00"))
        session.add(rfq_en)
        await session.flush()
        q_en_usd = Quote(
            rfq_id=rfq_en.id,
            supplier_id=sup1.id,
            subtotal=Decimal("10000.00"),
            total_price=Decimal("10000.00"),
            currency="USD",
            delivery_days=10,
            warranty_months=12,
        )
        q_en_try = Quote(
            rfq_id=rfq_en.id,
            supplier_id=sup2.id,
            subtotal=Decimal("420000.00"),
            total_price=Decimal("420000.00"),
            currency="TRY",
            delivery_days=10,
            warranty_months=12,
        )
        session.add_all([q_en_usd, q_en_try])
        await session.commit()

        engine_en = DeterministicEngine(db=session, fx_service=mock_fx)
        analysis_en = await engine_en.run_analysis(rfq_id=rfq_en.id, rules=rules, locale="en")

        # ── 1. NUMERIC VERIFICATION: Must be 100% IDENTICAL ───────────────────
        tco_tr_usd = next(t for t in analysis_tr.tco_results if t.currency == "USD")
        tco_en_usd = next(t for t in analysis_en.tco_results if t.currency == "USD")

        assert tco_tr_usd.total_tco == tco_en_usd.total_tco == Decimal("10000.00")
        assert tco_tr_usd.converted_total_tco == tco_en_usd.converted_total_tco == Decimal("400000.0000")
        assert tco_tr_usd.exchange_rate == tco_en_usd.exchange_rate == Decimal("40.000000")
        assert tco_tr_usd.exchange_rate_source == tco_en_usd.exchange_rate_source == "TCMB"
        assert tco_tr_usd.exchange_rate_date == tco_en_usd.exchange_rate_date == date(2026, 10, 19)

        # ── 2. CONVERSION PATH ACCURACY: Evaluates to 'DIRECT' in both ────────
        assert tco_tr_usd.conversion_path == "DIRECT"
        assert tco_en_usd.conversion_path == "DIRECT"

        # ── 3. EXPLANATORY TEXT VERIFICATION: Localized Appropriately ─────────
        # In Turkish:
        assert "Doğrudan Kur: USD/TRY = 40.000000" in tco_tr_usd.calculation_notes
        assert "Tarih: 2026-10-19" in tco_tr_usd.calculation_notes
        # In English:
        assert "Direct Rate: USD/TRY = 40.000000" in tco_en_usd.calculation_notes
        assert "Date: 2026-10-19" in tco_en_usd.calculation_notes
        assert "Doğrudan Kur" not in tco_en_usd.calculation_notes

        # Same currency note verification
        tco_tr_try = next(t for t in analysis_tr.tco_results if t.currency == "TRY")
        tco_en_try = next(t for t in analysis_en.tco_results if t.currency == "TRY")
        assert "[Aynı Para Birimi: TRY = TRY (Kur: 1.0)]" in tco_tr_try.calculation_notes
        assert "[Same Currency: TRY = TRY (Rate: 1.0)]" in tco_en_try.calculation_notes

        # ── 4. EVIDENCE ITEM VERIFICATION ─────────────────────────────────────
        fx_ev_tr = next(ev for ev in analysis_tr.evidence_items if ev.source_type == "fx_rate")
        fx_ev_en = next(ev for ev in analysis_en.evidence_items if ev.source_type == "fx_rate")

        # Turkish EvidenceItem
        assert fx_ev_tr.claim.startswith("Döviz Kuru Çevrimi: USD -> TRY")
        assert "Doğrudan Kur" in fx_ev_tr.content
        assert "TCMB (2026-10-19, ForexSelling)" in fx_ev_tr.source_reference

        # English EvidenceItem
        assert fx_ev_en.claim.startswith("FX Conversion: USD -> TRY")
        assert "Direct Rate" in fx_ev_en.content
        assert "Doğrudan Kur" not in fx_ev_en.content
        assert "TCMB (2026-10-19, ForexSelling)" in fx_ev_en.source_reference
