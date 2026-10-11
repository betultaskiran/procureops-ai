import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.organization import Organization
from app.models.supplier import Supplier

router = APIRouter(prefix="/api/v1/suppliers", tags=["suppliers"])


class SupplierCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=300, description="Supplier company name")
    email: str | None = Field(default=None, max_length=320, description="Contact email")
    phone: str | None = Field(default=None, max_length=50, description="Contact phone")
    city: str | None = Field(default=None, max_length=100, description="City")
    country: str | None = Field(default=None, max_length=100, description="Country")
    notes: str | None = Field(default=None, description="Internal notes")


class SupplierResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    country: str | None = None
    notes: str | None = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


async def _get_current_organization(db: AsyncSession) -> Organization:
    """Mock auth / default organization lookup."""
    result = await db.execute(select(Organization).limit(1))
    org = result.scalars().first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No organization found in database"
        )
    return org


@router.get(
    "",
    response_model=list[SupplierResponse],
    summary="List all suppliers",
    description="Fetch all active suppliers belonging to the current organization."
)
async def list_suppliers(
    db: AsyncSession = Depends(get_db)
) -> list[SupplierResponse]:
    org = await _get_current_organization(db)
    result = await db.execute(
        select(Supplier)
        .where(Supplier.organization_id == org.id, Supplier.is_active == True)
        .order_by(Supplier.name.asc())
    )
    suppliers = result.scalars().all()
    return [SupplierResponse.model_validate(s) for s in suppliers]


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new supplier",
    description="Creates a new supplier record for the organization with duplicate detection."
)
async def create_supplier(
    request: SupplierCreateRequest,
    db: AsyncSession = Depends(get_db)
) -> SupplierResponse:
    org = await _get_current_organization(db)
    trimmed_name = request.name.strip()

    # Duplicate check: case-insensitive name match within the same organization
    duplicate_query = select(Supplier).where(
        Supplier.organization_id == org.id,
        func.lower(func.trim(Supplier.name)) == func.lower(trimmed_name),
    )
    existing_result = await db.execute(duplicate_query)
    existing_supplier = existing_result.scalars().first()

    if existing_supplier:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A supplier with the name '{trimmed_name}' already exists in your organization."
        )

    # Optional duplicate check by email if email is provided
    if request.email and request.email.strip():
        trimmed_email = request.email.strip()
        email_query = select(Supplier).where(
            Supplier.organization_id == org.id,
            func.lower(func.trim(Supplier.email)) == func.lower(trimmed_email),
        )
        email_result = await db.execute(email_query)
        if email_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A supplier with the email '{trimmed_email}' already exists in your organization."
            )

    supplier = Supplier(
        organization_id=org.id,
        name=trimmed_name,
        email=request.email.strip() if request.email else None,
        phone=request.phone.strip() if request.phone else None,
        city=request.city.strip() if request.city else None,
        country=request.country.strip() if request.country else None,
        notes=request.notes.strip() if request.notes else None,
        is_active=True,
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    return SupplierResponse.model_validate(supplier)
