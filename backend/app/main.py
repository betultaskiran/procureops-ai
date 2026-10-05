"""
app/main.py

FastAPI application entry point.

The file is intentionally small. Its only jobs are:
  1. Create the FastAPI app with metadata
  2. Register routers
  3. Define startup/shutdown events
"""

from pathlib import Path

from fastapi import FastAPI

from app.core.config import settings
from app.api.health import router as health_router
from app.api.v1.quotes import router as quotes_router
from app.api.v1.analyses import router as analyses_router
from app.api.v1.knowledge import router as knowledge_router
from app.services.vector_store.qdrant import QdrantService

# ── Create the FastAPI application ────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Evidence-Backed Procurement Decision & Workflow Engine. "
        "Combines structured document extraction, deterministic computation, "
        "enterprise knowledge retrieval, and agentic AI orchestration."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── Startup event ──────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    """
    Uygulama başladığında çalışır.
    Upload dizinini oluşturur (yoksa).
    Qdrant koleksiyonunu başlatır.
    """
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    
    # RAG altyapısı için vektör veritabanını hazırla
    qdrant = QdrantService()
    await qdrant.initialize_collection()


# ── Register routers ──────────────────────────────────────────────────────────
# Phase 1: /health
# Phase 3: /api/v1/rfqs/{id}/quote-documents, /api/v1/quotes
# Phase 4: /api/v1/rfqs/{id}/analyze
# Phase 5: /api/v1/knowledge
app.include_router(health_router)
app.include_router(quotes_router)
app.include_router(analyses_router)
app.include_router(knowledge_router)


# ── Root endpoint ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"], summary="API root")
async def root():
    """Returns basic information about the API."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }
