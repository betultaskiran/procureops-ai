"""
app/services/email/worker.py

Durable Outbox Worker daemon and CLI runner (Phase 9).
Picks up pending or due retry deliveries from PostgreSQL and safely dispatches them.

Usage:
  # Continuous daemon polling every 5 seconds
  python -m app.services.email.worker

  # Single batch pass (for cron or CI)
  python -m app.services.email.worker --once
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

from sqlalchemy import select, and_, or_

from app.db.session import AsyncSessionLocal, engine
from app.models.email_delivery import EmailDelivery, EmailDeliveryStatus
from app.services.email.service import EmailDeliveryService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.email.worker")


async def process_outbox_batch(batch_size: int = 10) -> int:
    """
    Finds due pending deliveries (status='queued' and next_retry_at is None or <= now)
    and dispatches each through EmailDeliveryService.
    """
    now_utc = datetime.now(timezone.utc)
    delivery_ids: list = []

    async with AsyncSessionLocal() as db:
        stmt = (
            select(EmailDelivery.id)
            .where(
                and_(
                    EmailDelivery.status == EmailDeliveryStatus.QUEUED.value,
                    or_(
                        EmailDelivery.next_retry_at.is_(None),
                        EmailDelivery.next_retry_at <= now_utc,
                    ),
                )
            )
            .order_by(EmailDelivery.queued_at.asc())
            .limit(batch_size)
        )
        res = await db.execute(stmt)
        delivery_ids = list(res.scalars().all())

    if not delivery_ids:
        return 0

    logger.info(f"[OutboxWorker] Found {len(delivery_ids)} due delivery tasks. Dispatching...")
    processed_count = 0
    for d_id in delivery_ids:
        try:
            res = await EmailDeliveryService.dispatch_delivery(d_id)
            if res:
                processed_count += 1
        except Exception as exc:
            logger.exception(f"[OutboxWorker] Error processing delivery {d_id}: {exc}")

    return processed_count


async def run_worker_loop(poll_interval: int = 5, stop_event: asyncio.Event | None = None) -> None:
    """
    Continuous worker loop polling outbox queue until interrupted.
    """
    if stop_event is None:
        stop_event = asyncio.Event()

    logger.info(f"[OutboxWorker] Started email outbox worker loop (poll_interval={poll_interval}s)")

    while not stop_event.is_set():
        try:
            processed = await process_outbox_batch(batch_size=10)
            if processed > 0:
                logger.info(f"[OutboxWorker] Successfully dispatched {processed} emails.")
                # If jobs were found, check immediately for more without delay
                continue
        except Exception as exc:
            logger.exception(f"[OutboxWorker] Unexpected loop error: {exc}")

        # Sleep with early wakeup support
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            pass

    logger.info("[OutboxWorker] Outbox worker loop stopped cleanly.")


def main():
    parser = argparse.ArgumentParser(description="ProcureOps Email Outbox Worker")
    parser.add_argument("--once", action="store_true", help="Process a single batch and exit")
    parser.add_argument("--interval", type=int, default=5, help="Polling interval in seconds")
    args = parser.parse_args()

    stop_event = asyncio.Event()

    def handle_signal(*_):
        logger.info("[OutboxWorker] Received shutdown signal...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    async def _runner():
        if args.once:
            count = await process_outbox_batch(batch_size=50)
            logger.info(f"[OutboxWorker] Completed single batch run. Processed {count} jobs.")
        else:
            await run_worker_loop(poll_interval=args.interval, stop_event=stop_event)
        await engine.dispose()

    try:
        asyncio.run(_runner())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
