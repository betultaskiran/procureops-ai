import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.order import PurchaseOrder

class EmailService:
    """
    Tedarikçiye e-posta gönderiminden (simülasyon) sorumlu servis.
    Bu servis framework bağımsız tasarlandığı için ileride Celery içinden 
    veya FastAPI BackgroundTasks içinden çağrılabilir.
    """
    
    @staticmethod
    async def send_po_email(po_id: str):
        from app.db.session import AsyncSessionLocal
        
        # 1. Simulate network delay / email provider processing
        print(f"[EmailService] Email job started for PO: {po_id}")
        await asyncio.sleep(2) # 2 saniye bekle
        
        # 2. İşlem tamamlandı, veritabanını kendi session'ı ile güncelle
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
            po = result.scalars().first()
            
            if po:
                po.email_sent = True
                po.email_sent_at = datetime.utcnow()
                await db.commit()
                print(f"[EmailService] SUCCESS - Email sent to supplier for PO: {po.po_number}")
            else:
                print(f"[EmailService] ERROR - PO not found: {po_id}")
