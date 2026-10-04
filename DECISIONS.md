# ProcureOps AI — Architectural Decisions

This document records every significant architectural decision, why it was made,
what alternatives were considered, and what trade-offs were accepted.

Format for each decision:
- **Context**: The situation that required a decision
- **Decision**: What we chose
- **Reasons**: Why this choice
- **Alternatives**: What else we considered
- **Why rejected**: Why we did not choose the alternatives
- **Trade-offs**: What we gave up

---

## ADR-001: Structured extraction for supplier quotes (not RAG)

**Context**: Supplier quote documents need to be processed and their data compared.

**Decision**: Quote documents are parsed into structured PostgreSQL records using LLM-assisted field extraction + Pydantic validation.

**Reasons**:
- Quote data has a finite, predictable schema (price, VAT, delivery days, warranty, etc.)
- Exact data enables exact SQL comparisons and deterministic calculations
- Pydantic validation catches extraction errors immediately
- Structured data is auditable — you can see exactly what was extracted

**Alternatives**: Embed the entire quote as vector chunks; retrieve with semantic search when questions arise.

**Why rejected**: "What is the unit price for product X?" has a single correct answer. RAG would return a semantically similar chunk — not guaranteed to be the exact value. Precision is non-negotiable for financial procurement data.

**Trade-offs**: Extraction can fail for unusual document formats. We must handle extraction failures gracefully and allow human correction.

---

## ADR-002: RAG only for enterprise knowledge documents

**Context**: Company policies, SLAs, and contracts need to be searchable.

**Decision**: Only policy-type documents (policies, SLAs, contracts, framework agreements) are embedded and stored in Qdrant.

**Reasons**:
- Policy documents are unstructured prose — no fixed schema
- Relevant information is buried in paragraphs, not in predictable fields
- Semantic search is appropriate when you search by meaning ("minimum warranty requirement")

**Alternatives**: Manual rule entry (admin types policy rules into a structured database).

**Why rejected**: Policy documents are long, change over time, and contain nuanced language. Manual rule entry is error-prone and hard to maintain as policies evolve.

**Trade-offs**: RAG can retrieve irrelevant chunks. Retrieval quality must be evaluated and tuned. Chunk size and overlap affect precision.

---

## ADR-003: One orchestrator agent with well-defined tools

**Context**: The system needs AI reasoning over multiple data sources to produce a procurement recommendation.

**Decision**: A single agent orchestrates multiple deterministic tools. We start with one agent.

**Reasons**:
- One agent is easier to debug, test, and reason about
- Most procurement analyses fit within a single orchestration pass
- Premature multi-agent architecture adds coordination complexity without a proven need

**Alternatives**: Separate agents for extraction, comparison, policy checking, and recommendation.

**Why rejected**: Multi-agent systems require coordination protocols, shared state management, and error propagation across agents. These problems should only be introduced when a single agent demonstrably cannot handle the load or complexity.

**Trade-offs**: A single agent may become a bottleneck for complex RFQs with many suppliers. We can split by function when a measured bottleneck appears.

---

## ADR-004: Deterministic verification layer (not LLM self-verification)

**Context**: The agent produces a recommendation that may contain errors or hallucinations.

**Decision**: A rule engine (pure Python) validates the recommendation against business rules before it is shown to any human.

**Reasons**:
- LLMs can hallucinate facts ("Supplier X has 24-month warranty" when the quote says 12)
- A model that made an error often cannot identify it when asked to verify itself
- Deterministic rules produce consistent, testable, auditable results

**Alternatives**: Ask a second LLM call to verify the first LLM's output.

**Why rejected**: Same model family, same training data — systematic errors are likely to repeat. This adds latency and cost without reliability guarantees.

**Trade-offs**: The rule engine must be kept up to date as policies change. Rules have maintenance cost.

---

## ADR-005: Mandatory human approval before consequential actions

**Context**: The system can draft supplier emails and purchase orders.

**Decision**: No email is sent and no PO is created without explicit human approval.

**Reasons**:
- AI mistakes in procurement have real financial and legal consequences
- Procurement policies in most organisations require human authorisation
- Building trust in the AI system requires a track record of human-approved decisions

**Alternatives**: Auto-approve low-value orders; fully automated for routine procurement.

**Why rejected**: Accepted deliberately in Phase 1. Organisation-level automation thresholds can be added later when the system has a track record.

**Trade-offs**: Reduced automation speed. This is acceptable given the stakes.

---

## ADR-006: Decimal arithmetic for all monetary calculations

**Context**: The TCO calculator handles prices, VAT, discounts, and shipping.

**Decision**: All monetary values use Python's `decimal.Decimal` type, not `float`.

**Reasons**:
- IEEE 754 floating-point arithmetic introduces rounding errors (0.1 + 0.2 = 0.30000000000000004)
- Procurement involves financial reporting — errors are unacceptable
- `Decimal` is exact for base-10 arithmetic with a configurable precision

**Alternatives**: Store amounts as integers (smallest currency unit: cents or kuruş).

**Why not rejected entirely**: Integer storage is also valid and used in payment systems. We chose `Decimal` because it reads naturally in business logic code and handles percentage calculations cleanly. We may revisit for the database storage layer.

**Trade-offs**: Slightly more verbose code. Decimal arithmetic is slower than float (negligible for our scale).

---

## ADR-007: PostgreSQL over NoSQL for structured domain data

**Context**: Choosing a primary database for domain entities.

**Decision**: PostgreSQL for all structured data.

**Reasons**:
- Domain entities are relational (RFQ → Quotes → Items; Supplier → History)
- Foreign key constraints prevent orphaned records
- Transactions ensure consistency across related records
- SQL aggregation is powerful for supplier history analytics
- ACID compliance matters for financial procurement data

**Alternatives**: MongoDB (document store); DynamoDB (key-value/document).

**Why rejected**: Document stores are appropriate for flexible-schema data. Our domain schema is stable and predictable. We would lose relational integrity, joins, and aggregation power.

**Trade-offs**: Schema migrations are required when the model changes. Alembic manages this. Rigid schema means careful design upfront.

---

## ADR-008: Qdrant as vector database

**Context**: Choosing a vector store for policy document embeddings.

**Decision**: Qdrant, self-hosted via Docker.

**Reasons**:
- Self-hosted: no external API account or cost required for development
- Production-ready: used in production systems, not just prototypes
- Good Python client with filtering, collections, and payload support
- Can run in Docker alongside our other services

**Alternatives**: Pinecone (cloud-only, requires account); Chroma (simpler, less production-ready); pgvector (PostgreSQL extension).

**Why rejected**: Pinecone requires account setup and has free tier limits. Chroma is better for rapid prototyping than production. pgvector was seriously considered — it would simplify infrastructure — but Qdrant's dedicated vector features (filtering, named vectors, quantisation) are more appropriate for a project focused on learning retrieval systems.

**Trade-offs**: One more service to manage. More configuration than pgvector.

---

## ADR-009: Python str enum yerine PostgreSQL native ENUM kullanmama

**Context**: Roller, durum değerleri (RFQStatus, ApprovalStatus vb.) gibi sabit değer setleri için enum stratejisi seçimi.

**Decision**: `str + enum.Enum` mixin kullanarak değerleri PostgreSQL'de `VARCHAR` olarak saklarız.

**Reasons**:
- Python enum'u değiştirmek (yeni değer eklemek, isim değiştirmek) sadece Python dosyasında bir satır değişikliği
- PostgreSQL native ENUM'u değiştirmek ayrı bir `ALTER TYPE` migration'ı gerektirir
- `str` mixin sayesinde `UserRole.ADMIN == "admin"` → `True`, dönüştürme gerekmez
- Alembic, ENUM type değişikliklerini yanlış yönetebilir (bilinen kısıtlama)
- API response'larında otomatik string serialization

**Alternatives**: PostgreSQL native ENUM tipi.

**Why rejected**: Native ENUM veritabanı seviyesinde kısıtlama sağlar ama bakım maliyeti yüksektir. Uygulama seviyesinde Pydantic validation zaten değerleri kısıtlar. İki seviyede de kısıtlama gerekmez.

**Trade-offs**:
- Veritabanı seviyesinde enum kısıtlaması yok — geçersiz string teorik olarak yazılabilir
- Pydantic validation API katmanında bunu önler
- Doğrudan SQL insert yapan araçlar (pgAdmin vb.) geçersiz değer yazabilir — kabul edilebilir risk

---

*New decisions will be added as each phase introduces architectural choices.*

---

## ADR-010: Analysis Pipeline Sırası ve Katman İsimlendirmesi

**Context**: Extraction, TCO, Hard Rules, RAG, LLM Reasoning ve Verification'ın hangi sırada çalışacağı ve nasıl isimlendirileceği.

**Decision**: Altı aşamalı hibrit pipeline. İki farklı deterministik kontrol katmanı — LLM'den önce ve sonra — açıkça ayrıştırılır.

```
1. Extraction            → Tüm teklifler için PDF/belge → Structured Quote
2. Deterministic Pre-validation → TCO + Hard Rules → PASS / HARD_FAIL ayrımı
3. Parallel I/O          → asyncio.gather(RAG, SQL) — sadece PASS teklifler için
4. LLM Reasoning         → PASS: tam veri | HARD_FAIL: sadece özet
5. Post-LLM Verification → LLM çıktısını deterministik olgulara karşı kontrol
6. Evidence Assembly     → Tüm kaynaklar toplanır
7. Human Review
```

**Kritik kararlar:**

1. **Hard-fail teklifler LLM'ye tam veri olarak gönderilmez.**
   Sadece özetlenmiş eleme sonucu gönderilir (kural adı, bulunan değer, gerekli değer).
   Neden: Token tasarrufu + LLM'nin hard rule'u "trade-off olarak yeniden değerlendirmesi" önlenir.
   "LLM'ye göndermemek ≠ kullanıcıdan gizlemek" — audit trail ComplianceCheck tablosundan gelir.

2. **Hard constraint değerleri yapılandırılmış bir kural tablosundan okunur, policy belgesinden değil.**
   RAG bu değerleri "keşfetmek" için değil, LLM'e nuanslı policy bağlamı sağlamak için kullanılır.

3. **RAG ve SQL sorguları paralel çalışır (`asyncio.gather`).**
   Bu iki I/O işlemi birbirine bağımlı değildir, sıralı çalıştırılması gereksiz latency üretir.

4. **"Deterministic Pre-validation" ve "Post-LLM Verification" iki ayrı kavramdır.**

   | Katman | Ne zaman | Amaç | Soru |
   |---|---|---|---|
   | Deterministic Pre-validation | LLM'den önce | Eligibility | "Bu tedarikçi değerlendirilebilir mi?" |
   | Post-LLM Verification | LLM'den sonra | Güvenilirlik | "LLM doğru sonuca ulaştı mı?" |

**Alternatives considered:**
- **A: Hard-fail'leri LLM'ye hiç dahil etmeme** → Reddedit: LLM öneri metninde neden bazı tedarikçilerin olmadığını tutarlı şekilde açıklayamaz.
- **B: Tüm teklifleri LLM'ye gönderip işaretleme** → Reddedit: Gereksiz token harcaması, LLM'nin hard rule'u "yeniden değerlendirme" riski.
- **Seçilen: Özetlenmiş eleme sonucu** → LLM A'nın neden olmadığını bilir, ama trade-off tartışmasına temeli olan tam veriye erişemez.

**Trade-offs**: Kural tablosunun bakımı gerektirir. Yeni bir hard constraint eklemek için hem kural tablosuna hem de policy belgesine yazılması gerekebilir (çift kayıt riski). Bu risk Phase 5'te policy parsing geldiğinde azaltılabilir.
