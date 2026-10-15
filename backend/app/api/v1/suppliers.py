"""
app/api/v1/suppliers.py

Supplier management, performance intelligence, and order history endpoints.
Fully scoped to the authenticated tenant organization with RBAC enforcement.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_authenticated, require_employee_or_above
from app.db.session import get_db
from app.models.supplier import Supplier
from app.models.user import User
from app.services.supplier.performance import SupplierPerformanceService
from app.services.supplier.schemas import (
    PaginatedSupplierHistoryResponse,
    SupplierPerformanceResponse,
)

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


@router.get(
    "",
    response_model=list[SupplierResponse],
    summary="List all suppliers",
    description="Fetch all active suppliers belonging to the authenticated user's organization."
)
async def list_suppliers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> list[SupplierResponse]:
    result = await db.execute(
        select(Supplier)
        .where(
            Supplier.organization_id == current_user.organization_id,
            Supplier.is_active == True,
        )
        .order_by(Supplier.name.asc())
    )
    suppliers = result.scalars().all()
    return [SupplierResponse.model_validate(s) for s in suppliers]


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new supplier",
    description="Creates a new supplier record for the user's organization with duplicate detection."
)
async def create_supplier(
    request: SupplierCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee_or_above),
) -> SupplierResponse:
    org_id = current_user.organization_id
    trimmed_name = request.name.strip()

    # Duplicate check: case-insensitive name match within the same organization
    duplicate_query = select(Supplier).where(
        Supplier.organization_id == org_id,
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
            Supplier.organization_id == org_id,
            func.lower(func.trim(Supplier.email)) == func.lower(trimmed_email),
        )
        email_result = await db.execute(email_query)
        if email_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A supplier with the email '{trimmed_email}' already exists in your organization."
            )

    supplier = Supplier(
        organization_id=org_id,
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
    return SupplierResponse.model_validate(supplier)


@router.get(
    "/{supplier_id}/performance",
    response_model=SupplierPerformanceResponse,
    summary="Get supplier performance intelligence",
    description="Calculates reliability, financial totals, order counts, and quality metrics based on actual historical data."
)
async def get_supplier_performance(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> SupplierPerformanceResponse:
    # Scoped supplier query: non-disclosing 404 for cross-tenant suppliers
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.organization_id == current_user.organization_id,
        )
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tedarikçi ({supplier_id}) bulunamadı",
        )

    service = SupplierPerformanceService(db=db)
    return await service.get_supplier_performance(supplier)


@router.get(
    "/{supplier_id}/history",
    response_model=PaginatedSupplierHistoryResponse,
    summary="Get paginated supplier order history",
    description="Returns a paginated list of unified order history records (POs and legacy history) with provenance."
)
async def get_supplier_history(
    supplier_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated),
) -> PaginatedSupplierHistoryResponse:
    # Scoped supplier query: non-disclosing 404 for cross-tenant suppliers
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.organization_id == current_user.organization_id,
        )
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tedarikçi ({supplier_id}) bulunamadı",
        )

    service = SupplierPerformanceService(db=db)
    return await service.get_supplier_history(supplier, page=page, page_size=page_size)
