"""
tests/test_production_readiness.py

Phase 7 Production Readiness Test Suite:
1. Health checks: /health/live, /health/ready (200 OK and 503 degraded handling)
2. Correlation ID propagation and structured logging middleware
3. Dual-transport authentication: Bearer Authorization header & HttpOnly access_token cookie
4. Logout session and cookie invalidation
5. Production configuration fail-closed security invariants
6. Alembic schema and migration head consistency
7. Production error response sanitization
"""

import os
from unittest.mock import patch
import uuid

import httpx
from pydantic import ValidationError
import pytest
from sqlalchemy import text

from app.core.config import DEV_JWT_SECRET, Settings
from app.db.session import AsyncSessionLocal
from app.main import app


# ── 1. Health & Probe Tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_live_probe():
    """Verify that /health/live returns HTTP 200 for Kubernetes liveness checks."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health/live")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "version" in data


@pytest.mark.asyncio
async def test_health_ready_probe_success():
    """Verify that /health/ready returns HTTP 200 when backing services are reachable."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health/ready")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["services"]["postgres"] == "ok"
        assert data["services"]["redis"] == "ok"
        assert data["services"]["qdrant"] == "ok"


@pytest.mark.asyncio
async def test_health_ready_probe_degraded_returns_503():
    """When any backing service fails, /health/ready must return HTTP 503."""
    with patch("app.api.health._check_postgres", return_value="error: database connection refused"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/health/ready")
            assert res.status_code == 503
            data = res.json()
            assert data["status"] == "unready"
            assert "database connection refused" in data["services"]["postgres"]


# ── 2. Correlation ID Middleware Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_correlation_id_propagated_when_provided():
    """Incoming X-Correlation-ID header is echoed back on response."""
    custom_id = f"corr-{uuid.uuid4().hex}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health/live", headers={"X-Correlation-ID": custom_id})
        assert res.status_code == 200
        assert res.headers.get("X-Correlation-ID") == custom_id


@pytest.mark.asyncio
async def test_correlation_id_generated_when_absent():
    """When no correlation header is provided, a fresh correlation ID is created."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health/live")
        assert res.status_code == 200
        generated = res.headers.get("X-Correlation-ID")
        assert generated is not None
        assert len(generated) >= 16


# ── 3. Dual-Transport Authentication & Cookie Tests ───────────────────────────

@pytest.mark.asyncio
async def test_auth_login_sets_httponly_cookie():
    """
    POST /api/v1/auth/login returns bearer token in JSON and sets
    HttpOnly access_token cookie for browser clients.
    """
    unique_email = f"cookie-test-{uuid.uuid4().hex[:8]}@example.com"
    reg_payload = {
        "company_name": "Cookie Security Ltd",
        "full_name": "Cookie Admin",
        "email": unique_email,
        "password": "SecurePassword123!",
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]
        assert "access_token" in reg_res.cookies
        cookie_val = reg_res.cookies.get("access_token")
        assert cookie_val == token

        # Test login sets cookie as well
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": unique_email, "password": "SecurePassword123!"},
        )
        assert login_res.status_code == 200
        assert "access_token" in login_res.cookies


@pytest.mark.asyncio
async def test_auth_cookie_only_access_succeeds():
    """A client sending ONLY the HttpOnly cookie (no Authorization header) is authenticated."""
    unique_email = f"cookie-auth-{uuid.uuid4().hex[:8]}@example.com"
    reg_payload = {
        "company_name": "Cookie Client Corp",
        "full_name": "Cookie User",
        "email": unique_email,
        "password": "SecurePassword123!",
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]

    # Now make request with cookie only in a fresh client
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"access_token": token},
    ) as client:
        me_res = await client.get("/api/v1/auth/me")
        assert me_res.status_code == 200
        data = me_res.json()
        assert data["email"] == unique_email


@pytest.mark.asyncio
async def test_auth_logout_clears_cookie():
    """POST /api/v1/auth/logout deletes the access_token session cookie."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        logout_res = await client.post("/api/v1/auth/logout")
        assert logout_res.status_code == 200
        # Cookie must either be removed or set to empty / expired
        set_cookie_header = logout_res.headers.get("set-cookie", "")
        assert "access_token" in set_cookie_header


# ── 4. Production Configuration Fail-Closed Tests ─────────────────────────────

def test_production_rejects_debug_true():
    """In production (ENVIRONMENT='production'), DEBUG cannot be True."""
    # When DEBUG=True and ENVIRONMENT='production', validation must fail
    with pytest.raises(ValidationError) as exc:
        Settings(
            DEBUG=True,
            ENVIRONMENT="production",
            JWT_SECRET_KEY="super-secret-key-that-is-at-least-32-chars-long",
            POSTGRES_USER="procureops",
            POSTGRES_PASSWORD="secure_prod_password_123",
            POSTGRES_DB="procureops_prod",
            GEMINI_API_KEY="valid-gemini-key",
        )
    assert "Production configuration error" in str(exc.value)


def test_production_rejects_default_postgres_password():
    """In production, POSTGRES_PASSWORD cannot be 'change_me_in_production'."""
    with pytest.raises(ValidationError) as exc:
        Settings(
            DEBUG=False,
            ENVIRONMENT="production",
            JWT_SECRET_KEY="super-secret-key-that-is-at-least-32-chars-long",
            POSTGRES_USER="procureops",
            POSTGRES_PASSWORD="change_me_in_production",
            POSTGRES_DB="procureops_prod",
            GEMINI_API_KEY="valid-gemini-key",
        )
    assert "POSTGRES_PASSWORD cannot use default" in str(exc.value)


def test_production_rejects_wildcard_cors():
    """In production, wildcard '*' in CORS_ORIGINS is prohibited with credentials."""
    with pytest.raises(ValidationError) as exc:
        Settings(
            DEBUG=False,
            ENVIRONMENT="production",
            JWT_SECRET_KEY="super-secret-key-that-is-at-least-32-chars-long",
            POSTGRES_USER="procureops",
            POSTGRES_PASSWORD="secure_prod_password_123",
            POSTGRES_DB="procureops_prod",
            GEMINI_API_KEY="valid-gemini-key",
            CORS_ORIGINS=["*"],
        )
    assert "Wildcard '*' in CORS_ORIGINS is prohibited" in str(exc.value)


def test_cors_origins_parsing_from_comma_string():
    """CORS_ORIGINS correctly parses comma-delimited strings."""
    cfg = Settings(
        DEBUG=True,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=DEV_JWT_SECRET,
        POSTGRES_USER="procureops",
        POSTGRES_PASSWORD="dev_password",
        POSTGRES_DB="procureops_dev",
        GEMINI_API_KEY="valid-gemini-key",
        CORS_ORIGINS="https://app.procureops.com, https://admin.procureops.com",
    )
    assert cfg.CORS_ORIGINS == ["https://app.procureops.com", "https://admin.procureops.com"]


# ── 5. Alembic Migration Consistency Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_alembic_database_head_consistency():
    """Verify that the database alembic_version matches the latest migration head."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        current_version = result.scalar_one_or_none()
        assert current_version in ("9b4a1c2e3f5d", "e3d4c5b6a789"), f"Expected head e3d4c5b6a789 or 9b4a1c2e3f5d, got {current_version}"


@pytest.mark.asyncio
async def test_all_model_tables_exist_in_database():
    """Verify all 21 application tables are physically present in PostgreSQL."""
    expected_tables = {
        "organizations", "users", "suppliers", "supplier_history",
        "policy_documents", "rfqs", "quote_documents", "rfq_items",
        "quotes", "quote_items", "analyses", "tco_results",
        "compliance_checks", "evidence_items", "recommendations",
        "approvals", "audit_events", "purchase_orders", "po_quality_issues",
        "email_deliveries", "po_approval_steps"
    }

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        existing_tables = {row[0] for row in result.fetchall()}

        missing_tables = expected_tables - existing_tables
        assert not missing_tables, f"Database is missing expected tables: {missing_tables}"
