import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.rfq import RFQ
from app.models.analysis import Analysis, Recommendation, TCOResult
from app.models.quote import Quote
from app.models.supplier import Supplier

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class DashboardRFQResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    created_at: datetime
    
    # Resolved from latest analysis / recommendation
    recommended_supplier_name: Optional[str] = None
    recommended_tco: Optional[float] = None
    recommendation_status: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


@router.get(
    "/recent-rfqs",
    response_model=List[DashboardRFQResponse],
    summary="Get recent RFQs for the dashboard",
)
async def get_recent_rfqs(db: AsyncSession = Depends(get_db)) -> List[DashboardRFQResponse]:
    """
    Returns a flattened DTO for the dashboard's Recent RFQs table.
    Resolves the latest Analysis and its Recommendation to find the recommended supplier and TCO.
    """
    # In a real app with auth, we would filter by organization_id here:
    # where(RFQ.organization_id == current_user.organization_id)

    # To prevent N+1 queries, we eagerly load the related objects we need.
    # Note: selectinload is safe here, but for very large databases, a custom joined query might be better.
    stmt = (
        select(RFQ)
        .options(
            selectinload(RFQ.analyses).selectinload(Analysis.recommendation).selectinload(Recommendation.recommended_quote).selectinload(Quote.supplier),
            selectinload(RFQ.analyses).selectinload(Analysis.tco_results)
        )
        .order_by(desc(RFQ.created_at))
        .limit(20) # Limit for dashboard
    )
    
    result = await db.execute(stmt)
    rfqs = result.scalars().all()
    
    response_data = []
    
    for rfq in rfqs:
        dto = DashboardRFQResponse(
            id=rfq.id,
            title=rfq.title,
            status=rfq.status,
            created_at=rfq.created_at,
        )
        
        if rfq.analyses:
            # Sort analyses by created_at desc to get the latest
            latest_analysis = sorted(rfq.analyses, key=lambda x: x.created_at, reverse=True)[0]
            
            if latest_analysis.recommendation:
                rec = latest_analysis.recommendation
                dto.recommendation_status = rec.verification_status
                
                if rec.recommended_quote:
                    quote = rec.recommended_quote
                    if quote.supplier:
                        dto.recommended_supplier_name = quote.supplier.name
                    
                    # Find TCO for this quote in the latest analysis
                    for tco in latest_analysis.tco_results:
                        if tco.quote_id == quote.id:
                            dto.recommended_tco = float(tco.total_tco)
                            break
                    
                    # If TCO wasn't found in TCOResult, fallback to quote.total_price
                    if dto.recommended_tco is None:
                        dto.recommended_tco = float(quote.total_price)
                        
        response_data.append(dto)
        
    return response_data
