"""
backend/tests/auth_helper.py

Helper utilities to create real organizations, users with genuine roles,
and valid JWT tokens/headers for integration testing without any global mocks.
"""

import uuid
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.user import User, UserRole


class AuthContext(NamedTuple):
    organization: Organization
    user: User
    token: str
    headers: dict[str, str]


async def create_test_auth_context(
    role: UserRole | str = UserRole.ADMIN,
    org_name: str | None = None,
    org_id: uuid.UUID | None = None,
    user_email: str | None = None,
    is_active: bool = True,
    org_active: bool = True,
    db: AsyncSession | None = None,
) -> AuthContext:
    """
    Creates an organization (or reuses existing org_id) and a real User in the database,
    returning an AuthContext containing the organization, user, JWT token, and Authorization header.
    """
    role_value = role.value if isinstance(role, UserRole) else str(role)

    async def _setup(session: AsyncSession) -> AuthContext:
        if org_id is not None:
            org = await session.get(Organization, org_id)
            if not org:
                raise ValueError(f"Organization {org_id} not found")
        else:
            unique_hex = uuid.uuid4().hex[:8]
            name = org_name or f"Test Org {unique_hex}"
            org = Organization(
                name=name,
                slug=f"org-{unique_hex}",
                is_active=org_active,
            )
            session.add(org)
            await session.flush()

        user_hex = uuid.uuid4().hex[:8]
        email = user_email or f"{role_value}_{user_hex}@testcorp.com"
        user = User(
            organization_id=org.id,
            email=email,
            full_name=f"Test {role_value.title()} User",
            hashed_password=hash_password("Secr3tP@ss!"),
            role=role_value,
            is_active=is_active,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await session.refresh(org)

        token = create_access_token({
            "sub": str(user.id),
            "org_id": str(org.id),
            "role": role_value,
        })
        headers = {"Authorization": f"Bearer {token}"}

        return AuthContext(
            organization=org,
            user=user,
            token=token,
            headers=headers,
        )

    if db is not None:
        return await _setup(db)
    else:
        async with AsyncSessionLocal() as session:
            return await _setup(session)
