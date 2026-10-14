import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.supplier import Supplier, SupplierHistory
from app.models.rfq import RFQ, RFQStatus
from app.models.quote import Quote
from app.models.analysis import Analysis, AnalysisStatus, Approval, ApprovalStatus
from app.models.order import PurchaseOrder, PurchaseOrderStatus
from app.services.workflow.order import PurchaseOrderService


async def create_base_test_data(session):
    unique_suffix = uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Foundation Org {unique_suffix}",
        slug=f"foundation-org-{unique_suffix}"
    )
    session.add(org)
    await session.flush()

    supplier = Supplier(
        name=f"Supplier Test {unique_suffix}",
        organization_id=org.id
    )
    session.add(supplier)
    await session.flush()

    rfq = RFQ(
        organization_id=org.id,
        title="Delivery Foundation RFQ",
        budget=Decimal("100000.00"),
        status=RFQStatus.PENDING_APPROVAL.value,
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


# ── Test 1: PurchaseOrder schema and nullable delivery fields ─────────────────
@pytest.mark.asyncio
async def test_purchase_order_delivery_fields_nullable_by_default():
    """1. PurchaseOrder delivery alanları varsayılan olarak nullable olmalı ve geriye dönük uyumlu çalışmalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        po = PurchaseOrder(
            po_number=f"PO-TEST-{uuid.uuid4().hex[:6].upper()}",
            quote_id=quote.id,
            approval_id=approval.id,
            status=PurchaseOrderStatus.ISSUED.value,
        )
        session.add(po)
        await session.commit()
        await session.refresh(po)

        # Doğrulama: Yeni alanlar None olarak başlar, hiçbir çıkarım yapılmaz
        assert po.expected_delivery_date is None
        assert po.actual_delivery_date is None
        assert po.delivered_at is None
        assert po.final_amount is None
        assert po.delivery_notes is None
        assert po.status == "issued"


# ── Test 2: PO creation from approval computes expected_delivery_date ─────────
@pytest.mark.asyncio
async def test_po_creation_computes_expected_delivery_date_from_quote():
    """2. PO oluşturulduğunda quote.delivery_days ve approval.reviewed_at üzerinden expected_delivery_date hesaplanmalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        # PurchaseOrderService üzerinden PO üret
        po = await PurchaseOrderService.create_po_from_approval(session, approval)
        await session.commit()
        await session.refresh(po)

        # Beklenen teslimat tarihi: approval tarihi (bugün) + 14 gün
        expected_date = approval.reviewed_at.date() + timedelta(days=14)
        assert po.expected_delivery_date == expected_date

        # Fiilî teslimat alanları ASLA otomatik doldurulmaz (çıkarım yapılmaz)
        assert po.actual_delivery_date is None
        assert po.delivered_at is None
        assert po.final_amount is None


# ── Test 3: SupplierHistory linkage and ON DELETE SET NULL ────────────────────
@pytest.mark.asyncio
async def test_supplier_history_purchase_order_id_linkage_and_set_null():
    """3. SupplierHistory.purchase_order_id ilişkisi kurulabilmeli ve PO silindiğinde SET NULL çalışmalı."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        po = await PurchaseOrderService.create_po_from_approval(session, approval)
        await session.commit()
        await session.refresh(po)

        # SupplierHistory kaydına bu PO'yu bağla
        history_record = SupplierHistory(
            supplier_id=supplier.id,
            purchase_order_id=po.id,
            order_reference=po.po_number,
            order_date=date.today(),
            promised_date=po.expected_delivery_date,
            total_amount=Decimal("96000.00"),
            currency="TRY",
            quantity_ordered=10,
        )
        session.add(history_record)
        await session.commit()
        await session.refresh(history_record)

        assert history_record.purchase_order_id == po.id
        assert history_record.purchase_order.po_number == po.po_number

        # PO silindiğinde (ör. test temizliği veya istisnai durum), SET NULL çalışmalı
        await session.delete(po)
        await session.commit()

        # History kaydı silinmemeli, sadece purchase_order_id None olmalı
        await session.refresh(history_record)
        assert history_record.purchase_order_id is None
        assert history_record.order_reference is not None


# ── Test 4: Deduplication safety between live PO and legacy SupplierHistory ───
@pytest.mark.asyncio
async def test_supplier_history_deduplication_safety():
    """4. purchase_order_id alanı ile canlı PO'lar ve harici legacy geçmiş kayıtları tekilleştirilebilmeli."""
    async with AsyncSessionLocal() as session:
        org, supplier, rfq, quote, approval = await create_base_test_data(session)

        # 1. Harici legacy ERP kaydı (purchase_order_id = None)
        legacy_rec = SupplierHistory(
            supplier_id=supplier.id,
            purchase_order_id=None,
            order_reference="ERP-LEGACY-2023-01",
            order_date=date(2023, 5, 10),
            promised_date=date(2023, 5, 20),
            delivered_date=date(2023, 5, 19),
            total_amount=Decimal("45000.00"),
            currency="TRY",
            quantity_ordered=5,
            delay_days=-1,
        )
        session.add(legacy_rec)

        # 2. Canlı platform siparişi
        po = await PurchaseOrderService.create_po_from_approval(session, approval)
        session.add(po)
        await session.commit()
        await session.refresh(po)

        # Canlı sipariş için history kaydı oluşturulduğunda purchase_order_id atanır
        platform_rec = SupplierHistory(
            supplier_id=supplier.id,
            purchase_order_id=po.id,
            order_reference=po.po_number,
            order_date=date.today(),
            promised_date=po.expected_delivery_date,
            total_amount=Decimal("96000.00"),
            currency="TRY",
            quantity_ordered=10,
        )
        session.add(platform_rec)
        await session.commit()

        # Doğrulama: Harici kayıtlar `purchase_order_id IS NULL` filtresiyle,
        # canlı kayıtlar ise `purchase_order_id IS NOT NULL` ile çift sayım olmaksızın ayrıştırılabilir.
        all_hist = (await session.execute(
            select(SupplierHistory).where(SupplierHistory.supplier_id == supplier.id)
        )).scalars().all()
        assert len(all_hist) == 2

        legacy_only = [h for h in all_hist if h.purchase_order_id is None]
        assert len(legacy_only) == 1
        assert legacy_only[0].order_reference == "ERP-LEGACY-2023-01"

        po_linked = [h for h in all_hist if h.purchase_order_id is not None]
        assert len(po_linked) == 1
        assert po_linked[0].purchase_order_id == po.id


# ── Test 5: Status lifecycle definitions & compatibility ──────────────────────
def test_purchase_order_status_lifecycle_values():
    """5. PurchaseOrderStatus enum değerleri mevcut string sözleşmeleriyle tam uyumlu olmalı."""
    assert PurchaseOrderStatus.DRAFT.value == "draft"
    assert PurchaseOrderStatus.ISSUED.value == "issued"
    assert PurchaseOrderStatus.DELIVERED.value == "delivered"
    assert PurchaseOrderStatus.COMPLETED.value == "completed"
    assert PurchaseOrderStatus.CANCELLED.value == "cancelled"
