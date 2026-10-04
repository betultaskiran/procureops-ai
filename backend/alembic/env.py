"""
alembic/env.py

Alembic'in migration'ları nasıl çalıştıracağını tanımlar.

İKİ MOD:
  offline → SQL script üretir, veritabanına bağlanmaz
            (örn: DBA'ya script vermek için)
  online  → Veritabanına bağlanır ve migration'ı anında çalıştırır

SÜRÜCÜ SEÇİMİ:
  Alembic psycopg2 (sync) kullanır.
  Neden async değil?
    - Migration'lar tek seferlik, async'in faydası yok
    - psycopg2 ile env.py kodu çok daha basit
    - asyncpg tabanlı env.py için asyncio.run() ve özel connection
      yönetimi gerekir — gereksiz karmaşıklık
    - SQLAlchemy'nin resmi önerisi de budur

AUTOGENERATE:
  target_metadata = Base.metadata → Alembic modellerimizi okur
  "alembic revision --autogenerate" komutu çalıştırıldığında:
    1. Mevcut veritabanı şemasını okur
    2. SQLAlchemy modellerini (Base.metadata) okur
    3. Farkı bulur
    4. Migration dosyası üretir
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Alembic config objesi ──────────────────────────────────────────────────────
config = context.config

# Python logging'i alembic.ini'deki ayarlarla konfigüre et
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Modellerimizi import ediyoruz ──────────────────────────────────────────────
# Bu import kritik: Base.metadata tüm tabloların tanımını içerir.
# Alembic bu metadata'yı okuyarak tablolarımızı bilir.
# Eğer bu import olmazsa autogenerate hiçbir tablo görmez!
from app.models import Base  # noqa: F401, E402
# Tüm modellerin Base.metadata'ya kayıt olması için models/__init__.py
# bunları import etmeli — zaten öyle yapıyoruz.

target_metadata = Base.metadata


def get_url() -> str:
    """
    Veritabanı URL'ini environment variable'lardan oluşturur.

    psycopg2 için postgresql+psycopg2:// şeması kullanılır.
    (asyncpg'nin aksine sync driver)

    Ortam değişkenleri Docker Compose tarafından inject edilir.
    """
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ["POSTGRES_DB"]
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def run_migrations_offline() -> None:
    """
    'Offline' mod: SQL dosyası üretir, veritabanına bağlanmaz.

    Kullanım:
        alembic upgrade head --sql > migration.sql

    Sonra bu SQL dosyası DBA'ya verilebilir.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Kolon tip değişikliklerini de yakala
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    'Online' mod: Veritabanına bağlanır ve migration'ı çalıştırır.

    Bu mod 'alembic upgrade head' komutuyla çalışır.
    """
    # alembic.ini'deki [alembic] section'ını oku ve URL'i override et
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        # NullPool: Migration sonrası bağlantıları havuzda tutma, hemen kapat.
        # Migration'lar tek seferlik — connection pool'a gerek yok.
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Kolon tip değişikliklerini yakala (örn: String(50) → String(100))
        )

        with context.begin_transaction():
            context.run_migrations()


# Hangi modda çalışacağımızı belirle ve çalıştır
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
