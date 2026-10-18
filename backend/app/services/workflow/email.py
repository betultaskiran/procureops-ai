import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.order import PurchaseOrder
from app.models.quote import Quote
from app.models.rfq import RFQ
from app.services.email.service import EmailDeliveryService

logger = logging.getLogger("app.workflow.email")


class EmailService:
    """
    Workflow email service for purchase orders and vendor communications.
    Delegates to the durable transactional outbox (Phase 9) for reliable delivery,
    retries, and auditability.
    """

    @staticmethod
    async def send_po_email(po_id: str | uuid.UUID):
        """
        Sends the official PO issuance notification to the winning supplier
        via the persistent outbox service.
        """
        parsed_id = uuid.UUID(str(po_id))
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PurchaseOrder)
                .options(
                    selectinload(PurchaseOrder.quote).selectinload(Quote.rfq),
                    selectinload(PurchaseOrder.quote).selectinload(Quote.supplier),
                )
                .where(PurchaseOrder.id == parsed_id)
            )
            po = result.scalars().first()

            if not po:
                logger.error(f"[EmailService] Cannot send email. PO not found: {po_id}")
                return

            quote = po.quote
            rfq = quote.rfq if quote else None
            org_id = rfq.organization_id if rfq else None

            if not org_id:
                logger.warning(f"[EmailService] PO {po.po_number} has no associated organization.")
                return

            try:
                delivery, _ = await EmailDeliveryService.create_po_notification(
                    db=db,
                    po_id=po.id,
                    organization_id=org_id,
                )
                # Dispatch delivery immediately in background task
                await EmailDeliveryService.dispatch_delivery(delivery.id)
                logger.info(f"[EmailService] PO {po.po_number} email dispatched via outbox: delivery_id={delivery.id}")
            except ValueError as exc:
                logger.error(f"[EmailService] Validation failed for PO email: {exc}")
                # Do NOT mark po.email_sent = True on validation failure (e.g. DRAFT status or missing email)
                return
            except Exception as exc:
                logger.error(f"[EmailService] Unexpected error sending PO email: {exc}")
                return
