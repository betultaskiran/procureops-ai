"""
backend/tests/test_multi_currency_rfq_analysis.py

End-to-End Regression Test:
Validates that an RFQ with quotes in different currencies (TRY, USD, EUR)
successfully completes the 5-stage analysis pipeline via POST /api/v1/rfqs/{rfq_id}/analyze
with 200 OK, performing deterministic TCO currency normalization and preserving
audit evidence without 400 Bad Request errors.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.analysis import Analysis, AnalysisStatus, Recommendation, VerificationStatus
from app.models.organization import Organization
from app.models.quote import Quote
from app.models.rfq import RFQ
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.services.agent.schemas import AgentRecommendationSchema
from app.services.agent.service import AgentService
from app.services.fx.schemas import ExchangeRateDTO


@pytest.mark.asyncio
async def test_multi_currency_rfq_analysis_returns_200_ok():
    """
    Kullanıcı Senaryosu:
    Farklı para birimlerine (TRY, USD, EUR) sahip teklifler içeren bir RFQ için
    POST /api/v1/rfqs/{rfq_id}/analyze çağrısı yapılır.
    Deterministik FX motoru sayesinde 400 Bad Request
    alınmadan 200 OK ile analiz başarıyla tamamlanır.
    """
    async with AsyncSessionLocal() as session:

        # 2. Test organizasyonu, tedarikçileri ve kullanıcısını oluştur
        unique = uuid.uuid4().hex[:8]
        org = Organization(name=f"MultiCurr Org {unique}", slug=f"multicurr-org-{unique}")
        session.add(org)
        await session.flush()

        sup_try = Supplier(name=f"Yerel Tedarikçi {unique}", organization_id=org.id)
        sup_usd = Supplier(name=f"Global US Supplier {unique}", organization_id=org.id)
        sup_eur = Supplier(name=f"European Partner {unique}", organization_id=org.id)
        session.add_all([sup_try, sup_usd, sup_eur])
        await session.flush()

        user = User(
            organization_id=org.id,
            email=f"buyer_{unique}@procureops.local",
            full_name="Procurement Specialist",
            hashed_password=hash_password("Passw0rd123!"),
            role=UserRole.MANAGER.value,
            is_active=True,
        )
        session.add(user)
        await session.flush()

        # 3. RFQ Oluştur (Bütçe: 150,000 TRY)
        rfq = RFQ(
            organization_id=org.id,
            title=f"Multi-Currency Enterprise Server Procurement {unique}",
            budget=Decimal("150000.00"),
            max_delivery_days=20,
            min_warranty_months=24,
            payment_terms="net-30",
        )
        session.add(rfq)
        await session.flush()

        # 4. Üç farklı para biriminde teklif ekle
        # Quote 1: 50,000 TRY
        q_try = Quote(
            rfq_id=rfq.id,
            supplier_id=sup_try.id,
            subtotal=Decimal("50000.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("10000.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("60000.00"),
            currency="TRY",
            delivery_days=10,
            warranty_months=24,
            payment_terms="net-30",
        )
        # Quote 2: 1,500 USD (TCO: 1,800 USD -> 1800 * 34.50 = 62,100 TRY)
        q_usd = Quote(
            rfq_id=rfq.id,
            supplier_id=sup_usd.id,
            subtotal=Decimal("1500.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("300.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("1800.00"),
            currency="USD",
            delivery_days=12,
            warranty_months=36,
            payment_terms="net-30",
        )
        # Quote 3: 1,400 EUR (TCO: 1,680 EUR -> 1680 * 37.50 = 63,000 TRY)
        q_eur = Quote(
            rfq_id=rfq.id,
            supplier_id=sup_eur.id,
            subtotal=Decimal("1400.00"),
            vat_rate=Decimal("0.20"),
            vat_amount=Decimal("280.00"),
            shipping_cost=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            other_costs=Decimal("0.00"),
            total_price=Decimal("1680.00"),
            currency="EUR",
            delivery_days=14,
            warranty_months=24,
            payment_terms="net-30",
        )
        session.add_all([q_try, q_usd, q_eur])
        await session.commit()
        await session.refresh(rfq)
        await session.refresh(q_try)
        await session.refresh(q_usd)
        await session.refresh(q_eur)

        token = create_access_token({"sub": str(user.id), "org_id": str(org.id), "role": "manager"})
        headers = {"Authorization": f"Bearer {token}"}

    # 5. LLM ve FX sağlayıcısını mocklayarak deterministik E2E analiz endpoint'ini çalıştır
    mock_agent_schema = AgentRecommendationSchema(
        recommended_quote_id=q_try.id,
        justification="Yerel Tedarikçi TRY bazında en düşük TCO ve hızlı teslimat sunmaktadır [Kaynak 1: Kural Motoru].",
        trade_off_analysis="USD ve EUR teklifleri döviz kuru riski taşımakta olup TRY teklifi daha avantajlıdır.",
        risk_factors=[],
        confidence_score=95,
        is_human_review_required=False,
    )

    from app.services.fx.tcmb_provider import TCMBExchangeRateProvider
    today_utc = datetime.now(timezone.utc).date()
    mock_fx_rates = [
        ExchangeRateDTO(
            source_currency="USD",
            target_currency="TRY",
            rate=Decimal("40.000000"),
            rate_type="ForexSelling",
            source="TCMB",
            rate_date=today_utc,
            fetched_at=datetime.now(timezone.utc),
            unit=1,
            bulletin_no="TEST/001",
        ),
        ExchangeRateDTO(
            source_currency="EUR",
            target_currency="TRY",
            rate=Decimal("44.000000"),
            rate_type="ForexSelling",
            source="TCMB",
            rate_date=today_utc,
            fetched_at=datetime.now(timezone.utc),
            unit=1,
            bulletin_no="TEST/001",
        ),
    ]

    with patch.object(AgentService, "generate_recommendation", new_callable=AsyncMock) as mock_agent, \
         patch.object(TCMBExchangeRateProvider, "fetch_rates", new_callable=AsyncMock, return_value=mock_fx_rates):
        async def fake_recommendation(analysis_id, organization_id, locale="tr"):
            async with AsyncSessionLocal() as inner_session:
                rec = Recommendation(
                    analysis_id=analysis_id,
                    recommended_quote_id=q_try.id,
                    reasoning=f"{mock_agent_schema.justification}\n\n**Trade-off Analizi:**\n{mock_agent_schema.trade_off_analysis}",
                    verification_status=VerificationStatus.PENDING.value,
                    risks="[]",
                    alternative_notes="Güven Skoru: 95/100. İnsan Onayı Gerekli mi: Hayır",
                )
                inner_session.add(rec)
                await inner_session.commit()
                await inner_session.refresh(rec)
                return rec

        mock_agent.side_effect = fake_recommendation

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/rfqs/{rfq.id}/analyze",
                json={
                    "rules": {
                        "max_tco_budget": 150000.00,
                        "budget_currency": "TRY",
                        "max_delivery_days": 20,
                        "min_warranty_months": 24,
                    },
                    "locale": "tr",
                },
                headers=headers,
            )

        # 6. 200 OK Doğrulaması
        assert resp.status_code == 200, f"Expected 200 OK but got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["status"] == "completed"

        # 7. TCO Sonuçları Doğrulaması: Her para birimi TRY'ye doğru çevrilmiş olmalı
        tco_map = {t["quote_id"]: t for t in data["tco_results"]}
        assert str(q_try.id) in tco_map
        assert str(q_usd.id) in tco_map
        assert str(q_eur.id) in tco_map

        # TRY Teklifi: 60,000 TRY (Identity kur 1.0)
        tco_try = tco_map[str(q_try.id)]
        assert tco_try["currency"] == "TRY"
        assert tco_try["target_currency"] == "TRY"
        assert tco_try["exchange_rate"] == 1.0
        assert tco_try["converted_total_tco"] == 60000.0

        # USD Teklifi: 1,800 USD converted to TRY using validated rate
        tco_usd_res = tco_map[str(q_usd.id)]
        assert tco_usd_res["currency"] == "USD"
        assert tco_usd_res["target_currency"] == "TRY"
        usd_rate = tco_usd_res["exchange_rate"]
        assert usd_rate is not None and usd_rate > 0
        expected_usd_tco = round(1800.0 * usd_rate, 4)
        assert tco_usd_res["converted_total_tco"] == expected_usd_tco
        assert "USD/TRY" in tco_usd_res["calculation_notes"]
        assert tco_usd_res["exchange_rate_source"] == "TCMB"

        # EUR Teklifi: 1,680 EUR converted to TRY using validated rate
        tco_eur_res = tco_map[str(q_eur.id)]
        assert tco_eur_res["currency"] == "EUR"
        assert tco_eur_res["target_currency"] == "TRY"
        eur_rate = tco_eur_res["exchange_rate"]
        assert eur_rate is not None and eur_rate > 0
        expected_eur_tco = round(1680.0 * eur_rate, 4)
        assert tco_eur_res["converted_total_tco"] == expected_eur_tco
        assert "EUR/TRY" in tco_eur_res["calculation_notes"]
        assert tco_eur_res["exchange_rate_source"] == "TCMB"

        # 8. Tüm 5 Aşamanın Başarıyla Tamamlandığını Doğrula
        stage_names = [s["stage"] for s in data["stage_results"]]
        assert "extraction_validation" in stage_names
        assert "deterministic_evaluation" in stage_names
        assert "policy_compliance" in stage_names
        assert "supplier_recommendation" in stage_names
        assert "independent_verification" in stage_names

        # 9. GET /api/v1/rfqs/{rfq_id}/analysis sorgusunun da 200 döndüğünü doğrula
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            get_resp = await client.get(
                f"/api/v1/rfqs/{rfq.id}/analysis",
                headers=headers,
            )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["id"] == data["id"]
        assert len(get_data["tco_results"]) == 3
