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

    def chunk_document(
        self, 
        text: str, 
        chunk_size: int = 1200, 
        overlap: int = 150
    ) -> List[Dict[str, Any]]:
        """
        Belgeyi başlık, madde ve sayfa sınırlarını koruyarak yapılandırılmış parçalara (chunks) böler.
        Her parça için:
          - text: Parça metni
          - chunk_index: Parça dizini (0-indexed)
          - section_title: Madde veya bölüm başlığı (örn. 'MADDE 1: ONAY YETKİ MATRİSİ')
          - page_number: Parçanın ait olduğu sayfa numarası (varsayılan: 1)
          - is_header: Başlık/üstbilgi parçası olup olmadığı
        """
        if not text or not text.strip():
            return []

        import re

        # 1. Normalizasyon
        normalized = re.sub(r"\r\n", "\n", text)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()

        lines = normalized.split("\n")
        
        current_page = 1
        page_pattern = re.compile(r"^---\s*Page\s+(\d+)\s*---$", re.IGNORECASE)
        heading_pattern = re.compile(
            r"^(#{1,3}\s+|(?:MADDE|Madde|ARTICLE|Article|BÖLÜM|Bölüm)\s+\d+[:.]?)"
        )

        raw_sections = []  # List of (sec_text, page_number, heading_line)
        current_section_lines = []
        current_section_page = 1
        current_heading = None

        for line in lines:
            line_str = line.strip()
            
            # Sayfa geçişi kontrolü
            page_match = page_pattern.match(line_str)
            if page_match:
                current_page = int(page_match.group(1))
                continue
            
            if line_str == "---":
                continue

            # Yeni madde veya başlık başladı mı?
            if heading_pattern.match(line_str):
                if current_section_lines:
                    sec_text = "\n".join(current_section_lines).strip()
                    if sec_text:
                        raw_sections.append((sec_text, current_section_page, current_heading))
                    current_section_lines = []
                
                current_section_page = current_page
                current_heading = line_str
                current_section_lines.append(line_str)
            else:
                if not current_section_lines and not current_heading:
                    current_section_page = current_page
                if line_str:
                    current_section_lines.append(line_str)

        if current_section_lines:
            sec_text = "\n".join(current_section_lines).strip()
            if sec_text:
                raw_sections.append((sec_text, current_section_page, current_heading))

        if len(raw_sections) <= 1:
            paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
            raw_sections = [(p, 1, None) for p in paragraphs]

        # 3. Her bölümü yapılandırılmış chunk nesnesine dönüştür
        structured_chunks = []
        chunk_idx = 0

        for sec_text, sec_page, heading in raw_sections:
            sec_text = sec_text.strip()
            if not sec_text or len(sec_text) < 15:
                continue

            title = None
            is_header = False

            if heading:
                clean_heading = re.sub(r"^[#\s]+", "", heading).strip()
                clean_heading = re.sub(r"\*+", "", clean_heading).strip()
                title = clean_heading
                is_header = False
            else:
                first_line = sec_text.splitlines()[0].strip()
                has_metadata_keywords = any(kw in sec_text for kw in ("Belge Kodu", "Revizyon No", "Yürürlük Tarihi"))
                if len(raw_sections) > 1 and (has_metadata_keywords or (first_line.startswith("#") and chunk_idx == 0)):
                    clean_first = re.sub(r"^[#\s]+", "", first_line).strip()
                    clean_first = re.sub(r"\*+", "", clean_first).strip()
                    title = clean_first or "Belge Başlığı ve Genel Bilgiler"
                    is_header = True
                else:
                    if chunk_idx == 0 and len(raw_sections) == 1:
                        title = "Genel Hükümler"
                    else:
                        title = f"Bölüm {chunk_idx + 1}"
                    is_header = False

            if len(sec_text) > chunk_size:
                sub_paragraphs = [p.strip() for p in sec_text.split("\n\n") if p.strip()]
                cur = ""
                for p in sub_paragraphs:
                    if len(cur) + len(p) + 2 <= chunk_size:
                        cur = f"{cur}\n\n{p}".strip() if cur else p
                    else:
                        if cur and len(cur) > 25:
                            structured_chunks.append({
                                "text": cur,
                                "chunk_index": chunk_idx,
                                "section_title": title,
                                "page_number": sec_page,
                                "is_header": is_header,
                            })
                            chunk_idx += 1
                        cur = p
                if cur and len(cur) > 25:
                    structured_chunks.append({
                        "text": cur,
                        "chunk_index": chunk_idx,
                        "section_title": title,
                        "page_number": sec_page,
                        "is_header": is_header,
                    })
                    chunk_idx += 1
            else:
                if len(sec_text) > 25:
                    structured_chunks.append({
                        "text": sec_text,
                        "chunk_index": chunk_idx,
                        "section_title": title,
                        "page_number": sec_page,
                        "is_header": is_header,
                    })
                    chunk_idx += 1

        if not structured_chunks:
            structured_chunks = [{
                "text": normalized,
                "chunk_index": 0,
                "section_title": "Genel Metin",
                "page_number": 1,
                "is_header": False,
            }]

        return structured_chunks

    def _chunk_text(self, text: str, chunk_size: int = 1200, overlap: int = 150) -> List[str]:
        """
        Geriye dönük uyumluluk için chunk metinlerini liste olarak döndürür.
        """
        chunks = self.chunk_document(text, chunk_size=chunk_size, overlap=overlap)
        return [c["text"] for c in chunks]

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
        chunks = self.chunk_document(text)
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

    def format_context_from_payloads(self, results: List[Dict[str, Any]]) -> str:
        """
        Verilen arama sonuçları listesinden zengin ve okunabilir LLM bağlamı üretir.
        """
        if not results:
            return "İlgili kurumsal bilgi bulunamadı."

        context_parts = []
        for i, payload in enumerate(results, 1):
            source_doc = payload.get("title") or payload.get("source") or "Bilinmeyen Belge"
            sec_title = payload.get("section_title")
            page_num = payload.get("page_number")
            doc_type = payload.get("document_type")

            header_parts = [f"Kaynak {i}: {source_doc}"]
            if doc_type:
                header_parts.append(f"Tür: {doc_type}")
            if sec_title:
                header_parts.append(f"Madde: {sec_title}")
            if page_num:
                header_parts.append(f"Sayfa: {page_num}")

            header_str = " | ".join(header_parts)
            text = payload.get("text", "")
            context_parts.append(f"[{header_str}]\n{text}\n")

        return "\n".join(context_parts)

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

        return self.format_context_from_payloads(results)
