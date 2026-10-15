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
| **Phase 5** | **Authentication, RBAC & Team Management** | Real JWT auth, password hashing, role enforcement (`admin`, `manager`, `employee`, `viewer`), tenant isolation middleware, and `/dashboard/team` member management page. *(Currently mock auth / team page 404)* | ⏳ **Next Phase** |
| **Core AI** | **Deterministic TCO & Hard Rules** | Deterministic VAT, shipping, discount calculation (`tco.py`), hard rules evaluation (`compliance.py`, `orchestrator.py`, `test_multi_analysis.py`). | ✅ Complete |
| **Core AI** | **Policy Knowledge Base (RAG & Hybrid Search)** | Dense + BM25 sparse hybrid retrieval with Reciprocal Rank Fusion (RRF), topical grounding, PDF chunking (`rag/service.py`, `test_policy_rag.py` 10 tests). | ✅ Complete |
| **Core AI** | **Agentic Reasoning & Evidence Verification** | LLM trade-off synthesis, single-agent verification layer, evidence grounding cards (`agent/service.py`, `verification.py`, `EvidencePanel.tsx`). | ✅ Complete |
| **Workflow** | **Human Review, Approval & Idempotent PO** | Standard vs Exception approval (`acknowledged_policy_violation`), duplicate PO blocking, cancellation flow (`ReviewModal.tsx`, `order.py`, `email.py`). | ✅ Complete |
| **Phase 6** | **Background Jobs & Async Workers** | Celery / ARQ / Redis async worker daemon for background PDF ingestion and async email delivery. *(Redis active; async job runner pending)* | ⏳ Partial |
| **Phase 7** | **AI Evaluation & Quality Observability** | Automated benchmark dataset for extraction and policy retrieval precision, prompt regression testing, cost/token tracking. *(16-query RAG tests complete; full eval harness pending)* | ⏳ Partial |
| **Phase 8** | **Security Hardening & Audit Compliance** | Rate limiting, OWASP sanitization, file upload scanning, row-level tenant security, tamper-proof audit export (`models/audit.py` present). | ⏳ Partial |
| **Phase 9** | **Production CI/CD & Deployment** | GitHub Actions pipeline, production Docker/K8s manifests, automated migrations, SSL/TLS termination. | ⏳ Pending |

> [!IMPORTANT]
> **Audit Finding on Team Management & Authentication:**
> The frontend sidebar links to `/dashboard/team`, but the route does not exist (returns 404). Furthermore, backend endpoints currently use mock organization lookup (`select(Organization).limit(1)`). Phase 5 is designated as the immediate next phase to implement real authentication, tenant-scoped RBAC, and team member management.

---

## Core Principle

> **LLMs interpret and orchestrate. Deterministic systems calculate and verify.**

The LLM never produces final financial calculations. The system never blindly trusts the LLM's compliance claims. Every recommendation is verified by business rules and grounded in traceable evidence.
