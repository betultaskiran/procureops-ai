"""
backend/tests/test_policy_rag.py

Policies Modülü, Qdrant Vektör Tabanı, RAG Arama ve Deterministik Kural Motoru Testleri.
NOT: Bu testlerde kullanılan politika metinleri SENTETİK / ÖRNEK test verileridir, gerçek şirket politikası değildir.
"""

import io
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.policy_document import PolicyDocument
from app.models.quote import Quote
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.compliance import ComplianceChecker
from app.services.deterministic.tco import TCOResult
from app.models.analysis import ComplianceResult


# ── Sentetik Örnek Politika Metni (TEST AMAÇLI) ─────────────────────────────────
SAMPLE_POLICY_TEXT = """
=== ÖRNEK ŞİRKET SATIN ALMA VE TEDARİKÇİ YÖNERGESİ 2026 ===
(DİKKAT: Bu belge yalnızca test ve doğrulama amaçlı sentetik bir dokümandır.)

1. TEDARİKÇİ KALİTE VE SERTİFİKA ZORUNLULUKLARI:
Tüm donanım, sunucu ve altyapı tedarikçilerinin geçerli bir ISO 9001 Kalite Yönetim Sertifikası 
ve ISO 27001 Bilgi Güvenliği Sertifikasına sahip olması zorunludur. Sertifikası bulunmayan 
tedarikçilerin teklifleri doğrudan elenir.

2. ONAY VE BÜTÇE LİMİTLERİ:
Toplam satın alma maliyeti 500.000 TL (KDV dahil) üzerindeki tüm alımlar için Yönetim Kurulu onayı zorunludur. 
Departman müdürleri yalnızca 500.000 TL altındaki harcamaları tek başına onaylayabilir.

3. ÖDEME VADESİ VE ŞARTLARI:
Tüm tedarik sözleşmelerinde azami ödeme vadesi teslimattan sonra Net 45 gündür. 
Peşin ödeme veya Net 60 gün ve üzeri ödeme şartları şirket mali işler direktörlüğü istisnası olmaksızın kabul edilemez.

4. GARANTİ VE SLA KOŞULLARI:
Donanım alımlarında asgari garanti süresi yerinde destek dahil 24 aydır. 
Kritik arızalara müdahale süresi en geç 4 iş günü içinde tamamlanmalıdır.
"""


@pytest.mark.asyncio
async def test_policy_upload_chunking_and_qdrant_sync():
    """
    1. Sentetik politika belgesinin yüklenmesi (Upload).
    2. Parçalama (Chunking) ve Qdrant'a embedding kaydı.
    3. Veritabanında is_chunked=True ve chunk_count doğrulanması.
    4. GET /api/v1/policies ile listelenmesi.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Belgeyi sanal dosya olarak hazırla
        file_bytes = SAMPLE_POLICY_TEXT.encode("utf-8")
        files = {
            "file": ("ornek_satin_alma_politikasi_2026.txt", io.BytesIO(file_bytes), "text/plain")
        }
        data = {
            "title": "Örnek Satın Alma ve Sertifika Politikası 2026 (Sentetik Test)",
            "document_type": "procurement_policy"
        }

        # 1. Upload & Ingest
        res = await client.post("/api/v1/policies/upload", data=data, files=files)
        assert res.status_code == 201, res.text
        policy_data = res.json()
        
        assert policy_data["is_chunked"] is True
        assert policy_data["chunk_count"] > 0
        assert policy_data["processing_error"] is None
        policy_id = policy_data["id"]

        # 2. List Policies
        list_res = await client.get("/api/v1/policies")
        assert list_res.status_code == 200
        policies = list_res.json()
        matching = [p for p in policies if p["id"] == policy_id]
        assert len(matching) == 1
        assert matching[0]["title"] == "Örnek Satın Alma ve Sertifika Politikası 2026 (Sentetik Test)"

        # 3. RAG Semantic Search Test: İlgili kuralı bulma
        search_res = await client.post(
            "/api/v1/policies/search",
            json={
                "query": "Tedarikçilerin ISO sertifikası zorunluluğu var mı?",
                "top_k": 3
            }
        )
        assert search_res.status_code == 200
        search_data = search_res.json()
        assert "ISO 9001" in search_data["context"]
        assert "ISO 27001" in search_data["context"]
        assert "[Kaynak" in search_data["context"]

        # 4. Negative Test: Olmayan / uydurma kural sorgusu
        negative_res = await client.post(
            "/api/v1/policies/search",
            json={
                "query": "Uzay araçları yakıt ikmali ve roket motoru standartları nedir?",
                "top_k": 3
            }
        )
        assert negative_res.status_code == 200
        neg_data = negative_res.json()
        # Vektör tabanında bu konuyla ilgili hiçbir kural bulunmadığı için bağlamda uzay aracı veya roket yer almamalıdır
        assert "roket motoru" not in neg_data["context"].lower()

        # 5. Delete Policy: Vektör tabanı ve DB senkron temizliği
        del_res = await client.delete(f"/api/v1/policies/{policy_id}")
        assert del_res.status_code == 200

        # Silindikten sonra DB'de olmamalı
        get_res = await client.get("/api/v1/policies")
        assert not any(p["id"] == policy_id for p in get_res.json())


@pytest.mark.asyncio
async def test_deterministic_checks_are_independent_of_rag():
    """
    Sayısal bütçe, teslimat süresi ve garanti koşullarının LLM/RAG'a bırakılmadan,
    backend'deki deterministik ComplianceChecker tarafından kesin olarak denetlendiğini doğrular.
    """
    analysis_id = uuid.uuid4()
    dummy_quote_id = uuid.uuid4()

    # Kural dışı teklif (Maksimum 30 gün teslimat, minimum 24 ay garanti, maksimum 400.000 TL bütçe)
    rules = PolicyRules(
        max_delivery_days=30,
        min_warranty_months=24,
        max_tco_budget=400000.0,
        require_payment_terms=["Net 30", "Net 45"]
    )

    # 1. Kuralı ihlal eden teklif
    failing_quote = Quote(
        id=dummy_quote_id,
        rfq_id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        currency="TRY",
        subtotal=450000.0,
        vat_rate=0.20,
        vat_amount=90000.0,
        shipping_cost=10000.0,
        discount_amount=0.0,
        other_costs=0.0,
        total_price=550000.0,
        delivery_days=60,       # 30 günü aşıyor (FAIL)
        warranty_months=12,     # 24 aydan az (FAIL)
        payment_terms="Net 90"  # Net 30/45 dışında (FAIL)
    )

    tco_failing = TCOResult(
        quote_id=dummy_quote_id,
        total_tco=550000.0,
        currency="TRY"
    )

    checks = ComplianceChecker.check_quote(
        quote=failing_quote,
        tco_result=tco_failing,
        rules=rules,
        analysis_id=analysis_id
    )

    results_by_rule = {c.rule_name: c for c in checks}

    # Teslimat süresi deterministik kontrolü
    assert results_by_rule["max_delivery_days"].result == ComplianceResult.FAIL
    assert results_by_rule["max_delivery_days"].actual_value == "60"

    # Garanti süresi deterministik kontrolü
    assert results_by_rule["min_warranty_months"].result == ComplianceResult.FAIL
    assert results_by_rule["min_warranty_months"].actual_value == "12"

    # Bütçe sınırı deterministik kontrolü
    assert results_by_rule["max_tco_budget"].result == ComplianceResult.FAIL
    assert float(results_by_rule["max_tco_budget"].actual_value) == 550000.0

    # Ödeme şartı deterministik kontrolü
    assert results_by_rule["require_payment_terms"].result == ComplianceResult.FAIL

    # 2. Tüm kurallara uyan teklif
    passing_quote = Quote(
        id=dummy_quote_id,
        rfq_id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        currency="TRY",
        subtotal=250000.0,
        vat_rate=0.20,
        vat_amount=50000.0,
        shipping_cost=0.0,
        discount_amount=0.0,
        other_costs=0.0,
        total_price=300000.0,
        delivery_days=20,       # <= 30 gün (PASS)
        warranty_months=36,     # >= 24 ay (PASS)
        payment_terms="Net 45"  # Uygun (PASS)
    )

    tco_passing = TCOResult(
        quote_id=dummy_quote_id,
        total_tco=300000.0,
        currency="TRY"
    )

    passing_checks = ComplianceChecker.check_quote(
        quote=passing_quote,
        tco_result=tco_passing,
        rules=rules,
        analysis_id=analysis_id
    )

    for c in passing_checks:
        assert c.result == ComplianceResult.PASS, f"Rule {c.rule_name} should have passed"
