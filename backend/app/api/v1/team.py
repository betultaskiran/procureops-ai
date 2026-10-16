"""
app/api/v1/team.py

Team Management Endpoints for ProcureOps AI:
- GET   /api/v1/team/members              : List members belonging to current user's organization
- POST  /api/v1/team/members              : Create/invite a new team member (admin only)
- PATCH /api/v1/team/members/{id}/role    : Change member role with last-admin guard (admin only)
- POST  /api/v1/team/members/{id}/deactivate : Deactivate member with last-admin & self-guards (admin only)
- POST  /api/v1/team/members/{id}/reactivate : Reactivate a deactivated member (admin only)
"""

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin, require_authenticated
from app.core.security import MAX_PASSWORD_BYTES, hash_password
from app.db.session import get_db
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/team", tags=["Team Management"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CreateMemberRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=200, description="Full name of member")
    email: EmailStr = Field(..., description="Corporate email address")
    role: UserRole = Field(..., description="Assigned role (admin, manager, employee, viewer)")
    password: str = Field(..., min_length=8, description="Initial password (at least 8 chars, max 72 bytes)")

    @field_validator("full_name")
    @classmethod
    def check_not_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Full name must contain at least 2 non-whitespace characters")
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


class UpdateRoleRequest(BaseModel):
    role: UserRole = Field(..., description="New role for member")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/members",
    response_model=list[TeamMemberResponse],
    summary="List team members in caller's organization",
)
async def list_team_members(
    current_user: User = Depends(require_authenticated),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    """
    Returns all active and inactive users belonging exclusively to the
    authenticated caller's organization. Accessible to all authenticated roles.
    """
    stmt = (
        select(User)
        .where(User.organization_id == current_user.organization_id)
        .order_by(User.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new member to the organization",
)
async def create_team_member(
    payload: CreateMemberRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Adds a new member directly into the admin's organization.
    Enforces password complexity, email uniqueness, and tenant scoping.
    """
    normalized_email = payload.email.strip().lower()

    # Check global email conflict
    email_stmt = select(User).where(func.lower(User.email) == normalized_email)
    existing_user = (await db.execute(email_stmt)).scalar_one_or_none()
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )

    role_val = payload.role.value if isinstance(payload.role, UserRole) else str(payload.role)

    new_user = User(
        organization_id=current_user.organization_id,
        email=normalized_email,
        full_name=payload.full_name,
        role=role_val,
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )

    await db.refresh(new_user)
    return new_user


@router.patch(
    "/members/{user_id}/role",
    response_model=TeamMemberResponse,
    summary="Update a team member's role",
)
async def update_member_role(
    user_id: uuid.UUID,
    payload: UpdateRoleRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Updates the role of a team member within the same organization.
    Prevents demoting the organization's last active administrator.
    """
    stmt = select(User).where(
        User.id == user_id,
        User.organization_id == current_user.organization_id,
    )
    target_user = (await db.execute(stmt)).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found.",
        )

    new_role_val = payload.role.value if isinstance(payload.role, UserRole) else str(payload.role)

    # Last active admin protection
    if target_user.role == UserRole.ADMIN.value and new_role_val != UserRole.ADMIN.value and target_user.is_active:
        admin_count_stmt = select(func.count(User.id)).where(
            User.organization_id == current_user.organization_id,
            User.role == UserRole.ADMIN.value,
            User.is_active.is_(True),
        )
        active_admin_count = (await db.execute(admin_count_stmt)).scalar() or 0
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last active administrator of the organization.",
            )

    target_user.role = new_role_val
    await db.commit()
    await db.refresh(target_user)
    return target_user


@router.post(
    "/members/{user_id}/deactivate",
    response_model=TeamMemberResponse,
    summary="Deactivate a team member",
)
async def deactivate_team_member(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Deactivates a team member, revoking login and API access.
    Guards:
    1. Administrators cannot deactivate their own account.
    2. Cannot deactivate the organization's last active administrator.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot deactivate their own account.",
        )

    stmt = select(User).where(
        User.id == user_id,
        User.organization_id == current_user.organization_id,
    )
    target_user = (await db.execute(stmt)).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found.",
        )

    # Last active admin protection
    if target_user.role == UserRole.ADMIN.value and target_user.is_active:
        admin_count_stmt = select(func.count(User.id)).where(
            User.organization_id == current_user.organization_id,
            User.role == UserRole.ADMIN.value,
            User.is_active.is_(True),
        )
        active_admin_count = (await db.execute(admin_count_stmt)).scalar() or 0
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active administrator of the organization.",
            )

    target_user.is_active = False
    await db.commit()
    await db.refresh(target_user)
    return target_user


@router.post(
    "/members/{user_id}/reactivate",
    response_model=TeamMemberResponse,
    summary="Reactivate a team member",
)
async def reactivate_team_member(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Reactivates a previously deactivated team member.
    """
    stmt = select(User).where(
        User.id == user_id,
        User.organization_id == current_user.organization_id,
    )
    target_user = (await db.execute(stmt)).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found.",
        )

    target_user.is_active = True
    await db.commit()
    await db.refresh(target_user)
    return target_user
