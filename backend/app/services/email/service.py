"""
app/services/email/service.py

High-level business service orchestrating persistent email deliveries,
idempotent queueing, background worker dispatch, and error handling (Phase 9).
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.email_delivery import (
    EmailDelivery,
    EmailDeliveryStatus,
    EmailMessageType,
)
from app.models.order import PurchaseOrder
from app.models.organization import Organization
from app.models.rfq import RFQ
from app.models.supplier import Supplier
from app.services.email.base import EmailMessage
from app.services.email.factory import get_email_provider
from app.services.email.renderer import (
    validate_email_address,
    render_rfq_invitation,
    render_po_notification,
)

logger = logging.getLogger("app.email.service")


class EmailDeliveryService:
    """
    Service responsible for persistent transactional outbox email operations.
    """

    @staticmethod
    async def create_rfq_invitation(
        db: AsyncSession,
        rfq_id: uuid.UUID,
        recipient_email: str,
        organization_id: uuid.UUID,
        supplier_id: uuid.UUID | None = None,
        recipient_name: str | None = None,
        custom_message: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[EmailDelivery, bool]:
        """
        Idempotently queues an RFQ invitation email for asynchronous delivery.

        Returns:
            tuple[EmailDelivery, is_new_or_requeued: bool]
        """
        # 1. Validate email address syntax and guard against CRLF injection
        clean_email = validate_email_address(recipient_email)

        # 2. Tenant isolation check: RFQ must belong to the caller's organization
        rfq_res = await db.execute(
            select(RFQ).where(and_(RFQ.id == rfq_id, RFQ.organization_id == organization_id))
        )
        rfq = rfq_res.scalars().first()
        if not rfq:
            raise ValueError("RFQ not found or access denied for this organization.")

        # 3. If supplier_id provided, verify tenant ownership
        supplier_name = "Supplier"
        if supplier_id:
            sup_res = await db.execute(
                select(Supplier).where(
                    and_(Supplier.id == supplier_id, Supplier.organization_id == organization_id)
                )
            )
            supplier = sup_res.scalars().first()
            if not supplier:
                raise ValueError("Supplier not found or access denied for this organization.")
            supplier_name = supplier.name

        # 4. Form deterministic idempotency key
        effective_key = idempotency_key or f"rfq_invite_{rfq.id}_{supplier_id or 'direct'}_{clean_email.lower()}"

        # 5. Check for pre-existing outbox record with this idempotency key
        existing_res = await db.execute(
            select(EmailDelivery).where(EmailDelivery.idempotency_key == effective_key)
        )
        existing = existing_res.scalars().first()

        if existing:
            # If already sent, delivered, or queued/in-flight, return existing record without duplicating
            if existing.status in (
                EmailDeliveryStatus.QUEUED.value,
                EmailDeliveryStatus.SENDING.value,
                EmailDeliveryStatus.SENT.value,
                EmailDeliveryStatus.DELIVERED.value,
            ):
                logger.info(
                    f"[EmailService] Idempotent request for key '{effective_key}'. Returning existing status '{existing.status}'."
                )
                return existing, False

            # If existing was failed, allow user to re-queue it cleanly
            existing.status = EmailDeliveryStatus.QUEUED.value
            existing.attempt_count = 0
            existing.last_error = None
            existing.next_retry_at = None
            existing.queued_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(existing)
            logger.info(f"[EmailService] Re-queued previously failed delivery: id={existing.id}")
            return existing, True

        # 6. Fetch organization name for branding
        org_res = await db.execute(select(Organization).where(Organization.id == organization_id))
        org = org_res.scalars().first()
        org_name = org.name if org else "ProcureOps Organization"

        # 7. Render message templates
        subject, text_body, html_body = render_rfq_invitation(
            rfq_id=rfq.id,
            rfq_title=rfq.title,
            rfq_description=rfq.description,
            required_quantity=rfq.required_quantity,
            required_date=rfq.required_date,
            supplier_name=supplier_name,
            recipient_name=recipient_name,
            organization_name=org_name,
            app_base_url=settings.APP_BASE_URL,
            custom_message=custom_message,
        )

        metadata = {
            "rfq_title": rfq.title,
            "supplier_name": supplier_name,
            "custom_message": custom_message,
            "app_base_url": settings.APP_BASE_URL,
        }

        # 8. Create persistent outbox record
        delivery = EmailDelivery(
            organization_id=organization_id,
            rfq_id=rfq.id,
            supplier_id=supplier_id,
            recipient_email=clean_email,
            recipient_name=recipient_name,
            subject=subject,
            message_type=EmailMessageType.RFQ_INVITATION.value,
            idempotency_key=effective_key,
            status=EmailDeliveryStatus.QUEUED.value,
            attempt_count=0,
            max_attempts=settings.EMAIL_MAX_RETRIES,
            queued_at=datetime.now(timezone.utc),
            metadata_json=json.dumps(metadata),
        )

        db.add(delivery)
        await db.commit()
        await db.refresh(delivery)

        logger.info(
            f"[EmailService] Enqueued RFQ invitation: delivery_id={delivery.id} rfq={rfq.id} to={clean_email}"
        )
        return delivery, True

    @staticmethod
    async def create_po_notification(
        db: AsyncSession,
        po_id: uuid.UUID,
        organization_id: uuid.UUID,
        idempotency_key: str | None = None,
    ) -> tuple[EmailDelivery, bool]:
        """
        Idempotently queues a Purchase Order notification email for the awarded supplier.
        """
        # Fetch PO and verify tenant
        po_res = await db.execute(
            select(PurchaseOrder)
            .join(PurchaseOrder.quote)
            .join(PurchaseOrder.quote.property.mapper.class_.rfq)
            .where(
                and_(
                    PurchaseOrder.id == po_id,
                    PurchaseOrder.quote.property.mapper.class_.rfq.property.mapper.class_.organization_id == organization_id,
                )
            )
        )
        po = po_res.scalars().first()
        if not po:
            raise ValueError("Purchase Order not found or access denied for this organization.")

        quote = po.quote
        supplier = quote.supplier
        recipient_email = supplier.email if supplier and supplier.email else None
        if not recipient_email:
            raise ValueError(f"Supplier '{supplier.name if supplier else 'Unknown'}' does not have a configured email address.")

        clean_email = validate_email_address(recipient_email)
        effective_key = idempotency_key or f"po_issuance_{po.id}_{po.po_number}"

        existing_res = await db.execute(
            select(EmailDelivery).where(EmailDelivery.idempotency_key == effective_key)
        )
        existing = existing_res.scalars().first()
        if existing:
            return existing, False

        org_res = await db.execute(select(Organization).where(Organization.id == organization_id))
        org = org_res.scalars().first()
        org_name = org.name if org else "ProcureOps Organization"

        subject, text_body, html_body = render_po_notification(
            po_number=po.po_number,
            po_id=po.id,
            supplier_name=supplier.name,
            total_amount=f"{quote.total_price:,.2f}" if quote.total_price else "0.00",
            currency=quote.currency or "TRY",
            organization_name=org_name,
            app_base_url=settings.APP_BASE_URL,
        )

        delivery = EmailDelivery(
            organization_id=organization_id,
            rfq_id=quote.rfq_id,
            supplier_id=supplier.id,
            purchase_order_id=po.id,
            recipient_email=clean_email,
            recipient_name=supplier.name,
            subject=subject,
            message_type=EmailMessageType.PO_ISSUANCE.value,
            idempotency_key=effective_key,
            status=EmailDeliveryStatus.QUEUED.value,
            attempt_count=0,
            max_attempts=settings.EMAIL_MAX_RETRIES,
            queued_at=datetime.now(timezone.utc),
            metadata_json=json.dumps({"po_number": po.po_number}),
        )

        db.add(delivery)
        await db.commit()
        await db.refresh(delivery)
        return delivery, True

    @staticmethod
    async def dispatch_delivery(delivery_id: uuid.UUID) -> EmailDelivery | None:
        """
        Atomically claims a queued or retry-eligible delivery record and transmits it via the provider.
        Safe against concurrent workers via SELECT ... FOR UPDATE SKIP LOCKED.
        """
        async with AsyncSessionLocal() as db:
            now_utc = datetime.now(timezone.utc)
            
            # Atomic claim
            stmt = (
                select(EmailDelivery)
                .where(
                    and_(
                        EmailDelivery.id == delivery_id,
                        EmailDelivery.status.in_([EmailDeliveryStatus.QUEUED.value, EmailDeliveryStatus.FAILED.value]),
                    )
                )
                .with_for_update(skip_locked=True)
            )
            result = await db.execute(stmt)
            delivery = result.scalars().first()

            if not delivery:
                logger.debug(f"[EmailService] Delivery {delivery_id} skipped: already locked or not queued.")
                return None

            # Mark state as 'sending' to avoid double-processing
            delivery.status = EmailDeliveryStatus.SENDING.value
            await db.commit()
            await db.refresh(delivery)

            # Re-render message from stored data or metadata
            metadata = {}
            if delivery.metadata_json:
                try:
                    metadata = json.loads(delivery.metadata_json)
                except Exception:
                    pass

            org_res = await db.execute(
                select(Organization).where(Organization.id == delivery.organization_id)
            )
            org = org_res.scalars().first()
            org_name = org.name if org else "ProcureOps Organization"

            if delivery.message_type == EmailMessageType.RFQ_INVITATION.value:
                rfq_res = await db.execute(select(RFQ).where(RFQ.id == delivery.rfq_id))
                rfq = rfq_res.scalars().first()
                rfq_title = rfq.title if rfq else metadata.get("rfq_title", "Procurement Request")
                rfq_desc = rfq.description if rfq else None
                req_qty = rfq.required_quantity if rfq else None
                req_date = rfq.required_date if rfq else None

                subject, text_body, html_body = render_rfq_invitation(
                    rfq_id=delivery.rfq_id or uuid.uuid4(),
                    rfq_title=rfq_title,
                    rfq_description=rfq_desc,
                    required_quantity=req_qty,
                    required_date=req_date,
                    supplier_name=metadata.get("supplier_name", "Valued Supplier"),
                    recipient_name=delivery.recipient_name,
                    organization_name=org_name,
                    app_base_url=settings.APP_BASE_URL,
                    custom_message=metadata.get("custom_message"),
                )
            else:
                # PO Notification
                subject = delivery.subject
                text_body = f"Purchase Order Notification from {org_name}.\nPO ID: {delivery.purchase_order_id}"
                html_body = f"<p>Purchase Order Notification from <strong>{org_name}</strong>.</p><p>PO ID: {delivery.purchase_order_id}</p>"

            email_msg = EmailMessage(
                recipient_email=delivery.recipient_email,
                recipient_name=delivery.recipient_name,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )

            # Call provider
            provider = get_email_provider()
            send_result = await provider.send_email(email_msg)

            # Update DB according to outcome
            if send_result.success:
                delivery.status = EmailDeliveryStatus.SENT.value
                delivery.sent_at = datetime.now(timezone.utc)
                delivery.provider_message_id = send_result.provider_message_id
                delivery.last_error = None
                delivery.next_retry_at = None

                # If this was linked to a PurchaseOrder, update PO's legacy flags
                if delivery.purchase_order_id:
                    po_res = await db.execute(
                        select(PurchaseOrder).where(PurchaseOrder.id == delivery.purchase_order_id)
                    )
                    po = po_res.scalars().first()
                    if po:
                        po.email_sent = True
                        po.email_sent_at = datetime.now(timezone.utc)

                logger.info(
                    f"[EmailService] Successfully sent delivery_id={delivery.id} to={delivery.recipient_email} "
                    f"msg_id={send_result.provider_message_id}"
                )
            else:
                delivery.attempt_count += 1
                sanitized_error = send_result.error_message or "Unknown delivery failure"

                if send_result.is_transient and delivery.attempt_count < delivery.max_attempts:
                    # Bounded exponential backoff
                    backoff_sec = settings.EMAIL_RETRY_BACKOFF_SECONDS * (2 ** (delivery.attempt_count - 1))
                    delivery.status = EmailDeliveryStatus.QUEUED.value
                    delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_sec)
                    delivery.last_error = f"[Transient - Retry {delivery.attempt_count}/{delivery.max_attempts}] {sanitized_error}"
                    logger.warning(
                        f"[EmailService] Transient failure for delivery_id={delivery.id}. Scheduled retry in {backoff_sec}s: {sanitized_error}"
                    )
                else:
                    # Permanent failure or max attempts reached
                    delivery.status = EmailDeliveryStatus.FAILED.value
                    delivery.next_retry_at = None
                    prefix = f"[Max attempts ({delivery.max_attempts}) exceeded]" if delivery.attempt_count >= delivery.max_attempts else "[Permanent failure]"
                    delivery.last_error = f"{prefix} {sanitized_error}"
                    logger.error(
                        f"[EmailService] Delivery failed terminal state: delivery_id={delivery.id} error={sanitized_error}"
                    )

            await db.commit()
            await db.refresh(delivery)
            return delivery

    @staticmethod
    async def retry_delivery(
        db: AsyncSession,
        delivery_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> EmailDelivery:
        """
        Manually re-enqueues a failed or pending delivery for immediate retry.
        """
        stmt = select(EmailDelivery).where(
            and_(
                EmailDelivery.id == delivery_id,
                EmailDelivery.organization_id == organization_id,
            )
        )
        res = await db.execute(stmt)
        delivery = res.scalars().first()
        if not delivery:
            raise ValueError("Email delivery record not found or access denied.")

        delivery.status = EmailDeliveryStatus.QUEUED.value
        delivery.attempt_count = 0
        delivery.last_error = None
        delivery.next_retry_at = None
        delivery.queued_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(delivery)
        logger.info(f"[EmailService] Manually re-enqueued delivery_id={delivery_id}")
        return delivery

    @staticmethod
    async def list_rfq_invitations(
        db: AsyncSession,
        rfq_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> list[EmailDelivery]:
        """
        Returns all email delivery records associated with an RFQ for the tenant.
        """
        stmt = (
            select(EmailDelivery)
            .where(
                and_(
                    EmailDelivery.rfq_id == rfq_id,
                    EmailDelivery.organization_id == organization_id,
                )
            )
            .order_by(EmailDelivery.created_at.desc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())
