import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.analysis import Approval
from app.models.order import PurchaseOrder

class PurchaseOrderService:
    """
    Onaylanmış işlemleri PO (Satın Alma Siparişi) kaydına dönüştürür.
    """
    
    @staticmethod
    async def create_po_from_approval(db: AsyncSession, approval: Approval) -> PurchaseOrder:
        # İdempotency kontrolü: Bu onaya ait aktif bir PO varsa tekrar üretme
        existing_res = await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.approval_id == approval.id,
                PurchaseOrder.status != "cancelled"
            )
        )
        existing_po = existing_res.scalar_one_or_none()
        if existing_po:
            return existing_po

        # Quote ID belirle: Normal onayda agent'ın önerdiği quote, 
        # Exception onayında ise yöneticinin seçtiği quote kullanılır.
        quote_id = approval.selected_quote_id
        if not quote_id:
            # Seçilen quote ID yoksayılmazsa analizdeki öneriyi almalıyız
            await db.refresh(approval, ["analysis"])
            await db.refresh(approval.analysis, ["recommendation"])
            recommendation = approval.analysis.recommendation
            if not recommendation or not recommendation.recommended_quote_id:
                raise ValueError("No valid quote found to create Purchase Order.")
            quote_id = recommendation.recommended_quote_id

        from datetime import date, timedelta
        from app.models.quote import Quote
        from app.models.rfq import RFQ
        from app.models.audit import AuditEvent
        from app.models.order import PurchaseOrderStatus

        quote_obj = await db.get(Quote, quote_id)
        org_id = None
        expected_delivery_date = None
        if quote_obj:
            rfq_obj = await db.get(RFQ, quote_obj.rfq_id)
            if rfq_obj:
                org_id = rfq_obj.organization_id
            if quote_obj.delivery_days is not None:
                start_date = approval.reviewed_at.date() if approval.reviewed_at else date.today()
                expected_delivery_date = start_date + timedelta(days=quote_obj.delivery_days)

        po_number = f"PO-2026-{str(uuid.uuid4())[:8].upper()}"

        # ── Spending Authority Threshold Gate (Procurement Policy Article 1) ───
        # Article 1.1: <= 250,000 TRY: Completed by Department Manager -> status = ISSUED
        # Article 1.2: > 250,000 TRY: Requires Purchasing Director & CFO joint approval.
        # Until multi-level approval architecture is implemented, a single manager approval
        # leaves the PO in DRAFT status, preventing automated supplier issuance and delivery.
        # Currency safety: Non-TRY currencies (USD, EUR, etc.) cannot be silently compared
        # against a TRY threshold and remain in DRAFT for financial review.
        from decimal import Decimal
        SINGLE_MANAGER_THRESHOLD_TRY = Decimal("250000.00")
        quote_currency = (quote_obj.currency or "TRY").upper() if quote_obj else "TRY"
        quote_total = quote_obj.total_price if quote_obj and quote_obj.total_price is not None else Decimal("0")

        if quote_currency != "TRY":
            is_above_threshold = True
        else:
            is_above_threshold = quote_total > SINGLE_MANAGER_THRESHOLD_TRY

        po_status = PurchaseOrderStatus.DRAFT.value if is_above_threshold else PurchaseOrderStatus.ISSUED.value

        po = PurchaseOrder(
            po_number=po_number,
            quote_id=quote_id,
            approval_id=approval.id,
            status=po_status,
            expected_delivery_date=expected_delivery_date,
        )
        
        db.add(po)
        await db.flush()

        db.add(AuditEvent(
            organization_id=org_id,
            actor_id=approval.reviewer_id,
            event_type="po_created",
            entity_type="purchase_order",
            entity_id=po.id,
            payload={
                "po_number": po.po_number,
                "quote_id": str(quote_id),
                "approval_id": str(approval.id),
                "status": po.status
            }
        ))

        await db.commit()
        await db.refresh(po)
        
        print(f"[PurchaseOrderService] Created PO {po.po_number} for quote {quote_id}")
        return po
