import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.supplier import Supplier, SupplierHistory

async def seed_history():
    async with AsyncSessionLocal() as session:
        # Find DEF Elektronik
        result = await session.execute(
            select(Supplier).where(Supplier.name.ilike("%DEF Elektronik%"))
        )
        supplier = result.scalar_one_or_none()

        if not supplier:
            print("DEF Elektronik bulunamadı. Lütfen önce analiz işlemini yapıp tedarikçinin oluşmasını sağlayın.")
            return

        # Check if history already exists
        hist_result = await session.execute(
            select(SupplierHistory).where(SupplierHistory.supplier_id == supplier.id)
        )
        existing = hist_result.scalars().all()
        if existing:
            print(f"{len(existing)} adet geçmiş sipariş zaten var. Tekrar eklenmiyor.")
            return

        # Add 3 historical orders
        history_records = [
            SupplierHistory(
                supplier_id=supplier.id,
                order_reference="PO-2024-001",
                order_date=date(2024, 1, 15),
                promised_date=date(2024, 1, 30),
                delivered_date=date(2024, 2, 2), # 3 days late
                total_amount=Decimal("150000.00"),
                currency="TRY",
                quantity_ordered=50,
                quantity_received=50,
                delay_days=3,
                quality_issues=0,
                rejection_count=0,
                notes="Teslimat 3 gün gecikti ancak ürünler sağlamdı."
            ),
            SupplierHistory(
                supplier_id=supplier.id,
                order_reference="PO-2024-085",
                order_date=date(2024, 5, 10),
                promised_date=date(2024, 5, 20),
                delivered_date=date(2024, 5, 25), # 5 days late
                total_amount=Decimal("200000.00"),
                currency="TRY",
                quantity_ordered=100,
                quantity_received=95,
                delay_days=5,
                quality_issues=2,
                rejection_count=5,
                notes="5 ürün hasarlı geldi, iade edildi. Teslimat gecikti."
            ),
            SupplierHistory(
                supplier_id=supplier.id,
                order_reference="PO-2024-112",
                order_date=date(2024, 8, 1),
                promised_date=date(2024, 8, 15),
                delivered_date=date(2024, 8, 14), # 1 day early
                total_amount=Decimal("50000.00"),
                currency="TRY",
                quantity_ordered=20,
                quantity_received=20,
                delay_days=-1,
                quality_issues=0,
                rejection_count=0,
                notes="Erken ve sorunsuz teslimat."
            )
        ]

        session.add_all(history_records)
        await session.commit()
        print("DEF Elektronik için 3 adet geçmiş sipariş verisi (SupplierHistory) başarıyla eklendi.")

if __name__ == "__main__":
    asyncio.run(seed_history())
