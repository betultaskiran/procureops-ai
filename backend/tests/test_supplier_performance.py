import math
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.supplier import Supplier, SupplierHistory
from app.models.rfq import RFQ, RFQStatus
from app.models.quote import Quote
from app.models.analysis import Analysis, AnalysisStatus, Approval, ApprovalStatus
from app.models.order import PurchaseOrder, PurchaseOrderStatus
from app.models.user import UserRole
from app.services.supplier.performance import SupplierPerformanceService
from tests.auth_helper import create_test_auth_context


async def create_base_test_data(session):
    unique_suffix = uuid.uuid4().hex[:8]
    # Use existing default org if present for mock auth consistency
    res = await session.execute(select(Organization).limit(1))
    org = res.scalars().first()
    if not org:
        org = Organization(
            name=f"Perf Org {unique_suffix}",
            slug=f"perf-org-{unique_suffix}"
        )
        session.add(org)
        await session.flush()

    supplier = Supplier(
        name=f"Perf Supplier {unique_suffix}",
        organization_id=org.id
    )
    session.add(supplier)
    await session.flush()

    rfq = RFQ(
        organization_id=org.id,
        title="Perf RFQ",
        budget=Decimal("150000.00"),
        status=RFQStatus.APPROVED.value,
    )
    session.add(rfq)
    await session.flush()

    quote = Quote(
        rfq_id=rfq.id,
        supplier_id=supplier.id,
        currency="TRY",
        subtotal=Decimal("80000.00"),
        total_price=Decimal("96000.00"),
        delivery_days=14,
        payment_terms="net-30",
    )
    session.add(quote)
    await session.flush()

    analysis = Analysis(
        rfq_id=rfq.id,
        status=AnalysisStatus.COMPLETED.value
    )
    session.add(analysis)
    await session.flush()

    approval = Approval(
        analysis_id=analysis.id,
        status=ApprovalStatus.APPROVED.value,
        selected_quote_id=quote.id,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(approval)
    await session.commit()

    return org, supplier, rfq, quote, approval


# ── Test 1: Empty history returns unavailable state and null metrics ──────────
@pytest.mark.asyncio
async def test_empty_history_returns_unavailable_and_null_metrics():
    """1. Sıfır geçmişe sahip tedarikçi: teslimat güvenilirliği unavailable ve null dönmeli; 0% uydurulmamalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, _, _, _ = await create_base_test_data(session)

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        assert perf.supplier_id == supplier.id
        assert perf.evaluated_orders_count == 0
        assert perf.confidence_level == "insufficient"
        assert perf.order_summary.total_orders_count == 0
        assert perf.order_summary.completed_orders_count == 0

        # Teslimat güvenilirliği
        assert perf.delivery_reliability.is_available is False
        assert perf.delivery_reliability.confidence == "insufficient"
        assert perf.delivery_reliability.eligible_orders_count == 0
        assert perf.delivery_reliability.on_time_orders_count is None
        assert perf.delivery_reliability.on_time_percentage is None
        assert perf.delivery_reliability.average_delay_days is None

        # Finansal özet boş olmalı
        assert perf.financial_summary == {}

        # Kalite takibi yapılmadığı açıkça belirtilmeli
        assert perf.quality_metrics.is_tracked is False
        assert perf.quality_metrics.tracked_orders_count == 0
        assert perf.quality_metrics.total_quality_issues is None
        assert perf.quality_metrics.total_rejections is None


# ── Test 2: Orders with missing delivery dates excluded ─────────────────────────
@pytest.mark.asyncio
async def test_orders_with_missing_delivery_dates_excluded_from_delivery_metrics():
    """2. Teslimat tarihi bilgisi olmayan siparişler güvenilirlik hesabına dahil edilmemeli."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        # Aktif PO (tarih yok)
        po1 = PurchaseOrder(
            po_number=f"PO-TEST-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.ISSUED.value,
            expected_delivery_date=date(2026, 11, 1),
            actual_delivery_date=None,  # Fiilî teslim henüz yapılmadı
        )
        session.add(po1)
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        assert perf.order_summary.active_orders_count == 1
        assert perf.order_summary.completed_orders_count == 0
        assert perf.delivery_reliability.is_available is False
        assert perf.delivery_reliability.eligible_orders_count == 0
        assert perf.delivery_reliability.on_time_percentage is None


# ── Test 3: Partial missing dates excluded from on-time calculation ────────────
@pytest.mark.asyncio
async def test_partial_missing_dates_excluded_from_on_time_calculation():
    """3. Sadece hem vaat edilen hem de fiilî teslim tarihi olan siparişler dahil edilmeli."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        # 1. Eksiksiz: 10 Ekim vaat, 10 Ekim teslim (0 gün gecikme -> zamanında)
        po_valid = PurchaseOrder(
            po_number=f"PO-VALID-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            expected_delivery_date=date(2026, 10, 10),
            actual_delivery_date=date(2026, 10, 10),
        )
        # 2. Vaat edilen tarih eksik
        po_missing_expected = PurchaseOrder(
            po_number=f"PO-NOEXP-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            expected_delivery_date=None,
            actual_delivery_date=date(2026, 10, 10),
        )
        # 3. Fiilî tarih eksik
        po_missing_actual = PurchaseOrder(
            po_number=f"PO-NOACT-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            expected_delivery_date=date(2026, 10, 10),
            actual_delivery_date=None,
        )
        session.add_all([po_valid, po_missing_expected, po_missing_actual])
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        assert perf.order_summary.completed_orders_count == 3
        # Yalnızca 1 sipariş uygun
        assert perf.delivery_reliability.is_available is True
        assert perf.delivery_reliability.eligible_orders_count == 1
        assert perf.delivery_reliability.on_time_orders_count == 1
        assert perf.delivery_reliability.on_time_percentage == 100.0
        assert perf.delivery_reliability.average_delay_days == 0.0
        # Tek sipariş olduğu için yetersiz güven
        assert perf.delivery_reliability.confidence == "insufficient"


# ── Test 4: Delivery early, on-time, late calculations ─────────────────────────
@pytest.mark.asyncio
async def test_delivery_early_on_time_late_calculations():
    """4. Erken (negatif delay) zamanında sayılmalı; tam gün ve geç teslimatlar doğru hesaplanmalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        # 1. Erken teslimat: 3 gün erken (delay = -3 <= 0 -> on-time)
        po1 = PurchaseOrder(
            po_number=f"PO-EARLY-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            expected_delivery_date=date(2026, 10, 10),
            actual_delivery_date=date(2026, 10, 7),
        )
        # 2. Tam gününde: 0 gün (delay = 0 <= 0 -> on-time)
        po2 = PurchaseOrder(
            po_number=f"PO-ONTIME-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            expected_delivery_date=date(2026, 10, 10),
            actual_delivery_date=date(2026, 10, 10),
        )
        # 3. Geç teslimat: 4 gün geç (delay = 4 > 0 -> late)
        po3 = PurchaseOrder(
            po_number=f"PO-LATE1-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            expected_delivery_date=date(2026, 10, 10),
            actual_delivery_date=date(2026, 10, 14),
        )
        # 4. Geç teslimat: 5 gün geç (delay = 5 > 0 -> late)
        po4 = PurchaseOrder(
            po_number=f"PO-LATE2-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            expected_delivery_date=date(2026, 10, 10),
            actual_delivery_date=date(2026, 10, 15),
        )
        session.add_all([po1, po2, po3, po4])
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        rel = perf.delivery_reliability
        assert rel.eligible_orders_count == 4
        assert rel.early_orders_count == 1
        assert rel.on_time_orders_count == 2  # 1 early + 1 on-time
        assert rel.late_orders_count == 2
        assert rel.on_time_percentage == 50.0  # (2 / 4) * 100
        # Ortalama gecikme: (-3 + 0 + 4 + 5) / 4 = 6 / 4 = 1.50 gün
        assert rel.average_delay_days == 1.50
        assert rel.confidence == "low"  # 4 sipariş -> low

        # Subset, karşılıklı ayrışıklık (mutual exclusivity) ve açıklama metni tutarlılığı:
        assert rel.on_time_orders_count + rel.late_orders_count == rel.eligible_orders_count
        assert rel.early_orders_count <= rel.on_time_orders_count
        exact_on_time = rel.on_time_orders_count - rel.early_orders_count
        assert exact_on_time == 1
        assert rel.early_orders_count + exact_on_time + rel.late_orders_count == rel.eligible_orders_count
        assert f"{rel.early_orders_count} erken" in rel.notes
        assert f"{exact_on_time} tam gününde" in rel.notes
        assert f"{rel.late_orders_count} gecikmeli" in rel.notes


# ── Test 5: Order status counts ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_order_status_counts():
    """5. Sipariş durumları (completed, delivered, cancelled, active/issued, draft) ayrıştırılmalı; taslak hariç tutulmalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        po_completed = PurchaseOrder(
            po_number=f"PO-C-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
        )
        po_delivered = PurchaseOrder(
            po_number=f"PO-D-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.DELIVERED.value,
        )
        po_cancelled = PurchaseOrder(
            po_number=f"PO-X-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.CANCELLED.value,
        )
        po_issued = PurchaseOrder(
            po_number=f"PO-I-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.ISSUED.value,
        )
        po_draft = PurchaseOrder(
            po_number=f"PO-DF-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.DRAFT.value,
        )
        session.add_all([po_completed, po_delivered, po_cancelled, po_issued, po_draft])
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        summary = perf.order_summary
        assert summary.completed_orders_count == 1
        assert summary.delivered_orders_count == 1
        assert summary.cancelled_orders_count == 1
        assert summary.active_orders_count == 1
        assert summary.draft_orders_count == 1
        # Karşılıklı ayrışık tüm durumların toplamı total_orders_count'a tam eşit olmalıdır: 1+1+1+1+1 = 5
        assert summary.total_orders_count == 5
        assert (
            summary.completed_orders_count
            + summary.delivered_orders_count
            + summary.cancelled_orders_count
            + summary.active_orders_count
            + summary.draft_orders_count
            == summary.total_orders_count
        )
        # Değerlendirilen (taslak hariç) sipariş sayısı: 5 - 1 = 4
        assert perf.evaluated_orders_count == 4


# ── Test 6: Insufficient sample size (< 2) qualification ──────────────────────
@pytest.mark.asyncio
async def test_insufficient_sample_size_qualification():
    """6. Tek siparişi olan tedarikçi niteleme olmaksızın '100% güvenilir' olarak görünmemeli."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        po = PurchaseOrder(
            po_number=f"PO-SINGLE-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            expected_delivery_date=date(2026, 10, 10),
            actual_delivery_date=date(2026, 10, 10),
        )
        session.add(po)
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        assert perf.evaluated_orders_count == 1
        assert perf.confidence_level == "insufficient"
        assert perf.delivery_reliability.confidence == "insufficient"
        assert "yetersiz" in perf.delivery_reliability.notes.lower()


# ── Test 7: Multi-currency separation ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_multi_currency_strict_isolation():
    """7. Farklı para birimleri (TRY ve USD) kesinlikle toplanmamalı; bağımsız havuzlar olarak raporlanmalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, _, approval = await create_base_test_data(session)

        # TRY Teklifi ve PO'su (10,000 TRY)
        q_try = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="TRY",
            subtotal=Decimal("10000.00"),
            total_price=Decimal("12000.00"),
        )
        session.add(q_try)
        await session.flush()

        po_try = PurchaseOrder(
            po_number=f"PO-TRY-{uuid.uuid4().hex[:6]}",
            quote_id=q_try.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            final_amount=Decimal("12000.00"),
        )

        # USD Teklifi ve PO'su (5,000 USD)
        q_usd = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="USD",
            subtotal=Decimal("5000.00"),
            total_price=Decimal("5000.00"),
        )
        session.add(q_usd)
        await session.flush()

        po_usd = PurchaseOrder(
            po_number=f"PO-USD-{uuid.uuid4().hex[:6]}",
            quote_id=q_usd.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            final_amount=Decimal("5000.00"),
        )

        session.add_all([po_try, po_usd])
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        assert "TRY" in perf.financial_summary
        assert "USD" in perf.financial_summary

        try_summary = perf.financial_summary["TRY"]
        assert try_summary.currency == "TRY"
        assert try_summary.total_spend == Decimal("12000.00")
        assert try_summary.orders_count == 1

        usd_summary = perf.financial_summary["USD"]
        assert usd_summary.currency == "USD"
        assert usd_summary.total_spend == Decimal("5000.00")
        assert usd_summary.orders_count == 1


# ── Test 8: Quote amount vs final PO amount ───────────────────────────────────
@pytest.mark.asyncio
async def test_quote_amount_vs_final_po_amount():
    """8. Kesinleşmiş final_amount ile teklif edilen quoted amount ayrıştırılmalı ve provenance kaydedilmeli."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        # 1. PO: Fatura kesinleşti (teklif 96,000 ama fatura 94,000)
        po_final = PurchaseOrder(
            po_number=f"PO-FNL-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            final_amount=Decimal("94000.00"),
        )
        # 2. PO: Fatura henüz kesinleşmedi (teklif 96,000 kullanıldı)
        po_quoted = PurchaseOrder(
            po_number=f"PO-QTD-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.ISSUED.value,
            final_amount=None,
        )
        session.add_all([po_final, po_quoted])
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        try_sum = perf.financial_summary["TRY"]
        assert try_sum.orders_count == 2
        assert try_sum.final_amount_orders_count == 1
        assert try_sum.quoted_amount_orders_count == 1
        # Toplam: 94000 + 96000 = 190000
        assert try_sum.total_spend == Decimal("190000.00")
        assert try_sum.average_order_value == Decimal("95000.00")
        assert try_sum.min_order_value == Decimal("94000.00")
        assert try_sum.max_order_value == Decimal("96000.00")


# ── Test 9: Missing quality data not assumed zero ─────────────────────────────
@pytest.mark.asyncio
async def test_missing_quality_data_not_assumed_zero():
    """9. Kalite verisi kaydedilmemiş tedarikçiler için 0 hata varsayımı yapılmamalı; is_tracked=False dönmeli."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        po = PurchaseOrder(
            po_number=f"PO-NOQL-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
        )
        session.add(po)
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        # Kalite takibi yapılmadığı açıkça raporlanmalı
        assert perf.quality_metrics.is_tracked is False
        assert perf.quality_metrics.tracked_orders_count == 0
        assert perf.quality_metrics.total_quality_issues is None
        assert perf.quality_metrics.total_rejections is None

        # Şimdi bağlı bir kalite kaydı ekleyelim
        hist = SupplierHistory(
            supplier_id=supplier.id,
            purchase_order_id=po.id,
            order_reference=po.po_number,
            order_date=date.today(),
            total_amount=Decimal("96000.00"),
            currency="TRY",
            quantity_ordered=10,
            quality_issues=2,
            rejection_count=1,
        )
        session.add(hist)
        await session.commit()

        perf_with_quality = await service.get_supplier_performance(supplier)
        assert perf_with_quality.quality_metrics.is_tracked is True
        assert perf_with_quality.quality_metrics.tracked_orders_count == 1
        assert perf_with_quality.quality_metrics.total_quality_issues == 2
        assert perf_with_quality.quality_metrics.total_rejections == 1


# ── Test 10: Deduplication & provenance ───────────────────────────────────────
@pytest.mark.asyncio
async def test_deduplication_and_provenance():
    """10. Canlı PO ve harici geçmiş kayıtları çift sayılmamalı; unlinked çakışmalar bayraklanmalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        # 1. Canlı platform siparişi
        po = PurchaseOrder(
            po_number=f"PO-COLL-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            expected_delivery_date=date(2026, 10, 10),
            actual_delivery_date=date(2026, 10, 10),
            final_amount=Decimal("50000.00"),
        )
        session.add(po)
        await session.commit()
        await session.refresh(po)

        # 2. Canlı PO'ya bağlı history (aynı sipariş - çift sayılmamalı)
        sh_linked = SupplierHistory(
            supplier_id=supplier.id,
            purchase_order_id=po.id,
            order_reference=po.po_number,
            order_date=date.today(),
            total_amount=Decimal("50000.00"),
            currency="TRY",
            quantity_ordered=10,
            quality_issues=0,
            rejection_count=0,
        )
        # 3. Bağlı olmayan ama aynı PO numarasına sahip çakışan harici kayıt
        sh_colliding = SupplierHistory(
            supplier_id=supplier.id,
            purchase_order_id=None,
            order_reference=po.po_number,  # Aynı referans!
            order_date=date(2026, 9, 1),
            total_amount=Decimal("50000.00"),
            currency="TRY",
            quantity_ordered=10,
        )
        # 4. Tamamen bağımsız harici ERP kaydı
        sh_external = SupplierHistory(
            supplier_id=supplier.id,
            purchase_order_id=None,
            order_reference="ERP-LEGACY-0099",
            order_date=date(2026, 8, 1),
            promised_date=date(2026, 8, 15),
            delivered_date=date(2026, 8, 14),
            delay_days=-1,
            total_amount=Decimal("30000.00"),
            currency="TRY",
            quantity_ordered=5,
        )
        session.add_all([sh_linked, sh_colliding, sh_external])
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        # Çakışma tespit edilmeli
        assert perf.has_conflicts is True
        assert perf.conflict_notes is not None
        assert po.po_number in perf.conflict_notes

        # Çift sayım önlenmeli: 1 canlı PO + 1 bağımsız ERP = 2 sipariş (çakışan hariç)
        assert perf.order_summary.completed_orders_count == 2
        assert perf.evaluated_orders_count == 2

        # Finansal toplam: 50,000 (canlı PO) + 30,000 (harici ERP) = 80,000 TRY
        assert perf.financial_summary["TRY"].total_spend == Decimal("80000.00")
        assert perf.financial_summary["TRY"].orders_count == 2


# ── Test 11: Cross-tenant access returns 404 via HTTP ─────────────────────────
@pytest.mark.asyncio
async def test_cross_tenant_access_returns_404():
    """11. Farklı organizasyona ait tedarikçiye erişim 404 dönmeli (bilgi sızdırılmamalı)."""
    async with AsyncSessionLocal() as session:
        # Org 1 (varsayılan auth org)
        org1, sup1, _, _, _ = await create_base_test_data(session)

        # Org 2 ve Tedarikçisi
        unique_suffix = uuid.uuid4().hex[:8]
        org2 = Organization(name=f"Foreign Org {unique_suffix}", slug=f"foreign-{unique_suffix}")
        session.add(org2)
        await session.flush()

        sup2 = Supplier(name=f"Foreign Supplier {unique_suffix}", organization_id=org2.id)
        session.add(sup2)
        await session.commit()
        await session.refresh(sup2)

        foreign_sup_id = sup2.id
        foreign_org_id = org2.id

    auth1 = await create_test_auth_context(role=UserRole.ADMIN, org_id=org1.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Varsayılan kullanıcı (Org 1) yabancı organizasyonun tedarikçisini sorguluyor
        res_perf = await client.get(f"/api/v1/suppliers/{foreign_sup_id}/performance", headers=auth1.headers)
        assert res_perf.status_code == 404
        assert "bulunamadı" in res_perf.json()["detail"]

        # 2. Query param ile yabancı organization_id gönderilerek bypass deneniyor
        res_perf_param = await client.get(
            f"/api/v1/suppliers/{foreign_sup_id}/performance?organization_id={foreign_org_id}",
            headers=auth1.headers,
        )
        assert res_perf_param.status_code == 404

        # 3. History endpoint için de 404 dönmeli
        res_hist = await client.get(f"/api/v1/suppliers/{foreign_sup_id}/history", headers=auth1.headers)
        assert res_hist.status_code == 404

        # 4. Olmayan UUID için de 404 dönmeli
        fake_id = uuid.uuid4()
        res_fake = await client.get(f"/api/v1/suppliers/{fake_id}/performance", headers=auth1.headers)
        assert res_fake.status_code == 404


# ── Test 12: Pagination boundaries and sorting in History API ──────────────────
@pytest.mark.asyncio
async def test_pagination_boundaries_and_sorting_in_history_api():
    """12. Tedarikçi geçmiş siparişleri sayfalanmalı, limit kontrolleri yapılmalı ve tarihe göre azalan sıralanmalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, _, _, _ = await create_base_test_data(session)

        # 5 adet harici sipariş kaydı (farklı tarihlerde)
        for i in range(5):
            hist = SupplierHistory(
                supplier_id=supplier.id,
                order_reference=f"ORD-PAGE-{i}",
                order_date=date(2026, 1, 1) + timedelta(days=i * 10),
                total_amount=Decimal("10000.00") + Decimal(i * 1000),
                currency="TRY",
                quantity_ordered=5,
            )
            session.add(hist)
        await session.commit()

    auth = await create_test_auth_context(role=UserRole.ADMIN, org_id=org.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sayfa 1 (page_size = 2) -> 2 kayıt dönmeli, total_count = 5, total_pages = 3
        res_p1 = await client.get(f"/api/v1/suppliers/{supplier.id}/history?page=1&page_size=2", headers=auth.headers)
        assert res_p1.status_code == 200
        data_p1 = res_p1.json()
        assert data_p1["total_count"] == 5
        assert data_p1["total_pages"] == 3
        assert data_p1["page"] == 1
        assert data_p1["page_size"] == 2
        assert len(data_p1["items"]) == 2

        # Sıralama: En yeni sipariş en başta olmalı (i=4 yani 2026-02-10)
        assert data_p1["items"][0]["order_reference"] == "ORD-PAGE-4"
        assert data_p1["items"][1]["order_reference"] == "ORD-PAGE-3"

        # 2. Sayfa 3 (page_size = 2) -> Son 1 kayıt dönmeli
        res_p3 = await client.get(f"/api/v1/suppliers/{supplier.id}/history?page=3&page_size=2", headers=auth.headers)
        assert res_p3.status_code == 200
        data_p3 = res_p3.json()
        assert len(data_p3["items"]) == 1
        assert data_p3["items"][0]["order_reference"] == "ORD-PAGE-0"

        # 3. Sayfa 4 (sınır aşımı) -> 0 kayıt, total_pages = 3
        res_p4 = await client.get(f"/api/v1/suppliers/{supplier.id}/history?page=4&page_size=2", headers=auth.headers)
        assert res_p4.status_code == 200
        data_p4 = res_p4.json()
        assert len(data_p4["items"]) == 0
        assert data_p4["total_pages"] == 3

        # 4. Geçersiz sayfalama parametreleri (FastAPI 422 Unprocessable Entity)
        res_invalid_page = await client.get(f"/api/v1/suppliers/{supplier.id}/history?page=0", headers=auth.headers)
        assert res_invalid_page.status_code == 422

        res_invalid_size = await client.get(f"/api/v1/suppliers/{supplier.id}/history?page_size=101", headers=auth.headers)
        assert res_invalid_size.status_code == 422


# ── Test 13: Cancelled and draft orders excluded from financial metrics ────────
@pytest.mark.asyncio
async def test_cancelled_and_draft_orders_excluded_from_financial_summary_and_mixed_provenance():
    """13. İptal edilmiş ve taslak siparişler finansal harcamaya dahil edilmemeli; karma provenance doğrulanmalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        # 1. Tamamlanmış Canlı PO: Fatura kesinleşti (50,000 TRY) -> DAHİL (final_po_amount)
        po_completed = PurchaseOrder(
            po_number=f"PO-COMP-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.COMPLETED.value,
            final_amount=Decimal("50000.00"),
        )
        # 2. Aktif/Issued Canlı PO: Fatura henüz yok, teklif tutarı kullanıldı (30,000 TRY) -> DAHİL (quoted_amount)
        q_active = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="TRY",
            subtotal=Decimal("25000.00"),
            total_price=Decimal("30000.00"),
        )
        session.add(q_active)
        await session.flush()

        po_issued = PurchaseOrder(
            po_number=f"PO-ACT-{uuid.uuid4().hex[:6]}",
            quote_id=q_active.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.ISSUED.value,
            final_amount=None,
        )
        # 3. Harici Geçmiş Kaydı: ERP'den aktarılan teslimat (20,000 TRY) -> DAHİL (historical_amount)
        sh_legacy = SupplierHistory(
            supplier_id=supplier.id,
            order_reference="ERP-HIST-2025-01",
            order_date=date(2025, 6, 1),
            delivered_date=date(2025, 6, 10),
            total_amount=Decimal("20000.00"),
            currency="TRY",
            quantity_ordered=10,
        )

        # 4. İptal Edilmiş Canlı PO (100,000 TRY) -> HARCAMAYA DAHİL EDİLMEMELİ!
        q_cancel = Quote(
            rfq_id=rfq.id,
            supplier_id=supplier.id,
            currency="TRY",
            subtotal=Decimal("80000.00"),
            total_price=Decimal("100000.00"),
        )
        session.add(q_cancel)
        await session.flush()

        po_cancelled = PurchaseOrder(
            po_number=f"PO-CANC-{uuid.uuid4().hex[:6]}",
            quote_id=q_cancel.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.CANCELLED.value,
            final_amount=Decimal("95000.00"),
            cancellation_reason="Tedarikçi teslim edemedi",
        )

        # 5. İptal Edilmiş Harici Kayıt (Fire/Ret nedeniyle: 40,000 TRY) -> HARCAMAYA DAHİL EDİLMEMELİ!
        sh_cancelled_rej = SupplierHistory(
            supplier_id=supplier.id,
            order_reference="ERP-HIST-REJ-01",
            order_date=date(2025, 7, 1),
            total_amount=Decimal("40000.00"),
            currency="TRY",
            quantity_ordered=5,
            quantity_received=0,
            rejection_count=5,
        )

        # 6. Notunda İptal Belirtilen Harici Kayıt (25,000 TRY) -> HARCAMAYA DAHİL EDİLMEMELİ!
        sh_cancelled_note = SupplierHistory(
            supplier_id=supplier.id,
            order_reference="ERP-HIST-NOTE-01",
            order_date=date(2025, 8, 1),
            total_amount=Decimal("25000.00"),
            currency="TRY",
            quantity_ordered=5,
            notes="Sipariş alıcı tarafından iptal edildi.",
        )

        # 7. Taslak Canlı PO (15,000 TRY) -> HARCAMAYA DAHİL EDİLMEMELİ!
        po_draft = PurchaseOrder(
            po_number=f"PO-DRF-{uuid.uuid4().hex[:6]}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.DRAFT.value,
        )

        session.add_all([
            po_completed,
            po_issued,
            sh_legacy,
            po_cancelled,
            sh_cancelled_rej,
            sh_cancelled_note,
            po_draft,
        ])
        await session.commit()

        service = SupplierPerformanceService(db=session)
        perf = await service.get_supplier_performance(supplier)

        # ── Finansal Doğrulamalar ──
        assert "TRY" in perf.financial_summary
        try_sum = perf.financial_summary["TRY"]

        # Yalnızca 3 geçerli sipariş dahil edilmeli (50,000 + 30,000 + 20,000 = 100,000 TRY)
        assert try_sum.orders_count == 3
        assert try_sum.total_spend == Decimal("100000.00")
        assert try_sum.average_order_value == Decimal("33333.33")
        assert try_sum.min_order_value == Decimal("20000.00")
        assert try_sum.max_order_value == Decimal("50000.00")

        # Provenance ayrımı
        assert try_sum.final_amount_orders_count == 1
        assert try_sum.quoted_amount_orders_count == 1
        assert try_sum.historical_amount_orders_count == 1

        # ── Sipariş Durumu Sayımları ve Mutually Exclusive Toplam ──
        summary = perf.order_summary
        assert summary.completed_orders_count == 2  # 1 PO + 1 legacy
        assert summary.active_orders_count == 1     # 1 issued PO
        assert summary.cancelled_orders_count == 3  # 1 PO + 2 legacy
        assert summary.draft_orders_count == 1      # 1 draft PO
        assert summary.delivered_orders_count == 0

        # Tüm durumların toplamı total_orders_count'a tam eşit olmalıdır: 2 + 1 + 3 + 1 + 0 = 7
        assert summary.total_orders_count == 7
        assert (
            summary.completed_orders_count
            + summary.delivered_orders_count
            + summary.cancelled_orders_count
            + summary.active_orders_count
            + summary.draft_orders_count
            == summary.total_orders_count
        )

        # Değerlendirilen siparişler (taslak hariç): 7 - 1 = 6
        assert perf.evaluated_orders_count == 6

