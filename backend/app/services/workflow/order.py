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

        # Rastgele bir PO numarası üret
        po_number = f"PO-2026-{str(uuid.uuid4())[:8].upper()}"

        po = PurchaseOrder(
            po_number=po_number,
            quote_id=quote_id,
            approval_id=approval.id,
            status="issued"
        )
        
        db.add(po)
        await db.flush()

        # AuditEvent kaydet
        from app.models.quote import Quote
        from app.models.rfq import RFQ
        from app.models.audit import AuditEvent

        quote_obj = await db.get(Quote, quote_id)
        org_id = None
        if quote_obj:
            rfq_obj = await db.get(RFQ, quote_obj.rfq_id)
            if rfq_obj:
                org_id = rfq_obj.organization_id

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
