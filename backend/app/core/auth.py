"""
app/core/auth.py

Authentication and authorization dependencies for FastAPI endpoints:
- get_current_user: Extract and validate JWT bearer token, load User from DB.
- get_current_active_user: Enforce that the authenticated user is active.
- require_role: Role-based access control (RBAC) dependency factory.
"""

import uuid
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole

# HTTPBearer with auto_error=False allows us to return a uniform RFC-6750 401 Unauthorized
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract JWT bearer token from request Authorization header, decode claims,
    and fetch the corresponding User from the database.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(sub)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subject in token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).options(selectinload(User.organization)).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Ensure the authenticated user's account and organization are currently active.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account",
        )

    if not current_user.organization or not current_user.organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is inactive or suspended",
        )

    return current_user


def require_role(*allowed_roles: UserRole | str) -> Callable:
    """
    Dependency factory that enforces role-based access control (RBAC).
    Usage:
        @router.post("/items", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.MANAGER))])
        or
        @router.post("/items")
        async def create_item(user: User = Depends(require_role(UserRole.ADMIN))):
    """
    role_values = {r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles}

    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role not in role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation",
            )
        return current_user

    return role_checker


# ── Role Permission Shortcuts ──────────────────────────────────────────────────
# Admin only: organization-wide administration, policy ingest/deletion
require_admin = require_role(UserRole.ADMIN)

# Manager or Admin: approvals (standard & exception), RFQ cancellation, RFQ deletion
require_manager_or_above = require_role(UserRole.ADMIN, UserRole.MANAGER)

# Employee or above: creating/updating RFQs, items, quotes, running analysis
require_employee_or_above = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.EMPLOYEE)

# Authenticated active user: read-only access (Viewer, Employee, Manager, Admin)
require_authenticated = get_current_active_user
