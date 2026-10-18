"""
app/main.py

FastAPI application entry point.

Responsibilities:
  1. Initialize structured logging and correlation tracking
  2. Create FastAPI app with metadata and modern lifespan lifecycle
  3. Register CORS, correlation ID middleware, and production-safe error handlers
  4. Register all API routers
"""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import (
    get_correlation_id,
    set_correlation_id,
    setup_logging,
)
from app.api.health import router as health_router
from app.api.v1.quotes import router as quotes_router
from app.api.v1.rfqs import router as rfqs_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.analyses import router as analyses_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.policies import router as policies_router
from app.api.v1.auth import router as auth_router
from app.api.v1.team import router as team_router
from app.api.v1.orders import router as orders_router
from app.api.v1.portal import router as portal_router
from app.services.vector_store.qdrant import QdrantService

# ── Initialize Logging Early ───────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger("app.main")


# ── Lifespan Event Handler (replaces deprecated on_event) ──────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown management.
    """
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    # Initialize vector store collection for RAG
    try:
        qdrant = QdrantService()
        await qdrant.initialize_collection()
    except Exception as exc:
        logger.warning(f"Qdrant collection initialization warning: {exc}")

    yield

    logger.info(f"Shutting down {settings.APP_NAME}")


# ── Create the FastAPI application ────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Evidence-Backed Procurement Decision & Workflow Engine. "
        "Combines structured document extraction, deterministic computation, "
        "enterprise knowledge retrieval, and agentic AI orchestration."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG or settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.DEBUG or settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)


# ── Correlation ID & Structured Logging Middleware ────────────────────────────
@app.middleware("http")
async def correlation_and_logging_middleware(request: Request, call_next):
    corr_id = (
        request.headers.get("X-Correlation-ID")
        or request.headers.get("X-Request-ID")
        or uuid.uuid4().hex
    )
    set_correlation_id(corr_id)
    request.state.correlation_id = corr_id

    start_time = time.perf_counter()
    req_logger = logging.getLogger("app.request")

    try:
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Correlation-ID"] = corr_id

        # Security Hardening Headers (Phase 14)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

        # Log requests; skip verbose logging for health checks unless failing
        if not request.url.path.startswith("/health") or response.status_code >= 400:
            req_logger.info(
                f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "correlation_id": corr_id,
                },
            )
        return response
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        req_logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc}",
            exc_info=True,
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
                "correlation_id": corr_id,
            },
        )
        raise exc


# ── Global Safe Exception Handler ─────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    corr_id = getattr(request.state, "correlation_id", None) or get_correlation_id() or uuid.uuid4().hex
    err_logger = logging.getLogger("app.errors")
    err_logger.error(f"Internal server error: {exc}", exc_info=True, extra={"correlation_id": corr_id})

    is_production = settings.ENVIRONMENT.lower() in ("production", "prod")
    detail = "Internal server error" if is_production else str(exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": detail, "correlation_id": corr_id},
        headers={"X-Correlation-ID": corr_id},
    )


# ── Add CORS Middleware ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Register routers ──────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(suppliers_router)
app.include_router(rfqs_router)
app.include_router(dashboard_router)
app.include_router(quotes_router)
app.include_router(analyses_router)
app.include_router(knowledge_router)
app.include_router(policies_router)
app.include_router(auth_router)
app.include_router(team_router)
app.include_router(orders_router)
app.include_router(portal_router)


# ── Root endpoint ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"], summary="API root")
async def root():
    """Returns basic information about the API."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.DEBUG or settings.ENVIRONMENT != "production" else None,
        "health": "/health",
    }
