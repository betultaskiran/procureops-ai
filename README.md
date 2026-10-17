# ProcureOps AI

> Evidence-Backed Procurement Decision & Workflow Engine

An AI-assisted procurement system that combines structured document extraction, deterministic computation, enterprise knowledge retrieval, and agentic AI orchestration — with a human in the loop for every consequential decision.

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Git

### Run locally

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd procureops-ai

# 2. The .env file is already created for local development
#    (it is listed in .gitignore — never commit it)
#    To see all available variables: cat .env.example

# 3. Build and start all services
docker compose up --build

# 4. Verify everything is running
#    Landing page:   http://localhost:3000
#    API root:       http://localhost:8000
#    API docs:       http://localhost:8000/docs
#    Health check:   http://localhost:8000/health
```

### Stop all services

```bash
docker compose down
```

### Stop and delete all data (database, vector store)

```bash
docker compose down -v   # WARNING: destroys all persistent data
```

---

## Services

| Service  | URL                      | Purpose                        |
|----------|--------------------------|--------------------------------|
| Frontend | http://localhost:3000    | Next.js / TypeScript UI        |
| Backend  | http://localhost:8000    | FastAPI Python API             |
| API Docs | http://localhost:8000/docs | Auto-generated Swagger UI    |
| Postgres | localhost:5432           | Relational database            |
| Qdrant   | http://localhost:6333    | Vector database (policy docs)  |
| Redis    | localhost:6379           | Cache and job queue            |

---

## Project Structure

```
procureops-ai/
├── docker-compose.yml      # Orchestrates all services
├── .env.example            # Template for environment variables
├── .env                    # Local dev values (git-ignored)
│
├── backend/                # Python / FastAPI
│   ├── Dockerfile
│   ├── pyproject.toml      # Dependencies and project config
│   └── app/
│       ├── main.py         # FastAPI application entry point
│       ├── core/
│       │   └── config.py   # Centralised settings (env vars)
│       └── api/
│           └── health.py   # Health check endpoints
│
├── frontend/               # Next.js / TypeScript
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       └── app/
│           ├── layout.tsx  # Root layout (wraps every page)
│           └── page.tsx    # Landing page
│
├── ARCHITECTURE.md         # System design documentation
├── LEARNING.md             # Concepts learned at each phase
└── DECISIONS.md            # Architectural decisions with trade-offs
```

---

## Development Phases & Roadmap Audit

The following table reflects the actual implementation state verified by the codebase, endpoints, database schema, and test suite.

| Phase | Milestone / Domain | Implementation Scope & Evidence | Status |
|-------|--------------------|---------------------------------|--------|
| **Phase 0** | **Product & Architecture** | System design, ADRs (`DECISIONS.md`), architecture specifications (`ARCHITECTURE.md`). | ✅ Complete |
| **Phase 1** | **Development Foundation** | FastAPI + Next.js + PostgreSQL + Qdrant + Redis containerization (`docker-compose.yml`, health endpoints). | ✅ Complete |
| **Phase 2** | **Domain Models & Multi-Analysis** | SQLAlchemy models (`models/`), multi-quote analysis safety, fallback rules, staleness detection (`analyses.py`, `test_multi_analysis.py`). | ✅ Complete |
| **Phase 3** | **Quote Ingestion & Multi-Analysis Matrix** | PDF quote upload, structured LLM extraction, side-by-side comparison matrix, stale analysis banner (`ComparisonMatrix.tsx`, `quote_documents`, `test_rfq_quote_lifecycle.py`). | ✅ Complete |
| **Phase 4A** | **Supplier History Data Foundation** | Delivery fields on PO (`expected_delivery_date`, `actual_delivery_date`, `final_amount`, `delivery_notes`), `SupplierHistory` PO link (`models/order.py`, `models/supplier.py`, `test_supplier_history_foundation.py`). | ✅ Complete |
| **Phase 4B** | **Supplier Performance Engine & APIs** | `SupplierPerformanceService`, delivery reliability %, currency-isolated financials, quality metrics, collision detection (`/api/v1/suppliers/{id}/performance`, `history`, `test_supplier_performance.py`). | ✅ Complete |
| **Phase 4C** | **Supplier Performance UI & Drawer** | Accessible slide-over drawer (`SupplierPerformanceDrawer.tsx`), matrix triggers, focus trap, request identity guards, zero-page safety (`frontend/tests/supplier-drawer.test.mjs`). | ✅ Complete |
| **Phase 5** | **Authentication, RBAC & Team Management** | Real JWT auth, Argon2/Bcrypt hashing, role enforcement (`admin`, `manager`, `employee`, `viewer`), tenant-isolated organization scoping, `/dashboard/team` page, last-admin protection (`test_team_management.py`, `test_auth_core.py`, `test_rbac_tenant_isolation.py`). | ✅ Complete |
| **Phase 6** | **Purchase Order Lifecycle & Quality Tracking** | Dedicated lifecycle endpoints (`/api/v1/orders/{id}/deliver`, `/complete`, `/cancel`, `/quality-issues`), `POQualityIssue` model, delay metrics, terminal state safety, UI modals & delay badges (`test_order_lifecycle.py`). | ✅ Complete |
| **Phase 7** | **Production Readiness & Observability** | Alembic migration consistency (`7c4b92df0a12`), fail-closed production config, dual HttpOnly cookie + Bearer token session security, structured JSON logging with correlation IDs, `/health/live` & `/health/ready` probes, Sentry integration hook (`test_production_readiness.py`). | ✅ Complete |
| **Core AI** | **Deterministic TCO & Hard Rules** | Deterministic VAT, shipping, discount calculation (`tco.py`), hard rules evaluation (`compliance.py`, `orchestrator.py`, `test_multi_analysis.py`). | ✅ Complete |
| **Core AI** | **Policy Knowledge Base (RAG & Hybrid Search)** | Dense + BM25 sparse hybrid retrieval with Reciprocal Rank Fusion (RRF), topical grounding, PDF chunking (`rag/service.py`, `test_policy_rag.py` 10 tests). | ✅ Complete |
| **Core AI** | **Agentic Reasoning & Evidence Verification** | LLM trade-off synthesis, single-agent verification layer, evidence grounding cards (`agent/service.py`, `verification.py`, `EvidencePanel.tsx`). | ✅ Complete |
| **Workflow** | **Human Review, Approval & Idempotent PO** | Standard vs Exception approval (`acknowledged_policy_violation`), duplicate PO blocking, cancellation flow (`ReviewModal.tsx`, `order.py`, `email.py`). | ✅ Complete |
| **Phase 8** | **Document Intelligence & Reliable Ingestion** | Robust ingestion pipeline: text-based PDF (`pdfplumber`), scanned PDF & image OCR fallback (Gemini Multimodal Vision), `.xlsx` Excel parsing (`openpyxl`), arithmetic validation & discrepancy warnings, idempotent re-extraction & retry endpoint (`/reprocess`) (`services/extraction/`, `test_document_intelligence.py`). | ✅ Complete |
| **Phase 9** | **Reliable Email Integration** | Provider abstraction (`SMTPEmailProvider`, `MockEmailProvider`), persistent transactional outbox (`email_deliveries`), idempotent RFQ invitations & PO notifications, runnable worker loop, bounded exponential backoff (`services/email/`, `test_email_integration.py`). | ✅ Complete |
| **Phase 10** | **AI Workflow & Agent Orchestration** | 6-stage sequential pipeline (deterministic input validation, TCO & hard rules, Qdrant policy RAG with citation grounding, structured LLM synthesis, independent verification layer setting `passed`/`failed`/`inconclusive`, and human-in-the-loop review with exception approvals blocking PO generation on verification failure) (`services/orchestration/`, `test_workflow_orchestration.py`). | ✅ Complete |
| **Phase 11** | **Security & Pilot Readiness** | Full HttpOnly cookie session hardening, CSRF/CORS, concurrency, end-to-end logging, and pilot UAT. | ⏳ Pending |

---

## Production Deployment & Operational Runbook

### 1. Production Configuration & Secret Generation
Never run with default development secrets in production (`ENVIRONMENT=production` or `DEBUG=false` fails fast if default secrets are detected).

Generate cryptographically secure secrets:
```bash
# Generate 64-character hex JWT secret
openssl rand -hex 32

# Generate high-entropy database password
openssl rand -base64 24
```

Required production environment variables:
```ini
ENVIRONMENT=production
DEBUG=false
POSTGRES_USER=procureops
POSTGRES_PASSWORD=<strong_random_password>
POSTGRES_DB=procureops_db
POSTGRES_HOST=<database_host>
POSTGRES_PORT=5432
JWT_SECRET_KEY=<64_char_random_hex_key>
CORS_ORIGINS=https://app.yourdomain.com
GEMINI_API_KEY=<your_google_ai_studio_api_key>
LOG_FORMAT=json
LOG_LEVEL=INFO
# SENTRY_DSN=https://your_sentry_key@o0.ingest.sentry.io/0
```

### 2. Database Migrations
Always apply migrations before directing user traffic to new backend releases:
```bash
# Check current migration revision
docker compose exec backend alembic current

# Upgrade to latest head (7c4b92df0a12)
docker compose exec backend alembic upgrade head

# Rollback one revision if necessary
docker compose exec backend alembic downgrade -1
```

### 3. Database Backup & Restore Procedures
Backup (Logical dump):
```bash
docker compose exec -T postgres pg_dump -U procureops -d procureops_db -F c -b -v -f /tmp/backup.dump
docker compose cp postgres:/tmp/backup.dump ./procureops_backup_$(date +%Y%m%d_%H%M%S).dump
```

Restore:
```bash
docker compose cp ./procureops_backup.dump postgres:/tmp/backup.dump
docker compose exec postgres pg_restore -U procureops -d procureops_db -v -c /tmp/backup.dump
```

### 4. Health Probes & Monitoring
- **Liveness Probe**: `GET /health/live` (Returns HTTP 200 as long as the process is alive).
- **Readiness Probe**: `GET /health/ready` (Returns HTTP 200 when PostgreSQL, Redis, and Qdrant are operational; returns HTTP 503 if degraded).
- **Full Health Status**: `GET /health` (Returns detailed breakdown of all subsystem statuses).
- **Structured Logs**: In production with `LOG_FORMAT=json`, logs are emitted as JSON lines with correlation ID, HTTP route, duration in ms, and status code for integration with Datadog, ELK, or CloudWatch.

### 5. Document Intelligence & Multi-Format Ingestion
ProcureOps AI processes supplier quotes across multiple formats into structured, mathematically validated records:
- **Digital PDF**: Extracts text and tabular line items via `pdfplumber`.
- **Scanned PDF & Images (PNG/JPG)**: Automatically triggers fallback to Gemini Multimodal Vision OCR (`types.Part.from_bytes`) when text density is insufficient (< 50 characters) or when processing raw images.
- **Excel Workbooks (`.xlsx`)**: Structured worksheet parsing via `openpyxl` with `data_only=True` (resolving formulas to calculated values) and markdown table formatting. Legacy binary `.xls` files are rejected with guidance to upload `.xlsx` or `.pdf`.
- **Arithmetic Discrepancy Detection**: Computes item line math (`qty * unit_price`), subtotal comparisons, and grand total formula checks. Discrepancies are flagged in `Quote.notes` without dropping valid data.
- **Idempotent Reprocessing**: Failed or updated documents can be reprocessed via `POST /api/v1/rfqs/{rfq_id}/quote-documents/{document_id}/reprocess` without duplicate quote creation.

### 6. Reliable Email Integration & Transactional Outbox (Phase 9)
Supplier invitations and purchase order notifications are delivered using a database-backed transactional outbox:
- **Provider Abstraction**: Abstract `EmailProvider` with `SMTPEmailProvider`, `MockEmailProvider`, and `ConsoleEmailProvider`.
- **Persistent Outbox Table (`email_deliveries`)**: Tracks state transitions (`queued` -> `sending` -> `sent` / `failed` -> `delivered`).
- **Delivery Guarantees**: SMTP socket acceptance is recorded strictly as `sent`. `delivered` status requires explicit provider delivery signals / webhooks.
- **Idempotency & Concurrency**: Enforced at the database level using a unique index on `idempotency_key` and atomic `SELECT ... FOR UPDATE SKIP LOCKED` during worker dispatch.
- **Transient Backoff Retries**: Transient socket/server errors trigger bounded exponential backoff (`EMAIL_RETRY_BACKOFF_SECONDS * 2^(attempts-1)`), up to `EMAIL_MAX_RETRIES` (default 3). Permanent recipient or auth rejections fail fast without retrying.
- **Outbox Worker CLI & Daemon**:
  ```bash
  # Run continuous worker loop (polling every 5 seconds)
  docker compose exec backend python -m app.services.email.worker

  # Run a single batch pass (for cron or CI)
  docker compose exec backend python -m app.services.email.worker --once
  ```
- **Local Mailcatcher Testing**:
  To capture emails locally without sending external mail, run a lightweight SMTP receiver:
  ```bash
  # Python built-in debugging server on port 1025
  python -m smtpd -c DebuggingServer -n localhost:1025
  ```

### 7. AI Workflow & Agent Orchestration (Phase 10)
The RFQ analysis workflow is structured into 6 sequential, observable, and isolated stages:
1. **Stage 1 — Extraction & Input Validation (Deterministic)**: Validates minimum quote requirements (>= 2 quotes), currency consistency, and financial completeness. Rejects invalid inputs before any AI service invocation.
2. **Stage 2 — Deterministic TCO & Hard-Rule Evaluation (Deterministic)**: Pure Python calculation of total cost of ownership (subtotal + VAT + shipping - discount + other costs) and evaluation of non-negotiable delivery, warranty, and budget rules.
3. **Stage 3 — Policy Compliance Analysis (Qdrant RAG + Citation Grounding)**: Dense vector similarity search against organizational policies with a minimum score threshold (0.65). If no matching policies meet the threshold, marks `insufficient_evidence` without hallucination.
4. **Stage 4 — Supplier Recommendation (LLM Synthesis)**: Synthesis of financial, operational, and compliance data into a structured schema (`AgentRecommendationSchema`) with trade-off analysis, risk factors, and cited justification.
5. **Stage 5 — Independent Verification Layer (Deterministic & Grounding Engine)**: Evaluates hard-rule violations, TCO consistency, and citation accuracy. Assigns discrete verification states:
   - `passed`: All deterministic checks and citations validated.
   - `failed` / `overridden`: Hard-rule or TCO violation detected. System revokes recommendation (`recommended_quote_id = None`).
   - `inconclusive`: Citations refer to ungrounded or unsupported sources.
6. **Stage 6 — Human Review & Approval Gate (Human-in-the-Loop)**: Gated by verification outcome. Standard `approved` requests for analyses that failed verification return HTTP 400. Overriding a failed recommendation requires an explicit `exception_approved` action with `acknowledged_policy_violation = True` and manager justification.

---

## Core Principle

> **LLMs interpret and orchestrate. Deterministic systems calculate and verify.**

The LLM never produces final financial calculations. The system never blindly trusts the LLM's compliance claims. Every recommendation is verified by business rules and grounded in traceable evidence.
