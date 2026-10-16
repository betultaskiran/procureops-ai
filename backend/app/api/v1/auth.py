"""
app/api/v1/auth.py

Authentication endpoints for ProcureOps AI:
- POST /api/v1/auth/register : Atomically create a new organization and initial admin user
- POST /api/v1/auth/login    : Authenticate with email/password and obtain JWT bearer token
- GET  /api/v1/auth/me       : Retrieve current authenticated user and organization details
"""

from datetime import datetime
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.auth import get_current_active_user
from app.core.security import (
    MAX_PASSWORD_BYTES,
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None
    organization: OrganizationResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=200, description="Organization / company name")
    full_name: str = Field(..., min_length=2, max_length=200, description="Full name of initial admin user")
    email: EmailStr = Field(..., description="Corporate email address")
    password: str = Field(..., min_length=8, description="Password (at least 8 characters, maximum 72 bytes)")

    @field_validator("company_name", "full_name")
    @classmethod
    def check_not_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Field must contain at least 2 non-whitespace characters")
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"Password cannot exceed {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded"
            )
        return v


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., min_length=1, description="Password (maximum 72 bytes)")

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        if len(v) < 1:
            raise ValueError("Password cannot be empty")
        if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"Password cannot exceed {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded"
            )
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Helper Functions ──────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Convert arbitrary organization name into a URL-friendly slug."""
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    s = re.sub(r"[^a-z0-9-]", "", s).strip("-")
    if not s:
        s = "company"
    return s[:80]


def _set_auth_cookie(response: Response, token: str) -> None:
    """Attach secure HttpOnly session cookie for web clients."""
    is_prod = settings.ENVIRONMENT.lower() in ("production", "prod")
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=is_prod,
        path="/",
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new organization & initial admin",
    description=(
        "Public onboarding endpoint. Atomically creates a new organization and its "
        "initial admin user, then returns an access token. Arbitrary organization assignment "
        "or non-admin role escalation is disallowed."
    ),
)
async def register(
    payload: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    normalized_email = payload.email.lower().strip()

    # 1. Pre-check: Ensure email is not already taken
    existing_user_stmt = select(User).where(func.lower(User.email) == normalized_email)
    existing_user_res = await db.execute(existing_user_stmt)
    if existing_user_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists",
        )

    # 2. Generate a unique slug for the organization
    base_slug = _slugify(payload.company_name)
    slug = base_slug
    while True:
        slug_stmt = select(Organization).where(Organization.slug == slug)
        slug_res = await db.execute(slug_stmt)
        if not slug_res.scalar_one_or_none():
            break
        slug = f"{base_slug[:70]}-{uuid.uuid4().hex[:6]}"

    # 3. Create Organization and initial admin User atomically with rollback guard
    org = Organization(
        name=payload.company_name.strip(),
        slug=slug,
        is_active=True,
    )

    try:
        db.add(org)
        await db.flush()  # Populates org.id

        hashed = hash_password(payload.password)
        user = User(
            organization_id=org.id,
            email=normalized_email,
            full_name=payload.full_name.strip(),
            hashed_password=hashed,
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        db.add(user)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        err_msg = str(exc.orig).lower() if hasattr(exc, "orig") else str(exc).lower()
        if "email" in err_msg or "ix_users_email" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email address already exists",
            )
        elif "slug" in err_msg or "organizations_slug_key" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An organization with this slug or name already exists",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registration conflict: a unique constraint was violated",
            )

    await db.refresh(user)
    await db.refresh(org)
    user.organization = org

    # 4. Generate bearer token
    token = create_access_token({
        "sub": str(user.id),
        "org_id": str(org.id),
        "role": user.role,
    })

    _set_auth_cookie(response, token)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login with email and password",
    description="Authenticate an active user and receive an access token.",
)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    normalized_email = payload.email.lower().strip()

    stmt = (
        select(User)
        .options(selectinload(User.organization))
        .where(func.lower(User.email) == normalized_email)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account",
        )

    if not user.organization or not user.organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is inactive or suspended",
        )

    token = create_access_token({
        "sub": str(user.id),
        "org_id": str(user.organization_id),
        "role": user.role,
    })

    _set_auth_cookie(response, token)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout current user",
    description="Clears the HttpOnly access_token session cookie.",
)
async def logout(response: Response):
    is_prod = settings.ENVIRONMENT.lower() in ("production", "prod")
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
        secure=is_prod,
        path="/",
    )
    return {"message": "Logged out successfully"}


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user details",
    description="Retrieve the profile and organization of the authenticated user.",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
):
    return UserResponse.model_validate(current_user)
