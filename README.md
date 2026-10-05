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

## Development Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Product & Architecture | ✅ Complete |
| 1 | Development Foundation | ✅ Complete |
| 2 | Domain Model | ✅ Complete |
| 3 | Quote Ingestion & Extraction | ✅ Complete |
| 4 | TCO Calculator & Hard Rules | ✅ Complete |
| 5 | Policy Knowledge Base (RAG) | ✅ Complete |
| 6 | Agentic AI Reasoning | ⏳ Next |
| 7 | BM25, Hybrid Search & Reranking | — |
| 8 | Supplier Memory (SQL) | — |
| 9 | Verification & Evidence | — |
| 10 | Frontend API Integration | — |
| 11 | Frontend UI / UX | — |
| 12 | Authentication & Authorization | — |
| 13 | Background Jobs & Production AI | — |
| 14 | AI Evaluation | — |
| 15 | Security | — |
| 16 | Reports & Final Workflow | — |
| 17 | Testing & Deployment | — |

---

## Core Principle

> **LLMs interpret and orchestrate. Deterministic systems calculate and verify.**

The LLM never produces final financial calculations. The system never blindly trusts the LLM's compliance claims. Every recommendation is verified by business rules and grounded in traceable evidence.
