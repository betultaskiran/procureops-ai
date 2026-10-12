"""
app/api/v1/policies.py

Kurumsal politika belgeleri (Policy Documents) yönetim ve RAG ingestion API'si.
"""

import uuid
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.organization import Organization
from app.models.policy_document import DocumentType, PolicyDocument
from app.services.extraction.pdf_parser import PDFParseError, extract_text_from_pdf
from app.services.rag.service import RAGService

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


# ── Schemas ────────────────────────────────────────────────────────────────────

from datetime import datetime

class PolicyDocumentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    file_name: str
    file_path: str
    document_type: str
    is_active: bool
    is_chunked: bool
    chunk_count: Optional[int] = None
    qdrant_collection: Optional[str] = None
    processing_error: Optional[str] = None
    created_at: Optional[datetime | str] = None
    updated_at: Optional[datetime | str] = None

    model_config = {"from_attributes": True}


class PolicySearchRequest(BaseModel):
    query: str
    top_k: int = 3
    organization_id: Optional[uuid.UUID] = None


class PolicySearchHit(BaseModel):
    source: str
    doc_id: str
    chunk_index: int
    text: str
    title: Optional[str] = None
    document_type: Optional[str] = None
    section_title: Optional[str] = None
    page_number: Optional[int] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    score: Optional[float] = None
    is_header: Optional[bool] = False


class PolicySearchResponse(BaseModel):
    query: str
    context: str
    hits: List[PolicySearchHit] = []


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_default_org_id(db: AsyncSession) -> uuid.UUID:
    res = await db.execute(select(Organization).limit(1))
    org = res.scalars().first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization found. Please seed organizations first."
        )
    return org.id


def _extract_text_from_file(file_path: Path, filename: str) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(file_path)
    elif suffix in (".txt", ".md", ".json"):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    else:
        raise ValueError(f"Desteklenmeyen dosya uzantısı: {suffix}. Sadece PDF, TXT ve MD desteklenir.")


def _to_response(p: PolicyDocument) -> PolicyDocumentResponse:
    return PolicyDocumentResponse(
        id=p.id,
        organization_id=p.organization_id,
        title=p.title,
        file_name=p.file_name,
        file_path=p.file_path,
        document_type=p.document_type,
        is_active=p.is_active,
        is_chunked=p.is_chunked,
        chunk_count=p.chunk_count,
        qdrant_collection=p.qdrant_collection,
        processing_error=p.processing_error,
        created_at=p.created_at.isoformat() if p.created_at else None,
        updated_at=p.updated_at.isoformat() if p.updated_at else None,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=List[PolicyDocumentResponse], summary="List policy documents")
async def list_policies(
    organization_id: Optional[uuid.UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Organizasyona ait politika belgelerini listeler.
    """
    if not organization_id:
        organization_id = await _get_default_org_id(db)

    query = select(PolicyDocument).where(PolicyDocument.organization_id == organization_id)
    if is_active is not None:
        query = query.where(PolicyDocument.is_active == is_active)

    query = query.order_by(PolicyDocument.created_at.desc())
    result = await db.execute(query)
    policies = result.scalars().all()

    # Convert timestamps to string if needed
    response = []
    for p in policies:
        p_dict = {
            "id": p.id,
            "organization_id": p.organization_id,
            "title": p.title,
            "file_name": p.file_name,
            "file_path": p.file_path,
            "document_type": p.document_type,
            "is_active": p.is_active,
            "is_chunked": p.is_chunked,
            "chunk_count": p.chunk_count,
            "qdrant_collection": p.qdrant_collection,
            "processing_error": p.processing_error,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        response.append(PolicyDocumentResponse(**p_dict))

    return response


@router.post("/upload", response_model=PolicyDocumentResponse, status_code=status.HTTP_201_CREATED, summary="Upload & Ingest Policy Document")
async def upload_policy(
    file: UploadFile = File(..., description="Policy document file (PDF, TXT, MD)"),
    title: str = Form(..., description="Human-readable title for the policy document"),
    document_type: str = Form("procurement_policy", description="Type of document (e.g. procurement_policy, sla, code_of_conduct)"),
    organization_id: Optional[uuid.UUID] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Yeni politika belgesi yükler:
    1. Dosyayı diske kaydeder.
    2. Metni çıkarır (PDF / TXT / MD).
    3. Hata yoksa chunk'layıp Qdrant'a vektör olarak yazar.
    4. Hata durumunda hatayı DB'ye işler (is_chunked=False, processing_error=hata).
    """
    if not organization_id:
        organization_id = await _get_default_org_id(db)

    # Dosya tipi kontrolü
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".pdf", ".txt", ".md"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Desteklenmeyen dosya tipi. Yalnızca PDF, TXT veya MD kabul edilir.",
        )

    # Boyut kontrolü
    content = await file.read()
    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Dosya çok büyük. Maksimum boyut: {settings.MAX_UPLOAD_SIZE_MB} MB",
        )

    # Diske kaydet
    upload_dir = Path(settings.UPLOAD_DIR) / "policies"
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_filename = f"policy_{uuid.uuid4()}{suffix}"
    storage_path = upload_dir / storage_filename

    async with aiofiles.open(storage_path, "wb") as f:
        await f.write(content)

    # DB kaydı oluştur
    policy = PolicyDocument(
        organization_id=organization_id,
        title=title.strip(),
        file_name=file.filename or storage_filename,
        file_path=str(storage_path),
        document_type=document_type,
        is_active=True,
        is_chunked=False,
        chunk_count=0,
        qdrant_collection="knowledge_base",
        processing_error=None,
    )
    db.add(policy)
    await db.flush()

    # Metin çıkarma ve Qdrant ingestion
    rag_service = RAGService()
    try:
        extracted_text = _extract_text_from_file(storage_path, file.filename or "")
        if not extracted_text.strip():
            raise ValueError("Belgeden metin çıkarılamadı veya belge boş.")

        # Chunking ve Qdrant ingestion
        chunks = rag_service.chunk_document(extracted_text)
        if not chunks:
            raise ValueError("Belge parçalara (chunks) ayrılamadı.")

        # Eski embedding'leri temizle (varsa)
        await rag_service.delete_document(
            organization_id=str(policy.organization_id),
            doc_id=str(policy.id)
        )

        metadata = {
            "title": policy.title,
            "source": policy.title,
            "file_name": policy.file_name,
            "document_type": policy.document_type,
            "is_active": True,
        }

        await rag_service.vector_store.ingest_documents(
            organization_id=str(policy.organization_id),
            doc_id=str(policy.id),
            chunks=chunks,
            metadata=metadata,
        )

        policy.is_chunked = True
        policy.chunk_count = len(chunks)
        policy.processing_error = None

    except Exception as e:
        policy.is_chunked = False
        policy.chunk_count = 0
        policy.processing_error = f"İşleme hatası: {str(e)}"

    await db.commit()
    await db.refresh(policy)

    return PolicyDocumentResponse(
        id=policy.id,
        organization_id=policy.organization_id,
        title=policy.title,
        file_name=policy.file_name,
        file_path=policy.file_path,
        document_type=policy.document_type,
        is_active=policy.is_active,
        is_chunked=policy.is_chunked,
        chunk_count=policy.chunk_count,
        qdrant_collection=policy.qdrant_collection,
        processing_error=policy.processing_error,
        created_at=policy.created_at.isoformat() if policy.created_at else None,
        updated_at=policy.updated_at.isoformat() if policy.updated_at else None,
    )


@router.delete("/{policy_id}", status_code=status.HTTP_200_OK, summary="Delete a policy document and its embeddings")
async def delete_policy(
    policy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Politika belgesini veritabanından, diskten ve Qdrant vektör tabanından tamamen siler.
    """
    policy = await db.get(PolicyDocument, policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy document {policy_id} not found"
        )

    # 1. Qdrant'tan chunk'ları sil
    rag_service = RAGService()
    try:
        await rag_service.delete_document(
            organization_id=str(policy.organization_id),
            doc_id=str(policy.id)
        )
    except Exception as e:
        # Log hatası ancak silme akışını tamamen durdurma
        pass

    # 2. Diskten dosyayı sil
    try:
        path = Path(policy.file_path)
        if path.exists():
            path.unlink()
    except Exception:
        pass

    # 3. DB'den sil
    await db.delete(policy)
    await db.commit()

    return {"message": "Policy document and associated vector embeddings successfully deleted", "id": str(policy_id)}


@router.post("/{policy_id}/reindex", response_model=PolicyDocumentResponse, summary="Re-extract and re-index a policy document")
async def reindex_policy(
    policy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Mevcut politika belgesini yeniden parse eder, chunk'lar ve Qdrant vektör tabanını günceller.
    """
    policy = await db.get(PolicyDocument, policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy document {policy_id} not found"
        )

    file_path = Path(policy.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy file not found on disk: {policy.file_path}"
        )

    rag_service = RAGService()
    try:
        extracted_text = _extract_text_from_file(file_path, policy.file_name)
        if not extracted_text.strip():
            raise ValueError("Belgeden metin çıkarılamadı veya belge boş.")

        chunks = rag_service.chunk_document(extracted_text)
        if not chunks:
            raise ValueError("Belge parçalara (chunks) ayrılamadı.")

        # Eski embedding'leri temizle
        await rag_service.delete_document(
            organization_id=str(policy.organization_id),
            doc_id=str(policy.id)
        )

        metadata = {
            "title": policy.title,
            "source": policy.title,
            "file_name": policy.file_name,
            "document_type": policy.document_type,
            "is_active": True,
        }

        await rag_service.vector_store.ingest_documents(
            organization_id=str(policy.organization_id),
            doc_id=str(policy.id),
            chunks=chunks,
            metadata=metadata,
        )

        policy.is_chunked = True
        policy.chunk_count = len(chunks)
        policy.processing_error = None
    except Exception as e:
        policy.is_chunked = False
        policy.chunk_count = 0
        policy.processing_error = f"Yeniden indeksleme hatası: {str(e)}"

    await db.commit()
    await db.refresh(policy)

    return _to_response(policy)


@router.get("/{policy_id}/file", summary="Stream or view the original policy document file")
async def get_policy_file(
    policy_id: uuid.UUID,
    organization_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Orijinal politika belgesini görüntüler veya indirir.
    PDF dosyaları tarayıcıda doğrudan (inline) açılacak şekilde sunulur.
    Organizasyon yetkilendirmesi kontrol edilir.
    """
    policy = await db.get(PolicyDocument, policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Politika belgesi bulunamadı veya silinmiş."
        )

    if organization_id and policy.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu belgeye erişim yetkiniz bulunmamaktadır."
        )

    file_path = Path(policy.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Belge dosyası diskte bulunamadı: {policy.file_name}"
        )

    suffix = file_path.suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=policy.file_name,
        content_disposition_type="inline",
    )


@router.post("/search", response_model=PolicySearchResponse, summary="Search active policies (RAG Test)")
async def test_search_policies(
    request: PolicySearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    RAG entegrasyonunu ve anlamsal aramayı test etmek için endpoint.
    - Sadece ilgili organizasyonun aktif belgelerinden sonuç getirir.
    - Silinmiş belgeleri dışlar.
    - Doğrudan maddeleri (article chunks) önceliklendirir.
    """
    org_id = request.organization_id
    if not org_id:
        org_id = await _get_default_org_id(db)

    # 1. DB'den ilgili organizasyonun aktif belgelerini al (Silinmiş/inaktif belgeleri engelle)
    active_docs_res = await db.execute(
        select(PolicyDocument).where(
            PolicyDocument.organization_id == org_id,
            PolicyDocument.is_active == True,
        )
    )
    active_docs_map = {str(p.id): p for p in active_docs_res.scalars().all()}

    rag_service = RAGService()

    # 2. Qdrant'tan aday sonuçları çek (Yeterli çeşitlilik için top_k * 3)
    raw_hits = await rag_service.search_documents(
        organization_id=str(org_id),
        query=request.query,
        limit=max(request.top_k * 3, 10),
    )

    # 3. Yalnızca DB'de halen aktif olan belgelerin parçalarını filtrele
    valid_hits = []
    for h in raw_hits:
        doc_id = str(h.get("doc_id", ""))
        if doc_id in active_docs_map:
            doc = active_docs_map[doc_id]
            h_copy = dict(h)
            h_copy["title"] = doc.title
            h_copy["document_type"] = doc.document_type
            h_copy["file_name"] = doc.file_name
            valid_hits.append(h_copy)

    # 4. Precision odaklı filtreleme ve adaptif sıralama
    ranked_hits = rag_service.filter_and_rank_hits(
        valid_hits,
        top_k=request.top_k,
        min_score=0.62,
        score_window=0.085,
        query=request.query,
    )

    # 5. LLM bağlamını seçilen filtrelenmiş sonuçlardan üret
    context = rag_service.format_context_from_payloads(ranked_hits)

    # 6. Sonuç kartları listesini oluştur (Metin normalizasyonu ile mükerrer başlıkları arındır)
    hits = []
    for h in ranked_hits:
        sec_title = h.get("section_title")
        clean_text = rag_service.normalize_retrieved_text(h.get("text", ""), sec_title)
        hits.append(PolicySearchHit(
            source=h.get("title") or h.get("source") or "Bilinmeyen Belge",
            title=h.get("title"),
            doc_id=h.get("doc_id", ""),
            chunk_index=h.get("chunk_index", 0),
            text=clean_text,
            document_type=h.get("document_type"),
            section_title=sec_title,
            page_number=h.get("page_number", 1),
            file_name=h.get("file_name"),
            file_url=f"/api/v1/policies/{h.get('doc_id')}/file?organization_id={org_id}",
            score=round(float(h.get("score") or 0.0), 4),
            is_header=h.get("is_header", False),
        ))

    return PolicySearchResponse(
        query=request.query,
        context=context,
        hits=hits
    )
