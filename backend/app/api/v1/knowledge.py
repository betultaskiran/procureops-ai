"""
app/api/v1/knowledge.py

Kurumsal hafıza (Knowledge Base) ve RAG endpoint'leri.
Tenant-scoped to authenticated organization context with RBAC controls.
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import require_admin, require_authenticated
from app.models.user import User
from app.services.rag.service import RAGService

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

# ── Schemas ────────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    organization_id: Optional[uuid.UUID] = None  # Ignored; derived from authenticated user
    doc_id: uuid.UUID
    text_content: str
    metadata: dict | None = None


class SearchRequest(BaseModel):
    organization_id: Optional[uuid.UUID] = None  # Ignored; derived from authenticated user
    query: str
    top_k: int = 3


class SearchResult(BaseModel):
    context: str


class SuccessResponse(BaseModel):
    message: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/ingest",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a document into the Knowledge Base (Qdrant)",
    description=(
        "Verilen metni otomatik olarak küçük parçalara böler (chunking), "
        "Gemini ile vektörleştirir ve Qdrant veritabanına kaydeder. Admin yetkisi gerektirir."
    ),
)
async def ingest_document(
    request: IngestRequest,
    current_user: User = Depends(require_admin),
) -> SuccessResponse:
    rag_service = RAGService()
    try:
        # Organization ID is derived exclusively from the authenticated admin user
        await rag_service.ingest_document(
            organization_id=str(current_user.organization_id),
            doc_id=str(request.doc_id),
            text=request.text_content,
            metadata=request.metadata,
        )
        return SuccessResponse(message="Document successfully ingested into vector store.")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest document: {str(e)}",
        )


@router.post(
    "/search",
    response_model=SearchResult,
    summary="Search the Knowledge Base for context",
    description=(
        "Kullanıcının sorusunu alır, vektöre çevirir ve Qdrant'ta "
        "kullanıcının organizasyonuna ait en alakalı metin parçalarını bulup döner."
    ),
)
async def search_knowledge(
    request: SearchRequest,
    current_user: User = Depends(require_authenticated),
) -> SearchResult:
    rag_service = RAGService()
    try:
        # Organization ID is derived exclusively from authenticated user
        context = await rag_service.retrieve_context(
            organization_id=str(current_user.organization_id),
            query=request.query,
            top_k=request.top_k,
        )
        return SearchResult(context=context)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )
