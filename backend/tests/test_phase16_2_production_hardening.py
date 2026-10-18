"""
backend/tests/test_phase16_2_production_hardening.py

Phase 16.2 — Production Hardening & Deployment Safety Test Suite.

Verifies:
  Phase A: Qdrant vector-store graceful degradation, timeout/connection outage handling,
           preservation of deterministic evaluation (TCO + rules), mandatory human review
           enforcement, and verification gating on missing evidence.
  Phase B: Trusted reverse-proxy IP resolution, spoofed X-Forwarded-For protection,
           multi-hop traversal, malformed IP fail-safe handling, and rate-limit client isolation.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from starlette.requests import Request
from sqlalchemy import select

from app.core.config import settings
from app.core.rate_limit import resolve_client_ip, rate_limit
from app.db.session import AsyncSessionLocal
from app.models.analysis import (
    Analysis,
    AnalysisStatus,
    ComplianceResult,
    Recommendation,
    TCOResult,
    VerificationStatus,
)
from app.models.organization import Organization
from app.models.quote import Quote
from app.models.rfq import RFQ
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.core.security import hash_password
from app.schemas.orchestration import (
    StageName,
    StageStatus,
    VerificationOutcome,
    PolicyComplianceOutput,
    StageEvidenceRef,
    CitationSourceType,
)
from app.services.agent.schemas import AgentRecommendationSchema
from app.services.deterministic.schemas import PolicyRules
from app.services.orchestration.stages import (
    PolicyComplianceStage,
    SupplierRecommendationStage,
    IndependentVerificationStage,
)
from app.services.orchestration.pipeline import AnalysisPipelineOrchestrator
from app.services.rag.service import RAGService


def make_dummy_request(client_host: str = "127.0.0.1", headers: dict = None) -> Request:
    """Helper to build a mock Starlette request with client and headers."""
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/portal/rfq",
        "headers": raw_headers,
        "client": (client_host, 54321),
    }
    return Request(scope)


async def create_test_fixture(session):
    unique = uuid.uuid4().hex[:8]
    org = Organization(name=f"Hardening Org {unique}", slug=f"hardening-org-{unique}")
    session.add(org)
    await session.flush()

    sup1 = Supplier(name=f"Supplier Alpha {unique}", organization_id=org.id)
    sup2 = Supplier(name=f"Supplier Beta {unique}", organization_id=org.id)
    session.add_all([sup1, sup2])

    user = User(
        organization_id=org.id,
        email=f"buyer_{unique}@hardening.com",
        full_name="Hardening Buyer",
        hashed_password=hash_password("Passw0rd123!"),
        role=UserRole.MANAGER.value,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    rfq = RFQ(
        organization_id=org.id,
        title="Industrial Compressor RFQ",
        budget=Decimal("300000.00"),
        max_delivery_days=20,
        min_warranty_months=12,
        payment_terms="net-30",
    )
    session.add(rfq)
    await session.flush()

    q1 = Quote(
        rfq_id=rfq.id,
        supplier_id=sup1.id,
        subtotal=Decimal("120000.00"),
        total_price=Decimal("120000.00"),
        currency="TRY",
        delivery_days=15,
        warranty_months=24,
        payment_terms="net-30",
    )
    q2 = Quote(
        rfq_id=rfq.id,
        supplier_id=sup2.id,
        subtotal=Decimal("130000.00"),
        total_price=Decimal("130000.00"),
        currency="TRY",
        delivery_days=18,
        warranty_months=12,
        payment_terms="net-30",
    )
    session.add_all([q1, q2])
    await session.commit()
    await session.refresh(org)
    await session.refresh(user)
    await session.refresh(rfq)
    await session.refresh(q1)
    await session.refresh(q2)

    return org, user, rfq, [q1, q2]


# ═══════════════════════════════════════════════════════════════════════════════
# Phase A: Qdrant Vector-Store Resilience & Fallback Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_qdrant_resilience_connection_failure():
    """Qdrant connection failure triggers graceful degradation with inconclusive status and error code."""
    async with AsyncSessionLocal() as session:
        org, user, rfq, quotes = await create_test_fixture(session)

        mock_rag = MagicMock(spec=RAGService)
        mock_rag.vector_store = MagicMock()
        mock_rag.vector_store.search = AsyncMock(side_effect=ConnectionError("Connection refused to qdrant:6333"))

        stage_res, output, rag_context, evidence_refs = await PolicyComplianceStage.execute(
            organization_id=str(org.id),
            rfq=rfq,
            quotes=quotes,
            rag_service=mock_rag,
        )

        assert output.infrastructure_error is True
        assert output.error_code == "QDRANT_UNAVAILABLE"
        assert output.rag_status == "insufficient_evidence"
        assert output.is_sufficient_evidence is False
        assert output.evidence_count == 0
        assert len(evidence_refs) == 0

        assert stage_res.status == StageStatus.INCONCLUSIVE
        assert stage_res.error_code == "QDRANT_UNAVAILABLE"
        assert "altyapı kesintisi" in stage_res.summary or "tamamlanamadı" in stage_res.summary
        assert any("kesintisi" in w.lower() for w in stage_res.warnings)
        assert "zorunlu insan incelemesi" in rag_context.lower()


@pytest.mark.asyncio
async def test_qdrant_resilience_timeout():
    """Qdrant search timeout is safely caught, preserving error diagnostics without crashing."""
    async with AsyncSessionLocal() as session:
        org, user, rfq, quotes = await create_test_fixture(session)

        mock_rag = MagicMock(spec=RAGService)
        mock_rag.vector_store = MagicMock()
        mock_rag.vector_store.search = AsyncMock(side_effect=TimeoutError("Qdrant query timed out after 5.0s"))

        stage_res, output, rag_context, evidence_refs = await PolicyComplianceStage.execute(
            organization_id=str(org.id),
            rfq=rfq,
            quotes=quotes,
            rag_service=mock_rag,
        )

        assert output.infrastructure_error is True
        assert output.error_code == "QDRANT_UNAVAILABLE"
        assert output.is_sufficient_evidence is False
        assert stage_res.status == StageStatus.INCONCLUSIVE
        assert stage_res.metadata["infrastructure_error"] is True
        assert stage_res.metadata["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_qdrant_healthy_empty_search_results_distinction():
    """Healthy Qdrant with zero matching hits is clearly distinguished from infrastructure failure."""
    async with AsyncSessionLocal() as session:
        org, user, rfq, quotes = await create_test_fixture(session)

        mock_rag = MagicMock(spec=RAGService)
        mock_rag.vector_store = MagicMock()
        mock_rag.vector_store.search = AsyncMock(return_value=[])  # Healthy, but 0 hits
        mock_rag.filter_and_rank_hits = MagicMock(return_value=[])

        stage_res, output, rag_context, evidence_refs = await PolicyComplianceStage.execute(
            organization_id=str(org.id),
            rfq=rfq,
            quotes=quotes,
            rag_service=mock_rag,
        )

        assert output.infrastructure_error is False  # NOT an infrastructure failure
        assert output.error_code is None
        assert output.rag_status == "insufficient_evidence"
        assert output.is_sufficient_evidence is False
        assert output.evidence_count == 0

        assert stage_res.status == StageStatus.INCONCLUSIVE
        assert stage_res.error_code is None
        assert "0 kanıt maddesi" in stage_res.summary
        assert stage_res.metadata["infrastructure_error"] is False


@pytest.mark.asyncio
async def test_pipeline_e2e_qdrant_failure_preserves_deterministic_tco_and_enforces_human_review():
    """Full pipeline execution during Qdrant outage preserves deterministic TCO, saves results, and forces human review."""
    async with AsyncSessionLocal() as session:
        org, user, rfq, quotes = await create_test_fixture(session)

        mock_rag = MagicMock(spec=RAGService)
        mock_rag.vector_store = MagicMock()
        mock_rag.vector_store.search = AsyncMock(side_effect=ConnectionError("Qdrant host unreachable"))

        mock_llm = MagicMock()
        mock_llm.model_name = "mock-gemini-test"
        mock_llm.extract_structured = AsyncMock(return_value=AgentRecommendationSchema(
            recommended_quote_id=quotes[0].id,
            justification="En düşük maliyet ve yüksek garanti süresi.",
            trade_off_analysis="Alternatifler kıyaslandığında maliyet ve teslimat dengesi sağlanmıştır.",
            risk_factors=["Tedarikçi teslimat geçmişi izlenmelidir."],
            confidence_score=92,
            is_human_review_required=False,  # LLM initially says False
        ))

        orchestrator = AnalysisPipelineOrchestrator(db=session)
        rules = PolicyRules(max_delivery_days=20, min_warranty_months=12)

        analysis, stage_results = await orchestrator.run_pipeline(
            rfq_id=rfq.id,
            rules=rules,
            current_user=user,
            llm_provider=mock_llm,
            rag_service=mock_rag,
        )

        # 1. Pipeline did NOT crash to FAILED; it completed gracefully
        assert analysis.status == AnalysisStatus.COMPLETED.value
        assert len(stage_results) == 5

        # 2. Deterministic TCO and rule evaluation succeeded and were saved
        assert len(analysis.tco_results) == 2
        assert len(analysis.compliance_checks) > 0

        # 3. Policy Stage recorded QDRANT_UNAVAILABLE
        stage3 = next(s for s in stage_results if s.stage == StageName.POLICY_COMPLIANCE)
        assert stage3.status == StageStatus.INCONCLUSIVE
        assert stage3.error_code == "QDRANT_UNAVAILABLE"

        # 4. Independent Verification did NOT pass as VERIFIED; it is strictly INCONCLUSIVE
        stage5 = next(s for s in stage_results if s.stage == StageName.INDEPENDENT_VERIFICATION)
        assert stage5.status == StageStatus.INCONCLUSIVE
        assert analysis.recommendation.verification_status == VerificationStatus.INCONCLUSIVE.value

        # 5. Human review was strictly enforced
        assert "İnsan Onayı Gerekli mi: Evet" in analysis.recommendation.alternative_notes
        assert "ALTYAPI KESİNTİSİ" in analysis.recommendation.verification_notes


@pytest.mark.asyncio
async def test_independent_verification_policy_evidence_gate():
    """IndependentVerificationStage fails the policy evidence check and forces inconclusive when Qdrant failed."""
    async with AsyncSessionLocal() as session:
        org, user, rfq, quotes = await create_test_fixture(session)

        rec_schema = AgentRecommendationSchema(
            recommended_quote_id=quotes[0].id,
            justification="Tüm şartlar uygundur.",
            trade_off_analysis="Trade-off analizi yapılmıştır.",
            risk_factors=[],
            confidence_score=90,
            is_human_review_required=False,
        )

        analysis = Analysis(rfq_id=rfq.id, status=AnalysisStatus.RUNNING.value)
        session.add(analysis)
        await session.flush()

        tco1 = TCOResult(analysis_id=analysis.id, quote_id=quotes[0].id, total_tco=Decimal("120000.00"), currency="TRY", subtotal=Decimal("120000.00"), vat_amount=Decimal(0), shipping_cost=Decimal(0), discount_amount=Decimal(0), other_costs=Decimal(0))
        session.add(tco1)
        await session.flush()

        failed_policy_output = PolicyComplianceOutput(
            rag_status="insufficient_evidence",
            evidence_count=0,
            citations=[],
            query_used="test query",
            is_sufficient_evidence=False,
            infrastructure_error=True,
            error_code="QDRANT_UNAVAILABLE",
        )

        stage_res, output, rec_record = await IndependentVerificationStage.execute(
            db=session,
            analysis_id=analysis.id,
            recommendation_schema=rec_schema,
            quotes=quotes,
            eligible_quotes=[quotes[0]],
            eliminated_quotes=[quotes[1]],
            tco_results=[tco1],
            compliance_checks=[],
            policy_evidence_refs=[],
            policy_output=failed_policy_output,
        )

        assert output.verification_status == VerificationOutcome.INCONCLUSIVE
        assert rec_schema.is_human_review_required is True
        assert rec_record.verification_status == VerificationStatus.INCONCLUSIVE.value

        policy_check = next(c for c in output.checks if c.name == "policy_evidence_verification")
        assert policy_check.passed is False
        assert "ALTYAPI_KESINTISI" in policy_check.actual_value


# ═══════════════════════════════════════════════════════════════════════════════
# Phase B: Trusted Proxy & Rate Limiting Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_resolve_client_ip_direct_with_spoofed_forwarded_for():
    """Untrusted direct clients cannot spoof IP via X-Forwarded-For; direct peer IP is strictly enforced."""
    req = make_dummy_request(
        client_host="198.51.100.4",
        headers={"X-Forwarded-For": "10.0.0.1, 192.168.1.50"}
    )
    # Default settings (no trusted proxies configured)
    resolved = resolve_client_ip(req, trusted_proxies=[])
    assert resolved == "198.51.100.4"


def test_resolve_client_ip_from_single_trusted_proxy():
    """Requests arriving through a configured trusted reverse proxy extract the real client IP."""
    req = make_dummy_request(
        client_host="10.0.0.2",
        headers={"X-Forwarded-For": "203.0.113.88"}
    )
    resolved = resolve_client_ip(req, trusted_proxies=["10.0.0.0/8"])
    assert resolved == "203.0.113.88"


def test_resolve_client_ip_multi_hop_proxy_chain():
    """Right-to-left traversal extracts the first untrusted IP in a multi-proxy chain."""
    req = make_dummy_request(
        client_host="10.0.0.2",
        headers={"X-Forwarded-For": "198.51.100.5, 172.16.0.50, 10.0.0.99"}
    )
    # 10.0.0.0/8 and 172.16.0.0/12 are trusted reverse proxies (e.g. edge and ingress)
    resolved = resolve_client_ip(req, trusted_proxies=["10.0.0.0/8", "172.16.0.0/12"])
    assert resolved == "198.51.100.5"


def test_resolve_client_ip_invalid_or_empty_proxy_config():
    """Malformed or invalid proxy CIDRs fail safely to direct client peer without crashing."""
    req = make_dummy_request(
        client_host="192.0.2.1",
        headers={"X-Forwarded-For": "8.8.8.8"}
    )
    resolved = resolve_client_ip(req, trusted_proxies=["invalid-cidr-string", "999.999.999.999/99"])
    assert resolved == "192.0.2.1"


def test_resolve_client_ip_malformed_forwarded_for_header():
    """Malformed or hostile X-Forwarded-For headers fail safely to trusted peer IP without exceptions."""
    req = make_dummy_request(
        client_host="10.0.0.2",
        headers={"X-Forwarded-For": "<script>alert(1)</script>, not-an-ip"}
    )
    resolved = resolve_client_ip(req, trusted_proxies=["10.0.0.0/8"])
    assert resolved == "10.0.0.2"


def test_rate_limit_key_stability_and_isolation():
    """Identical clients receive identical rate-limit keys; distinct clients receive independent keys."""
    req_a = make_dummy_request(client_host="198.51.100.1")
    req_a_again = make_dummy_request(client_host="198.51.100.1")
    req_b = make_dummy_request(client_host="198.51.100.2")

    ip_a = resolve_client_ip(req_a, trusted_proxies=[])
    ip_a_again = resolve_client_ip(req_a_again, trusted_proxies=[])
    ip_b = resolve_client_ip(req_b, trusted_proxies=[])

    assert ip_a == ip_a_again == "198.51.100.1"
    assert ip_b == "198.51.100.2"
    assert ip_a != ip_b
