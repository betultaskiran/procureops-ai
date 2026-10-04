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
    """
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


# ── Register routers ──────────────────────────────────────────────────────────
# Phase 1: /health
# Phase 3: /api/v1/rfqs/{id}/quote-documents, /api/v1/quotes
# Phase 9: /api/v1/analyses  (coming)
app.include_router(health_router)
app.include_router(quotes_router)


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
