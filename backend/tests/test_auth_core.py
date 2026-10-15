"""
backend/tests/test_auth_core.py

Comprehensive tests for Phase 5.1 & Phase 5.1.1: Backend Authentication Core & Security Hardening.
Covers:
1. Security primitives (hash_password, verify_password, create_access_token, decode_access_token).
2. Production JWT secret validation (fail-closed in production, dev convenience in debug).
3. Bcrypt 72-byte boundary and multibyte UTF-8 password handling.
4. JWT required claims (exp claim enforcement).
5. Public registration (creates Organization + initial Admin User atomically).
6. Registration duplicate email and race-condition IntegrityError handling.
7. Registration payload validation (short password, >72 bytes, empty fields, invalid email).
8. Unique organization slug generation under name collision.
9. Successful login returns valid bearer token and user/org metadata.
10. Login rejection for incorrect password (401 Unauthorized).
11. Login rejection for nonexistent email (401 Unauthorized).
12. Inactive user login rejection (400 Bad Request).
13. Inactive organization login & /me rejection (403 Forbidden).
14. GET /api/v1/auth/me returns authenticated user & organization profile.
15. GET /api/v1/auth/me rejection on missing, expired, or malformed bearer token.
16. Fresh database role and organization authority (stale JWT claim invalidation).
17. RBAC dependency enforcement (require_role yields 403 Forbidden for unauthorized roles).
"""

from datetime import timedelta
from unittest.mock import patch
import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.auth import get_current_active_user, get_current_user, require_role
from app.core.config import DEV_JWT_SECRET, Settings, settings
from app.core.security import (
    MAX_PASSWORD_BYTES,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole


# ── 1. Production JWT Secret Validation Tests ─────────────────────────────────

def test_config_dev_default_allowed_in_debug():
    """Development mode (DEBUG=True) permits the default development secret."""
    cfg = Settings(
        DEBUG=True,
        ENVIRONMENT="development",
        JWT_SECRET_KEY=DEV_JWT_SECRET,
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        POSTGRES_DB="d",
        GEMINI_API_KEY="k",
    )
    assert cfg.JWT_SECRET_KEY == DEV_JWT_SECRET
    assert cfg.DEBUG is True


def test_config_production_rejects_default_secret():
    """Production mode (DEBUG=False) fails fast if the default dev secret is used."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            DEBUG=False,
            ENVIRONMENT="production",
            JWT_SECRET_KEY=DEV_JWT_SECRET,
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            POSTGRES_DB="d",
            GEMINI_API_KEY="k",
        )
    assert "Production configuration error" in str(exc_info.value)
    assert "JWT_SECRET_KEY cannot use the default development secret" in str(exc_info.value)
    # Ensure the secret itself is never leaked in the error
    assert DEV_JWT_SECRET not in str(exc_info.value)


def test_config_production_rejects_short_secret():
    """Production mode rejects secrets shorter than 32 characters."""
    short_secret = "short-secret-under-32-chars"
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            DEBUG=False,
            ENVIRONMENT="production",
            JWT_SECRET_KEY=short_secret,
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            POSTGRES_DB="d",
            GEMINI_API_KEY="k",
        )
    assert "Production configuration error" in str(exc_info.value)
    assert "must be at least 32 characters long" in str(exc_info.value)
    # Ensure the short secret value itself is never printed
    assert short_secret not in str(exc_info.value)


def test_config_production_accepts_valid_secret():
    """Production mode successfully starts with a unique 32+ character secret."""
    secure_secret = "super-secret-production-key-that-is-at-least-32-characters-long!"
    cfg = Settings(
        DEBUG=False,
        ENVIRONMENT="production",
        JWT_SECRET_KEY=secure_secret,
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        POSTGRES_DB="d",
        GEMINI_API_KEY="k",
    )
    assert cfg.JWT_SECRET_KEY == secure_secret
    assert cfg.DEBUG is False


def test_config_environment_production_flag_enforcement():
    """ENVIRONMENT='production' enforces strict secret rules even if DEBUG was set True."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            DEBUG=True,
            ENVIRONMENT="production",
            JWT_SECRET_KEY=DEV_JWT_SECRET,
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            POSTGRES_DB="d",
            GEMINI_API_KEY="k",
        )
    assert "Production configuration error" in str(exc_info.value)


# ── 2. Security Primitives Unit Tests ─────────────────────────────────────────

def test_password_hashing_and_verification():
    """Verify passwords are secure, salt-randomized, and never plain text."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(password, "") is False
    assert verify_password(password, "invalid_corrupted_hash") is False

    # Unique salts per call
    hashed2 = hash_password(password)
    assert hashed != hashed2
    assert verify_password(password, hashed2) is True


def test_password_72_byte_boundary_enforcement():
    """Bcrypt 72-byte boundary: exactly 72 bytes accepted; >72 bytes raises controlled error."""
    # Exactly 72 ASCII bytes
    exact_72_ascii = "A" * 72
    hashed = hash_password(exact_72_ascii)
    assert verify_password(exact_72_ascii, hashed) is True

    # 73 ASCII bytes -> raises controlled ValueError in hash_password, False in verify_password
    over_72_ascii = "A" * 73
    with pytest.raises(ValueError) as exc_info:
        hash_password(over_72_ascii)
    assert "cannot exceed 72 bytes" in str(exc_info.value)
    assert verify_password(over_72_ascii, hashed) is False

    # Multibyte UTF-8 characters: Turkish 'ş' is 2 bytes in UTF-8
    # 36 chars * 2 bytes = 72 bytes -> exactly at boundary
    exact_72_multibyte = "ş" * 36
    assert len(exact_72_multibyte.encode("utf-8")) == 72
    hashed_mb = hash_password(exact_72_multibyte)
    assert verify_password(exact_72_multibyte, hashed_mb) is True

    # 37 chars * 2 bytes = 74 bytes -> exceeds boundary
    over_72_multibyte = "ş" * 37
    assert len(over_72_multibyte.encode("utf-8")) == 74
    with pytest.raises(ValueError) as exc_info:
        hash_password(over_72_multibyte)
    assert "cannot exceed 72 bytes" in str(exc_info.value)
    assert verify_password(over_72_multibyte, hashed_mb) is False


def test_jwt_token_creation_and_decoding():
    """Verify JWT encoding, claim payload preservation, and expiration."""
    sub_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    data = {"sub": sub_id, "org_id": org_id, "role": "admin"}

    token = create_access_token(data, expires_delta=timedelta(minutes=15))
    decoded = decode_access_token(token)

    assert decoded["sub"] == sub_id
    assert decoded["org_id"] == org_id
    assert decoded["role"] == "admin"
    assert "exp" in decoded
    assert "iat" in decoded


def test_jwt_token_expiration():
    """Verify expired JWT tokens raise ExpiredSignatureError."""
    data = {"sub": str(uuid.uuid4())}
    token = create_access_token(data, expires_delta=timedelta(seconds=-10))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_jwt_token_missing_exp_claim_rejected():
    """Verify tokens crafted without an 'exp' claim are strictly rejected."""
    fake_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "admin"},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(fake_token)


def test_jwt_token_invalid_signature():
    """Verify tokens signed with a different key raise PyJWTError."""
    fake_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": 9999999999},
        "wrong-secret-key-that-is-at-least-32-bytes-long!",
        algorithm="HS256",
    )

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(fake_token)


# ── 3. Registration API Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_creates_organization_and_admin_atomically():
    """Registering creates an organization and initial admin user atomically."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_id = uuid.uuid4().hex[:6]
        payload = {
            "company_name": f"Acme Corporation {unique_id}",
            "full_name": f"Alice Admin {unique_id}",
            "email": f"alice_{unique_id}@acme.com",
            "password": "Password12345!",
        }

        res = await client.post("/api/v1/auth/register", json=payload)
        assert res.status_code == 201, res.text
        data = res.json()

        assert "access_token" in data
        assert data["token_type"] == "bearer"
        user_data = data["user"]
        assert user_data["email"] == payload["email"].lower()
        assert user_data["full_name"] == payload["full_name"]
        assert user_data["role"] == UserRole.ADMIN.value
        assert user_data["is_active"] is True
        assert "hashed_password" not in user_data  # NEVER leak password hash

        org_data = user_data["organization"]
        assert org_data is not None
        assert org_data["name"] == payload["company_name"]
        assert "acme-corporation" in org_data["slug"]

        # Confirm in database
        async with AsyncSessionLocal() as session:
            db_user = (
                await session.execute(
                    select(User).where(User.email == payload["email"].lower())
                )
            ).scalar_one()
            assert verify_password("Password12345!", db_user.hashed_password) is True
            assert str(db_user.organization_id) == str(org_data["id"])


@pytest.mark.asyncio
async def test_register_duplicate_email_conflict():
    """Duplicate email registration returns 409 Conflict."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_id = uuid.uuid4().hex[:6]
        payload = {
            "company_name": f"Company {unique_id}",
            "full_name": "Bob Duplicate",
            "email": f"bob_{unique_id}@corp.com",
            "password": "SecurePassword999!",
        }

        # First registration succeeds
        res1 = await client.post("/api/v1/auth/register", json=payload)
        assert res1.status_code == 201

        # Second registration with same email (even with different case) fails
        payload2 = payload.copy()
        payload2["email"] = payload["email"].upper()
        res2 = await client.post("/api/v1/auth/register", json=payload2)
        assert res2.status_code == 409
        assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_register_unique_slug_generation_on_name_collision():
    """Multiple companies with identical names get uniquely generated slugs."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        company_name = f"Collision Corp {uuid.uuid4().hex[:4]}"

        res1 = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": company_name,
                "full_name": "User One",
                "email": f"u1_{uuid.uuid4().hex[:6]}@collision.com",
                "password": "ValidPassword123!",
            },
        )
        assert res1.status_code == 201
        slug1 = res1.json()["user"]["organization"]["slug"]

        res2 = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": company_name,
                "full_name": "User Two",
                "email": f"u2_{uuid.uuid4().hex[:6]}@collision.com",
                "password": "ValidPassword123!",
            },
        )
        assert res2.status_code == 201
        slug2 = res2.json()["user"]["organization"]["slug"]

        assert slug1 != slug2


@pytest.mark.asyncio
async def test_register_db_integrity_error_rollback_returns_409():
    """Simulated race condition IntegrityError rolls back transaction and returns 409."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_id = uuid.uuid4().hex[:6]
        payload = {
            "company_name": f"Race Corp {unique_id}",
            "full_name": "Race User",
            "email": f"race_{unique_id}@race.com",
            "password": "ValidPassword123!",
        }

        # Patch db.commit to raise an IntegrityError as would happen in a concurrent race
        with patch("sqlalchemy.ext.asyncio.AsyncSession.commit", side_effect=IntegrityError("statement", {}, Exception("ix_users_email unique violation"))):
            res = await client.post("/api/v1/auth/register", json=payload)
            assert res.status_code == 409
            assert "already exists" in res.json()["detail"]


@pytest.mark.asyncio
async def test_register_validation_errors():
    """Registration enforces field constraints (email format, password length, 72-byte limit)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Password too short (< 8 chars)
        res = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": "Valid Company",
                "full_name": "Valid Name",
                "email": "valid@email.com",
                "password": "short",
            },
        )
        assert res.status_code == 422

        # Password exceeding 72 UTF-8 bytes (ASCII)
        res_long = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": "Valid Company",
                "full_name": "Valid Name",
                "email": "valid2@email.com",
                "password": "A" * 73,
            },
        )
        assert res_long.status_code == 422
        assert "cannot exceed 72 bytes" in res_long.text

        # Password exceeding 72 UTF-8 bytes (Multibyte Turkish 'ş' = 2 bytes)
        res_mb = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": "Valid Company",
                "full_name": "Valid Name",
                "email": "valid3@email.com",
                "password": "ş" * 37,
            },
        )
        assert res_mb.status_code == 422
        assert "cannot exceed 72 bytes" in res_mb.text

        # Invalid email format
        res = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": "Valid Company",
                "full_name": "Valid Name",
                "email": "not-an-email",
                "password": "ValidPassword123!",
            },
        )
        assert res.status_code == 422

        # Blank/empty company name
        res = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": "  ",
                "full_name": "Valid Name",
                "email": "valid@email.com",
                "password": "ValidPassword123!",
            },
        )
        assert res.status_code == 422


# ── 4. Login API Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success():
    """Successful login returns token and user info without password hash."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_id = uuid.uuid4().hex[:6]
        email = f"login_user_{unique_id}@test.com"
        password = "CorrectPassword123!"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Test Corp {unique_id}",
                "full_name": "Login User",
                "email": email,
                "password": password,
            },
        )
        assert reg_res.status_code == 201

        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_res.status_code == 200
        data = login_res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == email.lower()
        assert "hashed_password" not in data["user"]


@pytest.mark.asyncio
async def test_login_wrong_password_fails():
    """Login with wrong password returns 401 Unauthorized."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_id = uuid.uuid4().hex[:6]
        email = f"wrong_pwd_{unique_id}@test.com"

        await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Test Corp {unique_id}",
                "full_name": "Wrong Pwd User",
                "email": email,
                "password": "CorrectPassword123!",
            },
        )

        res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword456!"},
        )
        assert res.status_code == 401
        assert "Invalid email or password" in res.json()["detail"]


@pytest.mark.asyncio
async def test_login_password_over_72_bytes_produces_client_error():
    """Attempting login with a password > 72 bytes produces 422, never an unhandled 500."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "any@corp.com", "password": "B" * 73},
        )
        assert res.status_code == 422
        assert "cannot exceed 72 bytes" in res.text


@pytest.mark.asyncio
async def test_login_nonexistent_email_fails():
    """Login with nonexistent email returns 401 Unauthorized."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent_email_999@test.com", "password": "SomePassword123!"},
        )
        assert res.status_code == 401
        assert "Invalid email or password" in res.json()["detail"]


@pytest.mark.asyncio
async def test_login_inactive_user_blocked():
    """Inactive user cannot log in and receives 400 Bad Request."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_id = uuid.uuid4().hex[:6]
        email = f"inactive_{unique_id}@test.com"
        password = "ValidPassword123!"

        await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Inactive Corp {unique_id}",
                "full_name": "Inactive User",
                "email": email,
                "password": password,
            },
        )

        # Deactivate user in database
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.email == email)
            db_user = (await session.execute(stmt)).scalar_one()
            db_user.is_active = False
            await session.commit()

        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_res.status_code == 400
        assert "Inactive user account" in login_res.json()["detail"]


@pytest.mark.asyncio
async def test_login_inactive_organization_blocked():
    """Users of an inactive organization cannot log in (403 Forbidden)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_id = uuid.uuid4().hex[:6]
        email = f"inorg_{unique_id}@test.com"
        password = "ValidPassword123!"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Inactive Org Corp {unique_id}",
                "full_name": "InOrg User",
                "email": email,
                "password": password,
            },
        )
        assert reg_res.status_code == 201
        org_id = reg_res.json()["user"]["organization"]["id"]

        # Deactivate organization in database
        async with AsyncSessionLocal() as session:
            stmt = select(Organization).where(Organization.id == uuid.UUID(org_id))
            db_org = (await session.execute(stmt)).scalar_one()
            db_org.is_active = False
            await session.commit()

        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_res.status_code == 403
        assert "Organization is inactive or suspended" in login_res.json()["detail"]


# ── 5. Current User & Profile (/me) Tests ─────────────────────────────────────

@pytest.mark.asyncio
async def test_get_me_success():
    """GET /api/v1/auth/me returns current user profile and organization details."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_id = uuid.uuid4().hex[:6]
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Me Corp {unique_id}",
                "full_name": "Me User",
                "email": f"me_{unique_id}@test.com",
                "password": "Password12345!",
            },
        )
        token = reg_res.json()["access_token"]

        me_res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == f"me_{unique_id}@test.com"
        assert me_data["full_name"] == "Me User"
        assert me_data["role"] == UserRole.ADMIN.value
        assert me_data["organization"]["name"] == f"Me Corp {unique_id}"
        assert "hashed_password" not in me_data


@pytest.mark.asyncio
async def test_get_me_inactive_organization_returns_403():
    """Active user belonging to a deactivated organization is blocked with 403 Forbidden."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_id = uuid.uuid4().hex[:6]
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Deact Corp {unique_id}",
                "full_name": "Deact User",
                "email": f"deact_{unique_id}@test.com",
                "password": "Password12345!",
            },
        )
        token = reg_res.json()["access_token"]
        org_id = reg_res.json()["user"]["organization"]["id"]

        # 1. Access works initially
        res1 = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res1.status_code == 200

        # 2. Deactivate organization in database
        async with AsyncSessionLocal() as session:
            stmt = select(Organization).where(Organization.id == uuid.UUID(org_id))
            db_org = (await session.execute(stmt)).scalar_one()
            db_org.is_active = False
            await session.commit()

        # 3. Subsequent request with existing token is blocked with 403
        res2 = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res2.status_code == 403
        assert "Organization is inactive or suspended" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_get_me_missing_token_unauthorized():
    """GET /api/v1/auth/me without token returns 401 Unauthorized."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/auth/me")
        assert res.status_code == 401
        assert "WWW-Authenticate" in res.headers


@pytest.mark.asyncio
async def test_get_me_expired_token_unauthorized():
    """GET /api/v1/auth/me with expired token returns 401 Unauthorized."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        expired_token = create_access_token(
            {"sub": str(uuid.uuid4())},
            expires_delta=timedelta(seconds=-1),
        )
        res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert res.status_code == 401
        assert "expired" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_me_token_missing_exp_unauthorized():
    """GET /api/v1/auth/me with token lacking required exp claim returns 401 Unauthorized."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token_no_exp = jwt.encode(
            {"sub": str(uuid.uuid4())},
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )
        res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token_no_exp}"},
        )
        assert res.status_code == 401
        assert "validate credentials" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_me_malformed_token_unauthorized():
    """GET /api/v1/auth/me with corrupted token returns 401 Unauthorized."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )
        assert res.status_code == 401
        assert "validate credentials" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_me_nonexistent_user_token_unauthorized():
    """Token with a valid signature but non-existent user ID returns 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ghost_token = create_access_token({"sub": str(uuid.uuid4())})
        res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {ghost_token}"},
        )
        assert res.status_code == 401
        assert "User not found" in res.json()["detail"]


# ── 6. Live DB Authority & Role-Based Access Control (RBAC) Tests ─────────────

@pytest.mark.asyncio
async def test_stale_role_claim_in_token_overridden_by_fresh_database_role():
    """Token role claims are ignored; live PostgreSQL user role governs authorization."""
    # 1. Create a user initially with 'employee' role
    async with AsyncSessionLocal() as session:
        org = Organization(
            name=f"Role Corp {uuid.uuid4().hex[:4]}",
            slug=f"role-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(org)
        await session.flush()

        user = User(
            organization_id=org.id,
            email=f"mutate_{uuid.uuid4().hex[:6]}@role.com",
            full_name="Mutating Role User",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.EMPLOYEE.value,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    # 2. Token issued with "role": "employee"
    token = create_access_token({"sub": str(user_id), "org_id": str(org.id), "role": "employee"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Check initial /me returns employee
        me_res1 = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res1.status_code == 200
        assert me_res1.json()["role"] == UserRole.EMPLOYEE.value

        # 3. Promote user to 'manager' in database
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.id == user_id)
            db_user = (await session.execute(stmt)).scalar_one()
            db_user.role = UserRole.MANAGER.value
            await session.commit()

        # 4. Subsequent request with the SAME token immediately reflects 'manager'
        me_res2 = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res2.status_code == 200
        assert me_res2.json()["role"] == UserRole.MANAGER.value


@pytest.mark.asyncio
async def test_require_role_enforcement():
    """Role-based access control grants access to allowed roles and forbids others (403)."""
    # 1. Create an org with an admin, a manager, and an employee
    async with AsyncSessionLocal() as session:
        org = Organization(
            name=f"RBAC Corp {uuid.uuid4().hex[:4]}",
            slug=f"rbac-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(org)
        await session.flush()

        admin_user = User(
            organization_id=org.id,
            email=f"admin_{uuid.uuid4().hex[:6]}@rbac.com",
            full_name="Admin User",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        manager_user = User(
            organization_id=org.id,
            email=f"manager_{uuid.uuid4().hex[:6]}@rbac.com",
            full_name="Manager User",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.MANAGER.value,
            is_active=True,
        )
        employee_user = User(
            organization_id=org.id,
            email=f"employee_{uuid.uuid4().hex[:6]}@rbac.com",
            full_name="Employee User",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.EMPLOYEE.value,
            is_active=True,
        )
        session.add_all([admin_user, manager_user, employee_user])
        await session.commit()
        await session.refresh(admin_user)
        await session.refresh(manager_user)
        await session.refresh(employee_user)

    # 2. Test role dependencies directly
    admin_checker = require_role(UserRole.ADMIN)
    manager_or_admin_checker = require_role(UserRole.ADMIN, UserRole.MANAGER)

    # Admin user passes admin checker
    res = await admin_checker(current_user=admin_user)
    assert res.id == admin_user.id

    # Admin user passes manager-or-admin checker
    res = await manager_or_admin_checker(current_user=admin_user)
    assert res.id == admin_user.id

    # Manager passes manager-or-admin checker
    res = await manager_or_admin_checker(current_user=manager_user)
    assert res.id == manager_user.id

    # Manager fails admin checker -> 403 Forbidden
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await admin_checker(current_user=manager_user)
    assert exc_info.value.status_code == 403
    assert "Insufficient permissions" in exc_info.value.detail

    # Employee fails both admin and manager-or-admin checkers -> 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        await admin_checker(current_user=employee_user)
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        await manager_or_admin_checker(current_user=employee_user)
    assert exc_info.value.status_code == 403
