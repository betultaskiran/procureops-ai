"""
backend/scripts/cleanup_stale_fx_seeds.py

Bu script, geliştirme ve demo süreçlerinde veritabanına eklenen
sahte/tahmini (TCMB_SEED ve TCMB_FALLBACK) kur kayıtlarını güvenli bir şekilde
denetler ve temizler.

MİMARİ GÜVENLİK İLKELERİ:
1. Yalnızca `source IN ('TCMB_SEED', 'TCMB_FALLBACK')` olan kayıtları hedefler.
2. Resmi TCMB veya diğer doğrulanmış bülten kayıtlarına (source == 'TCMB') ASLA DOKUNMAZ.
3. Foreign key bağımlılığı bulunmamaktadır (`tco_results` kendi içinde snapshot saklar).
4. İşlem öncesi ve sonrası kayıt sayılarını net bir şekilde raporlar.
"""

import asyncio
import logging
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cleanup_stale_fx_seeds")


async def cleanup_stale_records():
    async with AsyncSessionLocal() as session:
        # 1. Mevcut durum analizi
        logger.info("=== 1. Mevcut exchange_rates Kaynak Dağılımı ===")
        res = await session.execute(
            text("SELECT source, count(*), min(rate_date), max(rate_date) FROM exchange_rates GROUP BY source;")
        )
        sources = res.fetchall()
        for s in sources:
            logger.info(f"Kaynak: {s[0]} -> {s[1]} adet (Tarih aralığı: {s[2]} - {s[3]})")

        # 2. Temizlenecek sahte/test kayıtlarını say
        res = await session.execute(
            text("SELECT count(*) FROM exchange_rates WHERE source IN ('TCMB_SEED', 'TCMB_FALLBACK');")
        )
        stale_count = res.scalar() or 0
        logger.info(f"\nTemizlenecek sahte/test kaydı sayısı: {stale_count}")

        if stale_count == 0:
            logger.info("Temizlenecek sahte kayıt bulunamadı. İşlem tamamlandı.")
            return

        # 3. Güvenli silme işlemi
        delete_stmt = text(
            "DELETE FROM exchange_rates WHERE source IN ('TCMB_SEED', 'TCMB_FALLBACK');"
        )
        result = await session.execute(delete_stmt)
        await session.commit()
        logger.info(f"Başarıyla {result.rowcount} adet sahte kur kaydı silindi.")

        # 4. İşlem sonrası doğrulama
        logger.info("\n=== 2. Temizlik Sonrası Kaynak Dağılımı ===")
        res = await session.execute(
            text("SELECT source, count(*), min(rate_date), max(rate_date) FROM exchange_rates GROUP BY source;")
        )
        post_sources = res.fetchall()
        for s in post_sources:
            logger.info(f"Kaynak: {s[0]} -> {s[1]} adet (Tarih aralığı: {s[2]} - {s[3]})")


if __name__ == "__main__":
    asyncio.run(cleanup_stale_records())
