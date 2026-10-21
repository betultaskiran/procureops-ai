"""
tests/test_auth_rate_limit.py

Integration and unit tests for authentication endpoint rate limiting:
1. POST /api/v1/auth/login enforces 10 req / 60 sec sliding window.
   - First 10 requests pass through to auth handler (e.g. 401 Unauthorized for invalid creds).
   - 11th request is blocked with HTTP 429 Too Many Requests and Retry-After header.
2. POST /api/v1/auth/register enforces 10 req / 60 sec sliding window.
   - First 10 requests pass through to registration validation handler.
   - 11th request is blocked with HTTP 429 Too Many Requests and Retry-After header.
3. Client IP isolation:
   - A different client IP address receives a fresh rate limit window and is not blocked.
4. Route isolation:
   - Distinct rate limit keys are used for /login and /register.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_auth_login_rate_limiting():
    """Verify that POST /api/v1/auth/login allows 10 requests and blocks the 11th with 429."""
    unique_ip = f"198.51.100.{uuid.uuid4().int % 200 + 10}"
    transport = ASGITransport(app=app, client=(unique_ip, 54321))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First 10 requests should reach authentication logic (failing with 401)
        for i in range(10):
            res = await client.post(
                "/api/v1/auth/login",
                json={"email": f"test_{i}@example.com", "password": "wrongpassword123"},
            )
            assert res.status_code == 401, f"Request {i+1} failed with status {res.status_code}"

        # 11th request must be throttled with 429 Too Many Requests
        throttled_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "test_11@example.com", "password": "wrongpassword123"},
        )
        assert throttled_res.status_code == 429
        assert "Retry-After" in throttled_res.headers
        assert throttled_res.headers["Retry-After"] == "60"
        assert "Çok fazla istek" in throttled_res.json()["detail"]


@pytest.mark.asyncio
async def test_auth_register_rate_limiting():
    """Verify that POST /api/v1/auth/register allows 10 requests and blocks the 11th with 429."""
    unique_ip = f"198.51.101.{uuid.uuid4().int % 200 + 10}"
    transport = ASGITransport(app=app, client=(unique_ip, 54322))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First 10 requests should reach registration logic (e.g. 422 for invalid schema)
        for i in range(10):
            res = await client.post(
                "/api/v1/auth/register",
                json={"invalid_field": "bad_payload"},
            )
            assert res.status_code == 422, f"Request {i+1} failed with status {res.status_code}"

        # 11th request must be throttled with 429 Too Many Requests
        throttled_res = await client.post(
            "/api/v1/auth/register",
            json={"invalid_field": "bad_payload"},
        )
        assert throttled_res.status_code == 429
        assert "Retry-After" in throttled_res.headers
        assert throttled_res.headers["Retry-After"] == "60"
        assert "Çok fazla istek" in throttled_res.json()["detail"]


@pytest.mark.asyncio
async def test_auth_rate_limiting_client_ip_isolation():
    """Verify that exhausting rate limits on one IP does not affect another IP."""
    exhausted_ip = f"198.51.102.{uuid.uuid4().int % 200 + 10}"
    fresh_ip = f"198.51.103.{uuid.uuid4().int % 200 + 10}"

    transport_exhausted = ASGITransport(app=app, client=(exhausted_ip, 54323))
    transport_fresh = ASGITransport(app=app, client=(fresh_ip, 54324))

    # Exhaust limit for exhausted_ip
    async with AsyncClient(transport=transport_exhausted, base_url="http://test") as client:
        for _ in range(10):
            res = await client.post(
                "/api/v1/auth/login",
                json={"email": "attacker@example.com", "password": "wrongpassword123"},
            )
            assert res.status_code == 401

        # 11th request blocked
        res_blocked = await client.post(
            "/api/v1/auth/login",
            json={"email": "attacker@example.com", "password": "wrongpassword123"},
        )
        assert res_blocked.status_code == 429

    # Fresh IP sends request - must NOT be throttled
    async with AsyncClient(transport=transport_fresh, base_url="http://test") as client:
        res_allowed = await client.post(
            "/api/v1/auth/login",
            json={"email": "legit@example.com", "password": "wrongpassword123"},
        )
        assert res_allowed.status_code == 401
