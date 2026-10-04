"""
app/db/session.py

Async veritabanı bağlantısı ve session yönetimi.

NEDEN İKİ FARKLI SÜRÜCÜ?
  asyncpg  → Uygulama kodu (async, yüksek performans)
  psycopg2 → Alembic migration'ları (sync, daha basit)

  Bu ayrım SQLAlchemy'nin resmi önerisidir. Migration'lar tek seferlik
  çalışır, async olmaları gerekmez. Uygulama kodu ise yüzlerce eşzamanlı
  isteği işler — asyncpg burada önemli.

FastAPI DEPENDENCY PATTERN:
  async def get_db() → AsyncSession bir "dependency" olarak tanımlanır.
  FastAPI endpoint'lere şöyle inject eder:

    @router.get("/rfqs")
    async def list_rfqs(db: AsyncSession = Depends(get_db)):
        ...

  get_db() bir generator'dür (yield kullanır). Bu sayede:
  - Her request için yeni session açılır
  - Request bittikten sonra (başarı veya hata) session otomatik kapatılır
  - Connection pool'a geri iade edilir
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _build_async_url(postgres_url: str) -> str:
    """
    config.py'deki postgresql:// URL'ini asyncpg için dönüştürür.

    Neden? SQLAlchemy farklı sürücüler için farklı URL şeması kullanır:
      postgresql://   → psycopg2 (sync)
      postgresql+asyncpg:// → asyncpg (async)
    """
    return postgres_url.replace("postgresql://", "postgresql+asyncpg://", 1)


# ── Engine ────────────────────────────────────────────────────────────────────
# Engine: veritabanı bağlantı havuzunu (connection pool) yönetir.
# Uygulama boyunca tek bir engine instance kullanılır.
#
# echo=DEBUG: DEBUG=True iken tüm SQL sorgularını konsola yazar.
# Geliştirme ortamında yararlı, production'da kesinlikle False.
engine = create_async_engine(
    _build_async_url(settings.postgres_url),
    echo=settings.DEBUG,
    # pool_pre_ping=True: Bir bağlantı kullanılmadan önce "canlı mı?" kontrol eder.
    # Uzun süre bekleyen bağlantıların kesilmiş olma ihtimaline karşı.
    pool_pre_ping=True,
)

# ── Session Factory ───────────────────────────────────────────────────────────
# async_sessionmaker: AsyncSession üretir.
# expire_on_commit=False: commit sonrası objelerin attribute'larını lazy
# reload etmeyi engeller. Async ortamda lazy reload çalışmaz.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency. Her HTTP isteği için bir session açar.

    Kullanım:
        from sqlalchemy.ext.asyncio import AsyncSession
        from fastapi import Depends
        from app.db.session import get_db

        @router.get("/rfqs")
        async def list_rfqs(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(RFQ))
            return result.scalars().all()

    try/finally pattern garanti eder:
      - Exception olsa bile session kapatılır
      - Connection pool'a bağlantı iade edilir
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
