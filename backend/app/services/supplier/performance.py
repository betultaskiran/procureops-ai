import math
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import PurchaseOrder, PurchaseOrderStatus
from app.models.quote import Quote
from app.models.rfq import RFQ
from app.models.supplier import Supplier, SupplierHistory
from app.services.supplier.schemas import (
    CurrencyFinancialSummary,
    DeliveryReliability,
    OrderSummary,
    PaginatedSupplierHistoryResponse,
    QualityMetrics,
    SupplierHistoryItemResponse,
    SupplierPerformanceResponse,
)


class SupplierPerformanceService:
    """
    Tedarikçi performans analizi ve geçmiş sipariş birleştirme servisi.

    Temel İlkeler:
    1. Kesin Veri Tabanı Kayıtları: Asla yapay veya uydurma 0% / 100% üretilmez.
    2. Çift Sayımı Önleme (Deduplication): Canlı PO'lar ile SupplierHistory kayıtları
       purchase_order_id üzerinden tekilleştirilir. Referans çakışmaları (unlinked collision)
       bayraklanır ve metriklerde PO verisi yetkili kaynak kabul edilir.
    3. Para Birimi İzolasyonu: Farklı para birimleri (TRY, USD, EUR vb.) asla birbirine
       eklenmez; bağımsız finansal özet havuzları olarak raporlanır.
    4. İcra & Kalite Kanıtı: Nihai PO fatura tutarı ile teklif tutarı ayrıştırılır;
       kalite verisi bulunmayan tedarikçiler için 0 hata varsayımı yapılmaz, 'is_tracked=False' döner.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _fetch_records(
        self, supplier: Supplier
    ) -> tuple[list[PurchaseOrder], list[SupplierHistory]]:
        """
        Tedarikçiye ve ilgili organizasyona ait canlı PO ve geçmiş kayıtlarını çeker.
        """
        # 1. Platform Purchase Orders (RFQ organizasyonuna ve Supplier'a bağlı)
        po_query = (
            select(PurchaseOrder)
            .join(PurchaseOrder.quote)
            .join(Quote.rfq)
            .where(
                Quote.supplier_id == supplier.id,
                RFQ.organization_id == supplier.organization_id,
            )
            .options(
                selectinload(PurchaseOrder.quote),
                selectinload(PurchaseOrder.supplier_history_entry),
            )
        )
        po_res = await self.db.execute(po_query)
        pos = list(po_res.scalars().all())

        # 2. Supplier History kayıtları
        hist_query = (
            select(SupplierHistory)
            .where(SupplierHistory.supplier_id == supplier.id)
            .order_by(SupplierHistory.order_date.desc(), SupplierHistory.created_at.desc())
        )
        hist_res = await self.db.execute(hist_query)
        histories = list(hist_res.scalars().all())

        return pos, histories

    def _partition_records(
        self, pos: list[PurchaseOrder], histories: list[SupplierHistory]
    ) -> tuple[
        dict[uuid.UUID, SupplierHistory],
        list[SupplierHistory],
        list[SupplierHistory],
    ]:
        """
        SupplierHistory kayıtlarını:
        - Canlı PO'ya bağlı olanlar (linked_histories)
        - Bağlı olmayıp PO numarası ile çakışanlar (colliding_histories)
        - Bağımsız harici kayıtlar (external_histories)
        olarak ayrıştırır.
        """
        po_map = {po.id: po for po in pos}
        po_numbers = {po.po_number: po for po in pos if po.po_number}

        linked_histories: dict[uuid.UUID, SupplierHistory] = {}
        colliding_histories: list[SupplierHistory] = []
        external_histories: list[SupplierHistory] = []

        for sh in histories:
            if sh.purchase_order_id and sh.purchase_order_id in po_map:
                linked_histories[sh.purchase_order_id] = sh
            elif sh.purchase_order_id is None and sh.order_reference and sh.order_reference in po_numbers:
                colliding_histories.append(sh)
            else:
                external_histories.append(sh)

        return linked_histories, colliding_histories, external_histories

    async def get_supplier_performance(self, supplier: Supplier) -> SupplierPerformanceResponse:
        """
        Tedarikçinin geçmiş kayıtlarını analiz ederek performans özetini üretir.
        """
        pos, histories = await self._fetch_records(supplier)
        linked_histories, colliding_histories, external_histories = self._partition_records(pos, histories)

        # ── 1. Sipariş Durum Sayımları ──────────────────────────────────────────
        completed_count = 0
        delivered_count = 0
        cancelled_count = 0
        active_count = 0
        draft_count = 0

        # Canlı PO'lar
        for po in pos:
            if po.status == PurchaseOrderStatus.COMPLETED.value:
                completed_count += 1
            elif po.status == PurchaseOrderStatus.DELIVERED.value:
                delivered_count += 1
            elif po.status == PurchaseOrderStatus.CANCELLED.value:
                cancelled_count += 1
            elif po.status == PurchaseOrderStatus.ISSUED.value:
                active_count += 1
            elif po.status == PurchaseOrderStatus.DRAFT.value:
                draft_count += 1

        # Harici kayıtlar (colliding olmayanlar çift sayımı önlemek için)
        for sh in external_histories:
            is_cancelled = (
                (sh.rejection_count > 0 and (sh.quantity_received == 0 or (sh.quantity_ordered > 0 and sh.rejection_count >= sh.quantity_ordered)))
                or (sh.notes is not None and any(term in sh.notes.lower() for term in ("iptal", "cancelled", "canceled")))
            )
            if is_cancelled:
                cancelled_count += 1
            elif sh.delivered_date is not None or sh.delay_days is not None:
                completed_count += 1
            else:
                active_count += 1

        evaluated_orders_count = completed_count + delivered_count + cancelled_count + active_count
        total_orders_count = evaluated_orders_count + draft_count

        order_summary = OrderSummary(
            total_orders_count=total_orders_count,
            completed_orders_count=completed_count,
            delivered_orders_count=delivered_count,
            cancelled_orders_count=cancelled_count,
            active_orders_count=active_count,
            draft_orders_count=draft_count,
        )

        # ── 2. Teslimat Güvenilirliği (Delivery Reliability) ───────────────────
        eligible_delays: list[int] = []

        # Canlı PO'lardan uygun olanlar (iptal veya taslak olmayan, her iki tarih dolu)
        for po in pos:
            if po.status in (PurchaseOrderStatus.CANCELLED.value, PurchaseOrderStatus.DRAFT.value):
                continue
            actual_date = po.actual_delivery_date or (po.delivered_at.date() if po.delivered_at else None)
            if po.expected_delivery_date is not None and actual_date is not None:
                delay = (actual_date - po.expected_delivery_date).days
                eligible_delays.append(delay)

        # Harici geçmiş kayıtlarından uygun olanlar
        for sh in external_histories:
            if sh.promised_date is not None and (sh.delivered_date is not None or sh.delay_days is not None):
                if sh.delay_days is not None:
                    delay = sh.delay_days
                else:
                    delay = (sh.delivered_date - sh.promised_date).days  # type: ignore[operator]
                eligible_delays.append(delay)

        eligible_count = len(eligible_delays)
        if eligible_count == 0:
            delivery_reliability = DeliveryReliability(
                is_available=False,
                confidence="insufficient",
                eligible_orders_count=0,
                on_time_orders_count=None,
                late_orders_count=None,
                early_orders_count=None,
                on_time_percentage=None,
                average_delay_days=None,
                notes="Teslimat performansını hesaplamak için yeterli teslimat tarihi verisi bulunmamaktadır.",
            )
        else:
            on_time_count = sum(1 for d in eligible_delays if d <= 0)
            early_count = sum(1 for d in eligible_delays if d < 0)
            late_count = sum(1 for d in eligible_delays if d > 0)
            on_time_pct = round((on_time_count / eligible_count) * 100.0, 2)
            avg_delay = round(sum(eligible_delays) / eligible_count, 2)

            if eligible_count < 2:
                conf = "insufficient"
                notes = (
                    f"Örneklem büyüklüğü yetersiz ({eligible_count} sipariş: "
                    f"{early_count} erken, {on_time_count - early_count} tam gününde, {late_count} gecikmeli). "
                    "Hesaplanan oran tek siparişe dayandığı için genellenemez."
                )
            elif eligible_count <= 4:
                conf = "low"
                notes = (
                    f"Sınırlı veri ({eligible_count} sipariş). "
                    f"{early_count} erken, {on_time_count - early_count} tam gününde, {late_count} gecikmeli."
                )
            else:
                conf = "high"
                notes = (
                    f"Güçlü veri temeli ({eligible_count} sipariş). "
                    f"{early_count} erken, {on_time_count - early_count} tam gününde, {late_count} gecikmeli."
                )

            delivery_reliability = DeliveryReliability(
                is_available=True,
                confidence=conf,
                eligible_orders_count=eligible_count,
                on_time_orders_count=on_time_count,
                late_orders_count=late_count,
                early_orders_count=early_count,
                on_time_percentage=on_time_pct,
                average_delay_days=avg_delay,
                notes=notes,
            )

        # ── 3. Finansal Özet (Financial Summary by Currency) ───────────────────
        # Para birimleri kesinlikle izole edilir; asla birbiriyle toplanmaz.
        currency_buckets: dict[str, dict] = {}

        # Canlı PO'lar (iptal ve taslak olmayanlar değerlendirilir)
        for po in pos:
            if po.status in (PurchaseOrderStatus.CANCELLED.value, PurchaseOrderStatus.DRAFT.value):
                continue
            curr = (po.quote.currency if po.quote and po.quote.currency else "TRY").strip().upper()
            if curr not in currency_buckets:
                currency_buckets[curr] = {
                    "amounts": [],
                    "final_count": 0,
                    "quoted_count": 0,
                    "historical_count": 0,
                }

            if po.final_amount is not None:
                currency_buckets[curr]["amounts"].append(Decimal(str(po.final_amount)))
                currency_buckets[curr]["final_count"] += 1
            else:
                quoted_amt = po.quote.total_price if po.quote else Decimal("0.00")
                currency_buckets[curr]["amounts"].append(Decimal(str(quoted_amt)))
                currency_buckets[curr]["quoted_count"] += 1

        # Harici kayıtlar
        for sh in external_histories:
            # İptal edilmiş harici kayıtlar finansal harcamaya dahil edilmez
            is_cancelled = (
                (sh.rejection_count > 0 and (sh.quantity_received == 0 or (sh.quantity_ordered > 0 and sh.rejection_count >= sh.quantity_ordered)))
                or (sh.notes is not None and any(term in sh.notes.lower() for term in ("iptal", "cancelled", "canceled")))
            )
            if is_cancelled:
                continue
            curr = (sh.currency or "TRY").strip().upper()
            if curr not in currency_buckets:
                currency_buckets[curr] = {
                    "amounts": [],
                    "final_count": 0,
                    "quoted_count": 0,
                    "historical_count": 0,
                }
            currency_buckets[curr]["amounts"].append(Decimal(str(sh.total_amount)))
            currency_buckets[curr]["historical_count"] += 1

        financial_summary: dict[str, CurrencyFinancialSummary] = {}
        for curr, data in currency_buckets.items():
            amounts = data["amounts"]
            if not amounts:
                continue
            total_spend = sum(amounts).quantize(Decimal("0.01"))
            avg_order = (total_spend / len(amounts)).quantize(Decimal("0.01"))
            min_order = min(amounts).quantize(Decimal("0.01"))
            max_order = max(amounts).quantize(Decimal("0.01"))

            financial_summary[curr] = CurrencyFinancialSummary(
                currency=curr,
                total_spend=total_spend,
                average_order_value=avg_order,
                min_order_value=min_order,
                max_order_value=max_order,
                orders_count=len(amounts),
                final_amount_orders_count=data["final_count"],
                quoted_amount_orders_count=data["quoted_count"],
                historical_amount_orders_count=data["historical_count"],
            )

        # ── 4. Kalite ve İade Metrikleri (Quality Metrics) ─────────────────────
        tracked_records_count = 0
        total_issues = 0
        total_rejections = 0

        # Canlı PO'lar ile bağlı SupplierHistory kayıtları
        for po in pos:
            sh = linked_histories.get(po.id) or po.supplier_history_entry
            if sh is not None:
                tracked_records_count += 1
                total_issues += sh.quality_issues
                total_rejections += sh.rejection_count

        # Harici kayıtlar
        for sh in external_histories:
            tracked_records_count += 1
            total_issues += sh.quality_issues
            total_rejections += sh.rejection_count

        if tracked_records_count == 0:
            quality_metrics = QualityMetrics(
                is_tracked=False,
                tracked_orders_count=0,
                total_quality_issues=None,
                total_rejections=None,
                notes="Bu tedarikçi için henüz kalite ve fire/iade takibi verisi kaydedilmemiştir.",
            )
        else:
            quality_metrics = QualityMetrics(
                is_tracked=True,
                tracked_orders_count=tracked_records_count,
                total_quality_issues=total_issues,
                total_rejections=total_rejections,
                notes=f"{tracked_records_count} sipariş üzerinden kalite takibi yapılmıştır.",
            )

        # ── 5. Genel Örneklem Büyüklüğü & İstatistiksel Güven ──────────────────
        if evaluated_orders_count < 2:
            confidence_level = "insufficient"
        elif evaluated_orders_count <= 4:
            confidence_level = "low"
        else:
            confidence_level = "high"

        # ── 6. Çakışma Kontrolü (Conflict Detection) ───────────────────────────
        has_conflicts = len(colliding_histories) > 0
        conflict_notes = None
        if has_conflicts:
            colliding_refs = [sh.order_reference for sh in colliding_histories if sh.order_reference]
            conflict_notes = (
                f"{len(colliding_histories)} adet harici geçmiş kaydında canlı PO referans çakışması tespit edildi "
                f"({', '.join(colliding_refs)}). Çift sayımı önlemek için canlı PO verileri yetkili kabul edildi."
            )

        return SupplierPerformanceResponse(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            organization_id=supplier.organization_id,
            order_summary=order_summary,
            delivery_reliability=delivery_reliability,
            financial_summary=financial_summary,
            quality_metrics=quality_metrics,
            evaluated_orders_count=evaluated_orders_count,
            confidence_level=confidence_level,
            has_conflicts=has_conflicts,
            conflict_notes=conflict_notes,
        )

    async def get_supplier_history(
        self,
        supplier: Supplier,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedSupplierHistoryResponse:
        """
        Tedarikçiye ait tüm geçmiş kayıtları birleştirilmiş, tekilleştirilmiş ve
        provenance (kaynak tipi ve tutar kökeni) belirterek sayfalanmış döner.
        """
        pos, histories = await self._fetch_records(supplier)
        linked_histories, colliding_histories, external_histories = self._partition_records(pos, histories)

        unified_items: list[SupplierHistoryItemResponse] = []

        # 1. Platform Purchase Orders
        for po in pos:
            sh = linked_histories.get(po.id) or po.supplier_history_entry
            actual_date = po.actual_delivery_date or (po.delivered_at.date() if po.delivered_at else None)
            delay = None
            if po.expected_delivery_date and actual_date:
                delay = (actual_date - po.expected_delivery_date).days

            if po.final_amount is not None:
                amt = Decimal(str(po.final_amount))
                amt_type = "final_po_amount"
            else:
                amt = Decimal(str(po.quote.total_price if po.quote else "0.00"))
                amt_type = "quoted_amount"

            currency = po.quote.currency if po.quote else "TRY"

            unified_items.append(
                SupplierHistoryItemResponse(
                    id=po.id,
                    source_type="purchase_order",
                    source_record_id=po.id,
                    order_reference=po.po_number,
                    order_date=po.created_at.date(),
                    expected_delivery_date=po.expected_delivery_date,
                    actual_delivery_date=actual_date,
                    delay_days=delay,
                    status=po.status,
                    amount=amt.quantize(Decimal("0.01")),
                    currency=currency,
                    amount_type=amt_type,
                    quality_issues=sh.quality_issues if sh else None,
                    rejection_count=sh.rejection_count if sh else None,
                    has_collision=False,
                    collision_note=None,
                    notes=po.delivery_notes or (sh.notes if sh else None),
                    created_at=po.created_at,
                )
            )

        # 2. Çakışan harici kayıtlar (Ayrı bir satır olarak listelenir, ancak has_collision=True)
        for sh in colliding_histories:
            delay = sh.delay_days
            if delay is None and sh.delivered_date and sh.promised_date:
                delay = (sh.delivered_date - sh.promised_date).days

            status = "completed" if (sh.delivered_date or sh.delay_days is not None) else "active"

            unified_items.append(
                SupplierHistoryItemResponse(
                    id=sh.id,
                    source_type="external_history",
                    source_record_id=sh.id,
                    order_reference=sh.order_reference or f"EXT-{str(sh.id)[:8]}",
                    order_date=sh.order_date,
                    expected_delivery_date=sh.promised_date,
                    actual_delivery_date=sh.delivered_date,
                    delay_days=delay,
                    status=status,
                    amount=Decimal(str(sh.total_amount)).quantize(Decimal("0.01")),
                    currency=sh.currency,
                    amount_type="historical_amount",
                    quality_issues=sh.quality_issues,
                    rejection_count=sh.rejection_count,
                    has_collision=True,
                    collision_note=f"Bu referans ({sh.order_reference}) canlı bir platform PO numarası ile çakışmaktadır ancak doğrudan bağlı değildir.",
                    notes=sh.notes,
                    created_at=sh.created_at,
                )
            )

        # 3. Bağımsız harici kayıtlar
        for sh in external_histories:
            delay = sh.delay_days
            if delay is None and sh.delivered_date and sh.promised_date:
                delay = (sh.delivered_date - sh.promised_date).days

            is_cancelled = (
                (sh.rejection_count > 0 and (sh.quantity_received == 0 or (sh.quantity_ordered > 0 and sh.rejection_count >= sh.quantity_ordered)))
                or (sh.notes is not None and any(term in sh.notes.lower() for term in ("iptal", "cancelled", "canceled")))
            )
            if is_cancelled:
                status = "cancelled"
            elif sh.delivered_date is not None or sh.delay_days is not None:
                status = "completed"
            else:
                status = "active"

            unified_items.append(
                SupplierHistoryItemResponse(
                    id=sh.id,
                    source_type="external_history",
                    source_record_id=sh.id,
                    order_reference=sh.order_reference or f"EXT-{str(sh.id)[:8]}",
                    order_date=sh.order_date,
                    expected_delivery_date=sh.promised_date,
                    actual_delivery_date=sh.delivered_date,
                    delay_days=delay,
                    status=status,
                    amount=Decimal(str(sh.total_amount)).quantize(Decimal("0.01")),
                    currency=sh.currency,
                    amount_type="historical_amount",
                    quality_issues=sh.quality_issues,
                    rejection_count=sh.rejection_count,
                    has_collision=False,
                    collision_note=None,
                    notes=sh.notes,
                    created_at=sh.created_at,
                )
            )

        # En yeni siparişten en eskiye doğru sıralama
        unified_items.sort(key=lambda x: (x.order_date, x.created_at), reverse=True)

        total_count = len(unified_items)
        effective_page = max(1, page)
        effective_page_size = max(1, min(100, page_size))
        total_pages = math.ceil(total_count / effective_page_size) if total_count > 0 else 0

        start_idx = (effective_page - 1) * effective_page_size
        end_idx = start_idx + effective_page_size
        paginated_items = unified_items[start_idx:end_idx]

        return PaginatedSupplierHistoryResponse(
            items=paginated_items,
            total_count=total_count,
            page=effective_page,
            page_size=effective_page_size,
            total_pages=total_pages,
        )
