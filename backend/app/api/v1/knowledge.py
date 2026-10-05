"""
app/api/v1/knowledge.py

Kurumsal hafıza (Knowledge Base) ve RAG endpoint'leri.
"""

import uuid
from typing import List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.rag.service import RAGService

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

# ── Schemas ────────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    organization_id: uuid.UUID
    doc_id: uuid.UUID
    text_content: str
    metadata: dict | None = None


class SearchRequest(BaseModel):
    organization_id: uuid.UUID
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
        "Gemini ile vektörleştirir ve Qdrant veritabanına kaydeder."
    ),
)
async def ingest_document(request: IngestRequest) -> SuccessResponse:
    rag_service = RAGService()
    try:
        await rag_service.ingest_document(
            organization_id=str(request.organization_id),
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
        "en alakalı metin parçalarını bulup birleştirilmiş bağlam (context) olarak döner."
    ),
)
async def search_knowledge(request: SearchRequest) -> SearchResult:
    rag_service = RAGService()
    try:
        context = await rag_service.retrieve_context(
            organization_id=str(request.organization_id),
            query=request.query,
            top_k=request.top_k,
        )
        return SearchResult(context=context)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )
