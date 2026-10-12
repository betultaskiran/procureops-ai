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

    def _chunk_text(self, text: str, chunk_size: int = 1200, overlap: int = 150) -> List[str]:
        """
        Belgeyi başlık, madde ve paragraf sınırlarını koruyarak mantıksal parçalara böler.
        Kelimeleri ve cümleleri ortadan bölmez, maddelerin anlam bütünlüğünü korur.
        """
        if not text or not text.strip():
            return []

        import re

        # 1. Normalizasyon
        normalized = re.sub(r"\r\n", "\n", text)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()

        # 2. Satır satır başlık ve madde sınırlarını tespit et
        lines = normalized.split("\n")
        sections = []
        current_section = []

        heading_pattern = re.compile(
            r"^(#{1,3}\s+|(?:MADDE|Madde|ARTICLE|Article|BÖLÜM|Bölüm)\s+\d+[:.]?)"
        )

        for line in lines:
            line_str = line.strip()
            # Sayfa ayraçları veya tek başına kalan çizgileri atla
            if re.match(r"^---\s*(?:Page\s+\d+\s*---)?$", line_str, re.IGNORECASE) or line_str == "---":
                continue

            if heading_pattern.match(line_str):
                if current_section:
                    sec_text = "\n".join(current_section).strip()
                    if sec_text:
                        sections.append(sec_text)
                    current_section = []
                current_section.append(line_str)
            else:
                if line_str:
                    current_section.append(line_str)

        if current_section:
            sec_text = "\n".join(current_section).strip()
            if sec_text:
                sections.append(sec_text)

        # Eğer madde veya başlık tespit edilemediyse, çift satır sonu (paragraf) ile ayır
        if len(sections) <= 1:
            sections = [p.strip() for p in normalized.split("\n\n") if p.strip()]

        # 3. Her madde/bölümü mantıksal bir chunk olarak ayır
        chunks = []
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue

            # Eğer bölüm tek başına chunk_size'dan büyükse, paragraflar üzerinden böl
            if len(sec) > chunk_size:
                paragraphs = [p.strip() for p in sec.split("\n\n") if p.strip()]
                cur = ""
                for p in paragraphs:
                    if len(cur) + len(p) + 2 <= chunk_size:
                        cur = f"{cur}\n\n{p}".strip() if cur else p
                    else:
                        if cur:
                            chunks.append(cur)
                        cur = p
                if cur:
                    chunks.append(cur)
            else:
                chunks.append(sec)

        # 25 karakterden uzun olan geçerli parçaları döndür
        result = [c for c in chunks if len(c.strip()) > 25]
        return result or [normalized]

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

    async def delete_document(self, organization_id: str, doc_id: str):
        """
        Belirtilen belgenin vektör veritabanındaki tüm kayıtlarını siler.
        """
        await self.vector_store.delete_by_doc_id(doc_id=doc_id, organization_id=organization_id)

    async def search_documents(
        self, 
        organization_id: str, 
        query: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Sorulan soruya en alakalı metin parçalarını payload listesi olarak döner.
        """
        return await self.vector_store.search(
            organization_id=organization_id,
            query=query,
            limit=limit
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
            source_doc = payload.get("title") or payload.get("source") or payload.get("source_name") or "Bilinmeyen Belge"
            text = payload.get("text", "")
            context_parts.append(f"[Kaynak {i}: {source_doc}]\n{text}\n")

        return "\n".join(context_parts)
