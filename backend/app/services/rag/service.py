"""
app/services/rag/service.py

RAG (Retrieval-Augmented Generation) operasyonları:
1. Uzun metinleri parçalama (Chunking)
2. Qdrant'a kaydetme (Ingestion)
3. Soruya göre en alakalı parçaları bulma (Retrieval)
"""

from typing import List, Dict, Any
from app.services.vector_store.qdrant import QdrantService


class RAGService:
    """
    Belgelerin (Politika, Sözleşme vb.) sisteme yüklenmesi ve 
    arama yapılması süreçlerini yönetir.
    """

    def __init__(self):
        self.vector_store = QdrantService()

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """
        Uzun metni, birbiriyle örtüşen (overlap) küçük parçalara (chunks) böler.
        Neden overlap? Cümlenin yarısı bir chunk'ta, diğer yarısı diğer chunk'ta
        kalırsa LLM bağlamı (context) kaybedebilir.
        """
        if not text:
            return []

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            # Bir sonraki chunk, mevcut chunk'ın son 'overlap' karakterinden başlar
            start += chunk_size - overlap

        return chunks

    async def ingest_document(
        self, 
        organization_id: str, 
        doc_id: str, 
        text: str, 
        metadata: Dict[str, Any] = None
    ):
        """
        Belgeyi parçalar ve vektör veritabanına kaydeder.
        """
        chunks = self._chunk_text(text)
        await self.vector_store.ingest_documents(
            organization_id=organization_id,
            doc_id=doc_id,
            chunks=chunks,
            metadata=metadata
        )

    async def retrieve_context(
        self, 
        organization_id: str, 
        query: str, 
        top_k: int = 3
    ) -> str:
        """
        Sorulan soruya en yakın 'top_k' adet metin parçasını bulup
        LLM'in okuyabileceği tek bir metin (context) olarak birleştirir.
        """
        results = await self.vector_store.search(
            organization_id=organization_id,
            query=query,
            limit=top_k
        )

        if not results:
            return "İlgili kurumsal bilgi bulunamadı."

        # Bulunan metinleri alt alta ekle
        context_parts = []
        for i, payload in enumerate(results, 1):
            source_doc = payload.get("source") or payload.get("source_name") or "Bilinmeyen Belge"
            text = payload.get("text", "")
            context_parts.append(f"[Kaynak {i}: {source_doc}]\n{text}\n")

        return "\n".join(context_parts)
