# ProcureOps AI — Learning Journal

This document records the key concepts learned at each phase.
Use this as study notes when preparing for interviews.

---

## Phase 0 — Product & Architecture

### What is System Design?
System design means deciding, before writing code, which components you need, how they communicate, where data lives, and what each layer is responsible for. Good system design prevents building the wrong thing.

### The Central Architectural Principle
> **LLMs interpret and orchestrate. Deterministic systems calculate and verify.**

An LLM is a probabilistic system — it generates likely outputs, not guaranteed correct ones. For financial calculations in procurement, we need exact answers. Therefore: let the LLM handle language (extraction, explanation, orchestration), and let backend code handle numbers (TCO, VAT, rule checks).

### What is a Domain Model?
A domain model is the set of "nouns" (entities) your system works with and how they relate to each other. In ProcureOps: RFQ, Quote, Supplier, Policy, Analysis, Approval. Getting the domain model right early prevents major refactoring later.

### RAG vs. Structured Extraction
- **RAG** (Retrieval-Augmented Generation): Take a document, break it into chunks, store as embeddings, retrieve semantically relevant chunks when needed. Best for: prose documents where you search by meaning (policies, contracts).
- **Structured Extraction**: Parse a document and pull out specific fields into a typed schema. Best for: documents with a finite, predictable structure (supplier quotes).

Do not use RAG when structured extraction is the right tool.

---

## Phase 1 — Development Foundation

### What is Docker?
Docker packages a service (and all its dependencies) into a **container** — a lightweight, isolated, reproducible environment. A container behaves identically on every machine because it carries its own operating system dependencies.

Key concepts:
- **Image**: A blueprint (like a class). Built once from a Dockerfile.
- **Container**: A running instance of an image (like an object).
- **Dockerfile**: Instructions for building an image. Each instruction creates a layer.
- **Layer caching**: Docker caches each layer. If the instruction hasn't changed, Docker reuses the cached result. This is why we `COPY pyproject.toml` before `COPY . .` — dependency installation (slow) is cached separately from source code copying (fast).

### What is Docker Compose?
Docker Compose defines and runs **multiple containers** as a single application. Instead of starting each service manually, you write a `docker-compose.yml` and run `docker compose up`.

Key concepts:
- **depends_on**: Tells Compose to start a service only after its dependencies. With `condition: service_healthy`, it waits for the healthcheck to pass.
- **volumes**: Named volumes persist data across container restarts. Without them, a database container loses all data when stopped.
- **env_file**: Injects environment variables from a file. This keeps secrets out of the image.

### What is FastAPI?
FastAPI is a Python web framework for building APIs. It is:
- **Async by default**: Uses Python's `async/await` for non-blocking I/O.
- **Type-safe**: Uses Python type hints for request/response validation.
- **Pydantic-integrated**: Validates all inputs and outputs using Pydantic schemas.
- **Self-documenting**: Automatically generates interactive API docs at `/docs`.

### What is Pydantic?
Pydantic is a Python library for **data validation using type annotations**. You define a class, declare field types, and Pydantic enforces them at runtime. If someone sends `{"price": "not-a-number"}` to a field typed as `float`, Pydantic raises a clear error before the bad data reaches your business logic.

We use `pydantic-settings` to read configuration from environment variables.

### What are Environment Variables?
Environment variables are key-value pairs injected into a process at runtime, from outside the code. Benefits:
1. **Security**: Secrets never appear in source code or Git history.
2. **Portability**: The same code runs in dev (with dev credentials) and production (with prod credentials).
3. **Configurability**: Change behaviour without changing code.

Convention: `.env.example` is committed (shows what variables exist). `.env` is git-ignored (contains real values).

### Why Synchronous Health Check Endpoints?
FastAPI runs synchronous (`def`) endpoints in a **thread pool executor** — separate threads that don't block the main async event loop. This is the correct way to use blocking I/O (like `psycopg2.connect()`) within an async server without freezing it. We use sync here because health checks are rare and correctness matters more than performance.

### What is a Named Volume?
In Docker, a **named volume** (`postgres_data`, `qdrant_data`) is storage managed by Docker that persists independently of the container lifecycle. When you run `docker compose down`, containers are destroyed but named volumes survive. Running `docker compose down -v` destroys volumes too (data loss).

### Technologies Introduced
- Docker, Docker Compose
- FastAPI, Uvicorn
- Pydantic, pydantic-settings
- Next.js (App Router), TypeScript
- PostgreSQL, Qdrant, Redis (as services, not yet used in application logic)
- pyproject.toml, uv (Python packaging)
- Tailwind CSS v4

---

---

## Phase 2 — Domain Model

### Relational Modeling Nedir?
Veritabanındaki her "nesne" bir tablo olarak temsil edilir. Tablolar birbirine **foreign key** ile bağlanır. Bu bağlantılar veri bütünlüğünü garanti eder:
- `RFQ` silindiğinde `quotes` da silinir (`CASCADE`)
- Var olmayan bir `rfq_id`'ye `quote` eklenemez (constraint)
- Bir tedarikçi, ona ait quote varken silinemez (`RESTRICT`)

### Primary Key Stratejisi: UUID vs Integer
**Sequential integer (1, 2, 3...):**
- Avantaj: Küçük, hızlı, debug'da okunabilir
- Dezavantaj: URL'de gizli bilgi sızar (`/rfqs/42` → "42 RFQ var")

**UUID (universally unique identifier):**
- Avantaj: Tahmin edilemez, dağıtık sistemlerde çakışma yok
- Dezavantaj: 36 karakter, biraz daha büyük index

Biz UUID seçtik: güvenlik ve ölçeklenebilirlik önemli.

### SQLAlchemy 2.0 Modern Syntax
```python
# Eski (1.x) stil — hâlâ çalışır ama legacy:
id = Column(Integer, primary_key=True)

# Yeni (2.0) stil — tip güvenli, IDE desteği mükemmel:
id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
```
`Mapped[T]` sayesinde IDE bir `User` objesinde `user.email`'in `str` döndüreceğini bilir.
`Mapped[str | None]` ise `nullable=True` anlamına gelir.

### ORM Relationships ve Async Loading
Async SQLAlchemy'de **lazy loading çalışmaz**. Neden?
```python
# Sync'te bu çalışır:
rfq = session.get(RFQ, some_id)
print(rfq.quotes)  # SQLAlchemy otomatik SELECT çeker — SYNC

# Async'te hata verir:
async with session:
    rfq = await session.get(RFQ, some_id)
    print(rfq.quotes)  # MissingGreenlet hatası!
```
Çözüm: `lazy="selectin"` — SQLAlchemy ilişkiyi ayrı bir `SELECT ... WHERE id IN (...)` sorgusuyla çeker.

### Alembic Migration Zinciri
Her migration dosyasında:
```python
revision = "abc123"       # Bu migration'ın ID'si
down_revision = None      # Bir önceki migration (None = ilk migration)
```
Alembic bu zinciri takip ederek hangi migration'ların çalıştığını bilir.
`alembic upgrade head` → tüm migration'ları sırayla uygula.
`alembic downgrade -1` → son migration'ı geri al.

### Neden İki Farklı PostgreSQL Sürücüsü?
| Sürücü | Kullanım | Neden |
|---|---|---|
| `asyncpg` | Uygulama kodu | Async, yüksek performans |
| `psycopg2` | Alembic migration'ları | Sync, daha basit env.py |

Migration'lar tek seferlik çalışır. Async'in faydası yok.
Uygulama kodu eşzamanlı istekleri işler — asyncpg burada kritik.

### NUMERIC vs FLOAT — Parasal Değerler İçin
```python
import decimal
0.1 + 0.2           # → 0.30000000000000004  ❌
decimal.Decimal("0.1") + decimal.Decimal("0.2")  # → 0.3  ✅
```
PostgreSQL `NUMERIC(14, 4)` → Python `Decimal` → Tam aritmetik.
Tedarik finansallarında yuvarlama hatası kabul edilemez.

### Mixin Pattern
```python
# TimestampMixin ve UUIDPrimaryKeyMixin ayrı class'lar.
# İstediğin modele istediğin kombinasyonda ekleyebilirsin:
class RFQ(Base, UUIDPrimaryKeyMixin, TimestampMixin): ...    # ID + timestamp
class QuoteItem(Base, UUIDPrimaryKeyMixin): ...               # Sadece ID
class AuditEvent(Base, UUIDPrimaryKeyMixin): ...              # ID, kendi created_at'i var
```
Kalıtım yerine composition — daha esnek ve anlaşılır.

### Index Neden Önemli?
```sql
-- Index olmadan:
SELECT * FROM quotes WHERE rfq_id = '...';
-- → PostgreSQL tüm tabloyu tarar (sequential scan) — yavaş

-- index=True ile:
-- → PostgreSQL B-tree index kullanır — çok hızlı
```
Sık sorgulanan foreign key'ler ve status kolonları index'lenmeli.
Index de maliyeti var: her INSERT/UPDATE biraz yavaşlar. Denge önemli.

### Teknolojiler
- SQLAlchemy 2.0 (asyncio mode)
- Alembic
- asyncpg (async PostgreSQL driver)
- psycopg2-binary (sync — Alembic için)

---

*More phases will be added as we progress.*
