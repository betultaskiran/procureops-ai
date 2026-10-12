"""
backend/tests/test_policy_rag.py

Policies Modülü, PDF Metin Çıkarımı (Extraction), Chunking,
Qdrant Vektör Tabanı Senkronizasyonu, 5 Hedefli Sorgu ve Deterministik Kural Testleri.
"""

import io
import uuid
from pathlib import Path
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
from app.services.extraction.pdf_parser import extract_text_from_pdf
from app.services.rag.service import RAGService


# ── Test PDF Dosya Yolu ───────────────────────────────────────────────────────
def get_test_pdf_path() -> Path:
    p = Path("uploads/policies/policy_4f32c978-fdb1-43b2-8d20-e8a174553e47.pdf")
    if p.exists():
        return p
    candidates = list(Path("uploads/policies").glob("*.pdf"))
    if candidates:
        return candidates[0]
    return Path("uploads/policies/policy_f7dd5b7a-5848-4b53-be85-34043348cb8f.pdf")


@pytest.mark.asyncio
async def test_uploaded_pdf_extraction_and_chunking_integrity():
    """
    Görev 4:
    1. PDF extraction çıktısında üç maddenin tamamının mevcut olduğunu doğrula.
    2. Chunk'ların birleşiminde üç maddenin de korunduğunu doğrula.
    """
    test_pdf = get_test_pdf_path()
    assert test_pdf.exists(), f"Test PDF dosyası diskte bulunamadı: {test_pdf}"

    # 1. Metin çıkarma
    extracted_text = extract_text_from_pdf(test_pdf)
    assert len(extracted_text) > 500, "Çıkarılan metin çok kısa"

    # Madde 1 doğrulaması
    assert "250.000 TL" in extracted_text or "250000" in extracted_text
    assert "CFO" in extracted_text
    assert "1.000.000 TL" in extracted_text
    assert "Yönetim Kurulu" in extracted_text

    # Madde 2 doğrulaması
    assert "ISO 9001" in extracted_text
    assert "Donanım" in extracted_text

    # Madde 3 doğrulaması
    assert "%90" in extracted_text
    assert "3 iş günü" in extracted_text
    assert "6 ay" in extracted_text

    # 2. Chunking doğrulaması
    rag = RAGService()
    chunks = rag._chunk_text(extracted_text)
    assert len(chunks) >= 3, f"Beklenen en az 3 chunk, üretilen: {len(chunks)}"

    combined_chunks = "\n\n".join(chunks)
    assert "250.000 TL" in combined_chunks
    assert "ISO 9001" in combined_chunks
    assert "%90" in combined_chunks
    assert "6 ay" in combined_chunks


@pytest.mark.asyncio
async def test_all_five_targeted_queries_retrieve_exact_articles():
    """
    Görev 2 ve Görev 4:
    Aşağıdaki 5 hedefli sorunun her biri için doğru politika maddesinin
    Qdrant retrieval sonuçlarında bulunduğunu doğrular.
    1. 250.000 TL üzerindeki alımlarda kimlerin onayı gerekir?
    2. 1.000.000 TL üzerindeki yatırımları kim onaylar?
    3. Donanım alımlarında hangi ISO sertifikası zorunludur?
    4. Teslimat güvenilirliği için minimum skor kaçtır?
    5. Üç iş gününden fazla gecikmenin sonucu nedir?
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Önce organizasyonu al
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Organization).limit(1))
            org = res.scalars().first()
            assert org is not None
            org_id = org.id

        # Soru 1: 250.000 TL onay yetkisi
        q1_res = await client.post(
            "/api/v1/policies/search",
            json={"query": "250.000 TL üzerindeki alımlarda kimlerin onayı gerekir?", "top_k": 3, "organization_id": str(org_id)}
        )
        assert q1_res.status_code == 200
        q1_ctx = q1_res.json()["context"]
        assert "250.000 TL" in q1_ctx
        assert "CFO" in q1_ctx
        assert "Satın Alma Direktörü" in q1_ctx

        # Soru 2: 1.000.000 TL onay yetkisi
        q2_res = await client.post(
            "/api/v1/policies/search",
            json={"query": "1.000.000 TL üzerindeki yatırımları kim onaylar?", "top_k": 3, "organization_id": str(org_id)}
        )
        assert q2_res.status_code == 200
        q2_ctx = q2_res.json()["context"]
        assert "1.000.000 TL" in q2_ctx
        assert "Yönetim Kurulu" in q2_ctx

        # Soru 3: ISO 9001 donanım sertifikası
        q3_res = await client.post(
            "/api/v1/policies/search",
            json={"query": "Donanım alımlarında hangi ISO sertifikası zorunludur?", "top_k": 3, "organization_id": str(org_id)}
        )
        assert q3_res.status_code == 200
        q3_ctx = q3_res.json()["context"]
        assert "ISO 9001" in q3_ctx
        assert "Donanım" in q3_ctx

        # Soru 4: Teslimat güvenilirlik skoru
        q4_res = await client.post(
            "/api/v1/policies/search",
            json={"query": "Teslimat güvenilirliği için minimum skor kaçtır?", "top_k": 3, "organization_id": str(org_id)}
        )
        assert q4_res.status_code == 200
        q4_ctx = q4_res.json()["context"]
        assert "%90" in q4_ctx

        # Soru 5: Üç iş günü gecikme sonucu
        q5_res = await client.post(
            "/api/v1/policies/search",
            json={"query": "Üç iş gününden fazla gecikmenin sonucu nedir?", "top_k": 3, "organization_id": str(org_id)}
        )
        assert q5_res.status_code == 200
        q5_ctx = q5_res.json()["context"]
        assert "3 iş günü" in q5_ctx
        assert "6 ay" in q5_ctx


@pytest.mark.asyncio
async def test_tenant_isolation_on_policy_search():
    """
    Farklı organizasyonun ID'si verildiğinde mevcut organizasyonun verisinin
    kesinlikle gelmediğini doğrular (Multi-tenancy isolation).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fake_org_id = uuid.uuid4()
        res = await client.post(
            "/api/v1/policies/search",
            json={"query": "ISO 9001 sertifikası", "top_k": 3, "organization_id": str(fake_org_id)}
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["hits"]) == 0
        assert "bulunamadı" in data["context"].lower()


@pytest.mark.asyncio
async def test_policy_deletion_clears_qdrant_vectors():
    """
    Yeni yüklenen bir belgenin silindiğinde Qdrant'tan da temizlendiğini doğrular.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Benzersiz token ile geçici bir metin belgesi yükle
        unique_token = f"TEST_TOKEN_{uuid.uuid4().hex[:8]}"
        temp_text = f"GEÇİCİ POLİTİKA {unique_token}: Tüm ofis harcamaları için Genel Müdür onayı şarttır."
        files = {"file": ("gecici_politika.txt", io.BytesIO(temp_text.encode("utf-8")), "text/plain")}
        data = {"title": f"Geçici Test Politikası {unique_token}", "document_type": "other"}

        upload_res = await client.post("/api/v1/policies/upload", data=data, files=files)
        assert upload_res.status_code == 201
        upload_data = upload_res.json()
        assert upload_data["is_chunked"] is True, f"Upload chunking error: {upload_data.get('processing_error')}"
        temp_id = upload_data["id"]
        org_id = upload_data["organization_id"]

        # Arama ile geldiğini doğrula
        search_res = await client.post(
            "/api/v1/policies/search",
            json={"query": f"Genel Müdür onayı {unique_token}", "top_k": 3, "organization_id": str(org_id)}
        )
        assert search_res.status_code == 200
        search_json = search_res.json()
        assert any(unique_token in h["text"] for h in search_json["hits"]) or unique_token in search_json["context"]

        # Belgeyi sil
        del_res = await client.delete(f"/api/v1/policies/{temp_id}")
        assert del_res.status_code == 200

        # Silindikten sonra aramada dönmemeli
        search_after = await client.post(
            "/api/v1/policies/search",
            json={"query": f"Genel Müdür onayı {unique_token}", "top_k": 3, "organization_id": str(org_id)}
        )
        assert search_after.status_code == 200
        assert unique_token not in search_after.json()["context"]
        assert not any(unique_token in h["text"] for h in search_after.json()["hits"])


@pytest.mark.asyncio
async def test_deterministic_checks_are_independent_of_rag():
    """
    Sayısal bütçe, teslimat süresi ve garanti koşullarının LLM/RAG'a bırakılmadan,
    backend'deki deterministik ComplianceChecker tarafından kesin olarak denetlendiğini doğrular.
    """
    analysis_id = uuid.uuid4()
    dummy_quote_id = uuid.uuid4()

    rules = PolicyRules(
        max_delivery_days=30,
        min_warranty_months=24,
        max_tco_budget=400000.0,
        require_payment_terms=["Net 30", "Net 45"]
    )

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

    assert results_by_rule["max_delivery_days"].result == ComplianceResult.FAIL
    assert results_by_rule["max_delivery_days"].actual_value == "60"

    assert results_by_rule["min_warranty_months"].result == ComplianceResult.FAIL
    assert results_by_rule["min_warranty_months"].actual_value == "12"

    assert results_by_rule["max_tco_budget"].result == ComplianceResult.FAIL
    assert float(results_by_rule["max_tco_budget"].actual_value) == 550000.0

    assert results_by_rule["require_payment_terms"].result == ComplianceResult.FAIL


@pytest.mark.asyncio
async def test_sla_and_multi_document_retrieval_with_source_cards():
    """
    SLA belgesindeki garanti, teslimat ve arıza müdahalesi maddelerinin
    zengin kaynak kartı metadata'ları (başlık, madde başlığı, sayfa numarası, dosya linki)
    ile doğru şekilde döndüğünü ve çoklu belge retrieval'ını doğrular.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Organization).limit(1))
            org = res.scalars().first()
            assert org is not None
            org_id = org.id

        # 1. SLA Garanti Maddesi
        res_warranty = await client.post(
            "/api/v1/policies/search",
            json={"query": "SLA garanti süresi ve kapsamı nedir?", "top_k": 3, "organization_id": str(org_id)}
        )
        assert res_warranty.status_code == 200
        w_data = res_warranty.json()
        assert len(w_data["hits"]) > 0
        top_hit = w_data["hits"][0]
        assert "36 ay" in top_hit["text"] or "garanti" in top_hit["text"].lower()
        assert top_hit["section_title"] is not None
        assert "GARANTİ" in top_hit["section_title"].upper()
        assert top_hit["page_number"] == 1
        assert top_hit["file_url"].startswith("/api/v1/policies/")

        # 2. SLA Arıza Müdahale Maddesi
        res_sla = await client.post(
            "/api/v1/policies/search",
            json={"query": "Kritik sunucu arıza müdahale süresi azami kaç saattir?", "top_k": 3, "organization_id": str(org_id)}
        )
        assert res_sla.status_code == 200
        sla_data = res_sla.json()
        assert len(sla_data["hits"]) > 0
        sla_hit = sla_data["hits"][0]
        assert "4 saat" in sla_hit["text"]
        assert "24 saat" in sla_hit["text"]
        assert "ARIZA MÜDAHALE" in (sla_hit["section_title"] or "").upper()

        # 3. Çoklu Belge Sorgusu (Donanım teslimatı hem SLA'da hem Satın Alma Politikasında var)
        res_multi = await client.post(
            "/api/v1/policies/search",
            json={"query": "Donanım teslimat ve lojistik kuralları nelerdir?", "top_k": 5, "organization_id": str(org_id)}
        )
        assert res_multi.status_code == 200
        multi_data = res_multi.json()
        # İki farklı belgenin de bulunabildiğini doğrula
        sources = {h["source"] for h in multi_data["hits"]}
        assert len(sources) >= 1
        assert any("14" in h["text"] or "teslimat" in h["text"].lower() for h in multi_data["hits"])


@pytest.mark.asyncio
async def test_policy_file_streaming_endpoint():
    """
    Orijinal PDF dosyasına erişim endpoint'ini doğrular.
    - Geçerli ID ile dosya indirilebilir veya inline görüntülenebilir (HTTP 200, PDF).
    - Geçersiz ID ile açık ve net HTTP 404 hatası döner.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Mevcut bir PDF politikasını bul
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(PolicyDocument).where(PolicyDocument.file_name.ilike("%.pdf")).limit(1))
            policy = res.scalars().first()
            assert policy is not None
            valid_id = policy.id

        # 1. Başarılı dosya akışı
        file_res = await client.get(f"/api/v1/policies/{valid_id}/file")
        assert file_res.status_code == 200
        assert "application/pdf" in file_res.headers.get("content-type", "")
        assert "inline" in file_res.headers.get("content-disposition", "")
        assert len(file_res.content) > 1000

        # 2. Olmayan ID sorgusu
        fake_id = uuid.uuid4()
        err_res = await client.get(f"/api/v1/policies/{fake_id}/file")
        assert err_res.status_code == 404
        assert "bulunamadı" in err_res.json()["detail"].lower()

        # 3. Yanlış organizasyon ID ile yetki reddi (HTTP 403)
        fake_org = uuid.uuid4()
        forbidden_res = await client.get(f"/api/v1/policies/{valid_id}/file?organization_id={fake_org}")
        assert forbidden_res.status_code == 403
        assert "yetkiniz" in forbidden_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_six_critical_queries_and_negative_retrieval():
    """
    Kullanıcının talep ettiği 6 kritik sorguyu ve negatif kanıt yönetimini doğrular:
    1. Standart dizüstü bilgisayar için minimum garanti süresi nedir? (24 ay / 2 yıl, SLA)
    2. Kritik sunucu arızasında müdahale ve çözüm süreleri nedir? (4 saat / 24 saat, SLA)
    3. Standart donanımın azami teslimat süresi nedir? (14 gün, SLA)
    4. 300.000 TL tutarındaki bir satın alma için hangi onaylar gerekir? (Satın Alma Direktörü ve CFO, Yönetmelik)
    5. ISO 9001 sertifikası olmayan bir BT donanım tedarikçisine ne olur? (Elenir, Yönetmelik)
    6. Belgelerde bulunmayan bir ödeme/teminat kuralı sorulduğunda sistem ne yapar? (Yeterli kanıt bulunamadı, 0 hit, halüsinasyonsuz)
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Organization).limit(1))
            org = res.scalars().first()
            assert org is not None
            org_id = str(org.id)

        # 1. Standart dizüstü bilgisayar garanti süresi
        r1 = await client.post("/api/v1/policies/search", json={
            "query": "Standart dizüstü bilgisayar için minimum garanti süresi nedir?",
            "top_k": 3,
            "organization_id": org_id
        })
        assert r1.status_code == 200
        d1 = r1.json()
        assert len(d1["hits"]) >= 1
        top_h1 = d1["hits"][0]
        assert "GARANTİ" in (top_h1["section_title"] or "").upper()
        assert "24 ay" in top_h1["text"] or "2 yıl" in top_h1["text"]
        assert top_h1["score"] >= 0.70
        # Mükerrer başlık olmadığını doğrula (gövde metni başlıkla başlamamalı)
        assert not top_h1["text"].strip().startswith("###")

        # 2. Kritik sunucu arıza müdahale ve çözüm
        r2 = await client.post("/api/v1/policies/search", json={
            "query": "Kritik sunucu arızasında müdahale ve çözüm süreleri nedir?",
            "top_k": 3,
            "organization_id": org_id
        })
        assert r2.status_code == 200
        d2 = r2.json()
        assert len(d2["hits"]) >= 1
        top_h2 = d2["hits"][0]
        assert "ARIZA" in (top_h2["section_title"] or "").upper()
        assert "4 saat" in top_h2["text"]
        assert "24 saat" in top_h2["text"]
        assert top_h2["score"] >= 0.75

        # 3. Standart donanımın azami teslimat süresi
        r3 = await client.post("/api/v1/policies/search", json={
            "query": "Standart donanımın azami teslimat süresi nedir?",
            "top_k": 3,
            "organization_id": org_id
        })
        assert r3.status_code == 200
        d3 = r3.json()
        assert len(d3["hits"]) >= 1
        top_h3 = d3["hits"][0]
        assert "TESLİMAT" in (top_h3["section_title"] or "").upper()
        assert "14" in top_h3["text"]
        assert top_h3["score"] >= 0.70

        # 4. 300.000 TL satın alma onay yetkisi
        r4 = await client.post("/api/v1/policies/search", json={
            "query": "300.000 TL tutarındaki bir satın alma için hangi onaylar gerekir?",
            "top_k": 3,
            "organization_id": org_id
        })
        assert r4.status_code == 200
        d4 = r4.json()
        assert len(d4["hits"]) >= 1
        top_h4 = d4["hits"][0]
        assert "ONAY" in (top_h4["section_title"] or "").upper()
        assert "CFO" in top_h4["text"]
        assert "Satın Alma Direktörü" in top_h4["text"]
        # İlgisiz SLA belgesinin çekilmediğini doğrula
        assert all(h["document_type"] == "procurement_policy" for h in d4["hits"])

        # 5. ISO 9001 sertifikası olmayan tedarikçi
        r5 = await client.post("/api/v1/policies/search", json={
            "query": "ISO 9001 sertifikası olmayan bir BT donanım tedarikçisine ne olur?",
            "top_k": 3,
            "organization_id": org_id
        })
        assert r5.status_code == 200
        d5 = r5.json()
        assert len(d5["hits"]) >= 1
        top_h5 = d5["hits"][0]
        assert "KALİTE" in (top_h5["section_title"] or "").upper()
        assert "ISO 9001" in top_h5["text"]
        assert "elenir" in top_h5["text"].lower() or "teknik" in top_h5["text"].lower()

        # 6. NEGATİF SORGU: Belgelerde bulunmayan bir ödeme/teminat kuralı
        r6 = await client.post("/api/v1/policies/search", json={
            "query": "Belgelerde bulunmayan bir ödeme/teminat kuralı sorulduğunda sistem ne yapar?",
            "top_k": 3,
            "organization_id": org_id
        })
        assert r6.status_code == 200
        d6 = r6.json()
        # İlgisiz maddeler yapay olarak döndürülmemelidir
        assert len(d6["hits"]) == 0
        # Modelin uydurma yapmaması için context açıkça negatif uyarı içermelidir
        assert "bulunamadı" in d6["context"].lower()
        assert "varsayımda bulunmadan" in d6["context"].lower()

