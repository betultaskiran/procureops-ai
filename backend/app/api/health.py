"""
app/api/health.py

Health check endpoint.

Purpose: prove that the backend is running AND that all dependent services
(PostgreSQL, Qdrant, Redis) are reachable. This is used by:
  - Docker orchestrators (to know if the container is healthy)
  - Monitoring systems (to detect outages)
  - Developers (to verify the local dev environment is working)

Design note: This is a synchronous endpoint (def, not async def).
FastAPI automatically runs synchronous endpoints in a thread pool executor,
so they do not block the async event loop. This is the correct way to call
blocking I/O (like psycopg2) from FastAPI without freezing the server.
"""

import psycopg2
import redis as redis_lib
import httpx
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(tags=["Health"])


def _check_postgres() -> str:
    """
    Attempts to open and immediately close a PostgreSQL connection.
    Returns "ok" or an error description.
    """
    try:
        conn = psycopg2.connect(settings.postgres_url, connect_timeout=3)
        conn.close()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


def _check_redis() -> str:
    """
    Sends a PING to Redis. Expects PONG.
    socket_connect_timeout prevents hanging if Redis is unreachable.
    """
    try:
        r = redis_lib.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            socket_connect_timeout=3,
        )
        r.ping()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


def _check_qdrant() -> str:
    """
    Calls Qdrant's REST health endpoint.
    Qdrant exposes GET /healthz which returns HTTP 200 when healthy.
    We use httpx in synchronous mode here to match the sync endpoint pattern.
    """
    try:
        response = httpx.get(
            f"{settings.qdrant_url}/healthz",
            timeout=3,
        )
        if response.status_code == 200:
            return "ok"
        return f"error: HTTP {response.status_code}"
    except Exception as exc:
        return f"error: {exc}"


@router.get("/health", summary="Service health check")
def health_check():
    """
    Returns the health status of the backend and all dependent services.

    Response shape:
    {
        "status": "ok" | "degraded",
        "version": "0.1.0",
        "services": {
            "postgres": "ok" | "error: ...",
            "qdrant":   "ok" | "error: ...",
            "redis":    "ok" | "error: ..."
        }
    }

    "status" is "ok" only when ALL services are healthy.
    "degraded" means at least one service has a problem.
    """
    services = {
        "postgres": _check_postgres(),
        "qdrant": _check_qdrant(),
        "redis": _check_redis(),
    }

    all_ok = all(v == "ok" for v in services.values())

    return {
        "status": "ok" if all_ok else "degraded",
        "version": settings.APP_VERSION,
        "services": services,
    }
