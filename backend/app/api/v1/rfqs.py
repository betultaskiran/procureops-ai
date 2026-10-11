import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.rfq import RFQ

router = APIRouter(prefix="/api/v1/rfqs", tags=["rfqs"])

# Response Schemas

class RFQItemResponse(BaseModel):
    id: uuid.UUID
    line_number: int
    description: str
    quantity: float
    unit: str | None

    model_config = ConfigDict(from_attributes=True)

class RFQResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_id: uuid.UUID | None
    title: str
    description: str | None
    required_quantity: int | None
    required_date: date | None
    budget: float | None = None
    max_delivery_days: int | None = None
    min_warranty_months: int | None = None
    payment_terms: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime | None
    items: list[RFQItemResponse] = []

    model_config = ConfigDict(from_attributes=True)

class RFQItemCreate(BaseModel):
    description: str
    quantity: float
    unit: str | None = None

class RFQCreateRequest(BaseModel):
    title: str
    description: str | None = None
    required_quantity: int | None = None
    required_date: date | None = None
    budget: float | None = None
    max_delivery_days: int | None = None
    min_warranty_months: int | None = None
    payment_terms: str | None = None
    items: list[RFQItemCreate] = []


# Endpoints

@router.get(
    "",
    response_model=list[RFQResponse],
    summary="List all RFQs",
    description="Fetch a list of all Request for Quotations in the system."
)
async def list_rfqs(db: AsyncSession = Depends(get_db)) -> list[RFQResponse]:
    result = await db.execute(
        select(RFQ)
        .options(selectinload(RFQ.items))
        .order_by(RFQ.created_at.desc())
    )
    rfqs = result.scalars().all()
    return [RFQResponse.model_validate(rfq) for rfq in rfqs]


@router.get(
    "/{rfq_id}",
    response_model=RFQResponse,
    summary="Get a specific RFQ",
    description="Fetch a single Request for Quotation by its UUID."
)
async def get_rfq(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> RFQResponse:
    result = await db.execute(
        select(RFQ).where(RFQ.id == rfq_id).options(selectinload(RFQ.items))
    )
    rfq = result.scalars().first()
    
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFQ {rfq_id} not found"
        )
        
    return RFQResponse.model_validate(rfq)


class PurchaseOrderResponse(BaseModel):
    id: uuid.UUID
    po_number: str
    quote_id: uuid.UUID
    approval_id: uuid.UUID
    status: str
    email_sent: bool
    created_at: datetime

    model_config = {"from_attributes": True}

@router.get(
    "/{rfq_id}/purchase-orders",
    response_model=list[PurchaseOrderResponse],
    summary="Get POs for an RFQ",
)
async def get_rfq_purchase_orders(
    rfq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[PurchaseOrderResponse]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.order import PurchaseOrder
    from app.models.quote import Quote
    
    result = await db.execute(
        select(PurchaseOrder)
        .join(PurchaseOrder.quote)
        .where(Quote.rfq_id == rfq_id)
    )
    pos = result.scalars().all()
    return [PurchaseOrderResponse.model_validate(po) for po in pos]

@router.post(
    "",
    response_model=RFQResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new RFQ",
)
async def create_rfq(
    request: RFQCreateRequest,
    db: AsyncSession = Depends(get_db)
) -> RFQResponse:
    from app.models.organization import Organization
    # Fetch first organization (mock auth)
    org_result = await db.execute(select(Organization).limit(1))
    org = org_result.scalars().first()
    if not org:
        raise HTTPException(status_code=500, detail="No organization found")
    
    rfq = RFQ(
        organization_id=org.id,
        title=request.title,
        description=request.description,
        required_quantity=request.required_quantity,
        required_date=request.required_date,
        budget=request.budget,
        max_delivery_days=request.max_delivery_days,
        min_warranty_months=request.min_warranty_months,
        payment_terms=request.payment_terms,
        status="draft"
    )
    db.add(rfq)
    await db.flush()

    from app.models.rfq import RFQItem
    for i, item in enumerate(request.items, start=1):
        rfq_item = RFQItem(
            rfq_id=rfq.id,
            line_number=i,
            description=item.description,
            quantity=item.quantity,
            unit=item.unit
        )
        db.add(rfq_item)
    
    await db.commit()
    await db.refresh(rfq, ["items"])
    return RFQResponse.model_validate(rfq)

class SupplierResponse(BaseModel):
    id: uuid.UUID
    name: str
    
    model_config = {"from_attributes": True}

@router.get(
    "/suppliers/list",
    response_model=list[SupplierResponse],
    summary="List all Suppliers",
)
async def list_suppliers(
    db: AsyncSession = Depends(get_db)
) -> list[SupplierResponse]:
    from app.models.supplier import Supplier
    result = await db.execute(select(Supplier))
    suppliers = result.scalars().all()
    return [SupplierResponse.model_validate(s) for s in suppliers]
