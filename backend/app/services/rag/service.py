"""
app/services/rag/service.py

RAG (Retrieval-Augmented Generation) operasyonları:
1. Uzun metinleri parçalama (Chunking)
2. Qdrant'a kaydetme (Ingestion)
3. Soruya göre en alakalı parçaları bulma (Retrieval)
"""

from typing import List, Dict, Any, Optional
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

    def normalize_retrieved_text(self, text: str, section_title: Optional[str] = None) -> str:
        """
        Retrieved metindeki HTML entity'lerini, bozuk markdown kaçış karakterlerini
        ve mükerrer madde başlıklarını temizler.
        """
        if not text:
            return ""

        import html
        import re

        # 1. HTML entity çözümü (&#x20;, &#x42;, &amp; vb.)
        cleaned = html.unescape(text)
        cleaned = cleaned.replace("&#x20;", " ").replace("&nbsp;", " ")

        # 2. Kaçırılmış markdown imlerini temizle (\**, \###, \<strong> vb.)
        cleaned = re.sub(r"\\(\*|_|#|`|\[|\]|<|>)", r"\1", cleaned)

        # 3. Eğer section_title zaten biliniyorsa, metin başındaki mükerrer başlık satırını kaldır
        if section_title:
            norm_title = re.sub(r"[#*_\s:]+", "", section_title).lower()
            lines = cleaned.splitlines()
            if lines:
                first_line_norm = re.sub(r"[#*_\s:]+", "", lines[0]).lower()
                if norm_title in first_line_norm or (len(first_line_norm) > 5 and first_line_norm in norm_title):
                    cleaned = "\n".join(lines[1:]).strip()

        # 4. PDF soft line-break (kelime/cümle ortası satır kayması) temizliği:
        # Madde numarası (1.1, 2. vb.), tire (-), liste (* ) veya başlık (#) ile başlamayan satırları
        # önceki satırla bir boşlukla birleştirerek akıcı metin oluştur.
        paragraphs = cleaned.split("\n\n")
        rebuilt_paragraphs = []
        for p in paragraphs:
            p_lines = p.splitlines()
            if not p_lines:
                continue
            rebuilt_lines = []
            for line in p_lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if rebuilt_lines and not re.match(r"^(\d+[\.\)]|[-*#•]|MADDE\s*\d+)", stripped, re.IGNORECASE):
                    rebuilt_lines[-1] = f"{rebuilt_lines[-1]} {stripped}"
                else:
                    rebuilt_lines.append(stripped)
            rebuilt_paragraphs.append("\n".join(rebuilt_lines))
        cleaned = "\n\n".join(rebuilt_paragraphs)

        return cleaned.strip()

    @staticmethod
    def extract_query_topics(query: str) -> List[str]:
        """
        Sorgudan bağlaç ve soru kelimelerini ayıklayıp temel konu kavramlarını ve kalıplarını çıkarır.
        """
        if not query:
            return []

        import re
        normalized = query.lower().replace("’", "'").replace("“", "").replace("”", "")

        stopwords = {
            "bu", "şu", "o", "ve", "veya", "ile", "için", "göre", "kadar", "bir", "en", "çok",
            "az", "ne", "nedir", "kaç", "kaçtır", "olan", "olarak", "mı", "mi", "mu", "mü",
            "var", "yok", "ise", "de", "da", "ki", "tüm", "her", "gibi", "kendi", "sonucu",
            "süresi", "durumu", "hakkında", "ilgili", "alınır", "edilir", "yapılır", "olur",
            "hangisi", "hangi", "kim", "kimler", "kimden", "kimlerden", "tarafından", "şartı",
            "kuralı", "madde", "belge", "şirket", "şirketin", "şirkette",
            "edilmeli", "yapılmalı", "olmalı", "olmalıdır", "geç", "erken"
        }

        special_phrases = [
            "teminat mektubu", "ödeme vadesi", "yurt dışı", "avans ödemesi",
            "cayma bedeli", "cezai şart", "bütçe limiti", "garanti süresi",
            "teslimat süresi", "arıza müdahale", "onay yetkisi", "iso 9001",
            "250 bin", "250.000 tl", "1.000.000 tl", "3 iş günü"
        ]

        found_topics = []
        for sp in special_phrases:
            if sp in normalized:
                found_topics.append(sp)

        words = re.findall(r"[a-z0-9çğıöşü\.]+", normalized)
        for w in words:
            if len(w) < 3 or w in stopwords:
                continue
            stem = re.sub(
                r"(larda|lerde|lerden|lardan|lerin|ların|inde|ında|ıyla|iyle|deki|daki|nın|nin|nun|nün|ya|ye|da|de|dan|den|lar|ler|sı|si|su|sü)$",
                "",
                w
            )
            if len(stem) >= 3 and stem not in stopwords:
                found_topics.append(stem)

        return list(set(found_topics))

    @staticmethod
    def split_query_clauses(query: str) -> List[str]:
        """
        Sorguyu bağımsız alt ifadelere/sorulara ayırır.
        Soru işareti (?), noktalı virgül (;), satır sonu (\\n) ve 've', 'ayrıca', 'hem de' bağlaçları ile böler.
        Yalnızca alt ifadeler bağımsız bir yüklem veya soru kalıbı taşıyorsa (bileşik soru ise) bölme uygular.
        """
        if not query:
            return []
        import re
        raw_clauses = re.split(r"[?;\n]+|\s+(?:ve|ayrıca|hem\s+de)\s+", query.strip(), flags=re.IGNORECASE)
        parts = [rc.strip() for rc in raw_clauses if len(rc.strip()) >= 2]
        if len(parts) <= 1:
            return [query.strip()]

        clause_markers = {
            "kaç", "ne", "nedir", "nelerdir", "kim", "kimler", "hangi", "mı", "mi", "mu", "mü",
            "edilmeli", "yapılmalı", "olmalı", "olmalıdır", "alınır", "edilir", "yapılır", "olur",
            "kaçtır", "kaçdır", "gerekir", "süresi", "şartı", "orani", "oranı", "limiti", "yetkisi", "matrisi"
        }

        def has_clause_marker(t: str) -> bool:
            words = set(re.findall(r"[a-z0-9çğıöşü]+", t.lower()))
            return bool(words & clause_markers)

        # Parçaları akıllıca birleştir: Eğer bir parça bağımsız bir yüklem/marker içermiyorsa,
        # kendisinden sonraki (veya önceki) parçayla birleştirilir.
        merged = []
        current_buf = []
        for p in parts:
            current_buf.append(p)
            if has_clause_marker(p):
                merged.append(" ve ".join(current_buf))
                current_buf = []
        if current_buf:
            if merged:
                merged[-1] = merged[-1] + " ve " + " ve ".join(current_buf)
            else:
                merged.append(" ve ".join(current_buf))

        if len(merged) <= 1:
            return [query.strip()]

        return merged

    @staticmethod
    def extract_clause_topics_with_context(
        clause_topics: List[str], 
        full_query_topics: List[str]
    ) -> List[str]:
        """
        Alt ifadenin konularını çıkarır ve ana sorgudaki anahtar varlıkları (sunucu, donanım, alım vb.) korur.
        """
        domain_entities = {
            "sunucu", "donanım", "laptop", "bilgisayar", "dizüstü", 
            "tedarikçi", "alım", "yatırım", "yazılım", "cihaz"
        }
        context_entities = [t for t in full_query_topics if t in domain_entities]
        return list(set(clause_topics + context_entities))

    @staticmethod
    def check_topic_grounding(query_topics: List[str], chunk_text: str, section_title: Optional[str] = None) -> float:
        """
        Aday chunk'ın, sorgunun temel konu kavramlarıyla örtüşme oranını hesaplar.
        Eş anlamlıları ve alternatif kavramları hesaba katar.
        """
        if not query_topics:
            return 1.0

        synonyms = {
            "laptop": ["dizüstü", "bilgisayar", "donanım"],
            "notebook": ["dizüstü", "bilgisayar", "donanım"],
            "servis": ["tedarikçi", "üretici", "teknik", "destek", "müdahale"],
            "250 bin": ["250.000", "250000", "250"],
            "1 milyon": ["1.000.000", "1000000"],
            "yıl": ["sene", "ay"],
            "ay": ["yıl", "sene"],
        }

        combined_target = f"{section_title or ''} {chunk_text or ''}".lower()

        matched = 0
        for topic in query_topics:
            if topic in combined_target:
                matched += 1
                continue
            syn_list = synonyms.get(topic, [])
            if any(syn in combined_target for syn in syn_list):
                matched += 1
                continue

        return matched / len(query_topics)

    def filter_and_rank_hits(
        self,
        candidates: List[Dict[str, Any]],
        top_k: int = 3,
        min_score: float = 0.62,
        score_window: float = 0.085,
        query: Optional[str] = None,
        min_topical_overlap: float = 0.35,
    ) -> List[Dict[str, Any]]:
        """
        Retrieval sonuçlarını precision odaklı filtreler ve sıralar:
        1. Asgari alaka eşiğini denetler: BM25 eşleşmesi varsa 0.62, saf dense aramada 0.63 taban eşik uygulanır.
        2. Konusal uyum (topical grounding) denetimi: Sorgunun kavramlarıyla örtüşmeyen semantik drift parçalarını eler.
        3. Çoklu niyet (multi-intent / composite queries) desteği: Sorguda 've', 'ayrıca' gibi bağlaçlarla
           birden fazla gereksinim (örn. teslimat süresi ve garanti kapsamı) sorulduğunda, her iki konuya
           ait bağımsız maddelerin ikisini de bağlama dahil eder.
        4. En yüksek aday dahi asgari eşiği geçemiyorsa boş döner (negatif kanıt / yetersiz bilgi).
        5. Adaptif skor aralığı (top_score - score_window) dışındaki ilgisiz parçaları eler.
        6. İçerik maddeleri mevcutken kapak/üstbilgi (is_header=True) parçalarını eler.
        7. Soruyla gerçekten ilişkili olanları seçer (yapay dolgu yapmaz).
        """
        if not candidates:
            return []

        sorted_candidates = sorted(
            candidates,
            key=lambda c: float(c.get("score") or 0.0),
            reverse=True
        )

        if not query:
            top_sc = float(sorted_candidates[0].get("score") or 0.0)
            return [c for c in sorted_candidates if float(c.get("score") or 0.0) >= max(min_score, top_sc - score_window)][:top_k]

        # Sorguyu alt ifadelere ve konulara ayır
        clauses = self.split_query_clauses(query)
        full_topics = self.extract_query_topics(query)
        clause_topics_list = [
            self.extract_clause_topics_with_context(self.extract_query_topics(c), full_topics)
            for c in clauses
        ]

        # 1. Asgari eşik ve konusal uyum filtresi
        filtered = []
        for c in sorted_candidates:
            sc = float(c.get("score") or 0.0)
            sp = float(c.get("sparse_score") or 0.0)
            cand_min = min_score if sp > 0.5 else max(min_score, 0.63)
            if sc < cand_min:
                continue

            text = c.get("text", "")
            sec_title = c.get("section_title", "")

            global_overlap = self.check_topic_grounding(full_topics, text, sec_title)
            clause_overlaps = [self.check_topic_grounding(ct, text, sec_title) for ct in clause_topics_list]
            best_overlap = max([global_overlap] + clause_overlaps)

            if best_overlap < min_topical_overlap:
                continue

            c_with_meta = dict(c)
            c_with_meta["_clause_overlaps"] = clause_overlaps
            filtered.append(c_with_meta)

        if not filtered:
            return []

        top_score = float(filtered[0].get("score") or 0.0)
        has_content_candidates = any(not c.get("is_header", False) for c in filtered)

        # 2. Seçim stratejisi:
        # A) Tekil niyetli sorgu ise (len(clauses) <= 1): standart adaptive score_window uygula
        if len(clauses) <= 1:
            final_hits = []
            for c in filtered:
                sc = float(c.get("score") or 0.0)
                if sc < top_score - score_window:
                    continue
                if has_content_candidates and c.get("is_header", False):
                    continue
                c_clean = dict(c)
                c_clean.pop("_clause_overlaps", None)
                final_hits.append(c_clean)
            return final_hits[:top_k]

        # B) Çoklu niyetli (composite) sorgu ise:
        # Her bir alt ifadeyi karşılayan en iyi adayı seç
        selected_for_clauses = {}
        for clause_idx, ct in enumerate(clause_topics_list):
            best_cand_for_clause = None
            best_cand_score = -1.0
            for c in filtered:
                if has_content_candidates and c.get("is_header", False):
                    continue
                c_overlap = c.get("_clause_overlaps", [])[clause_idx] if "_clause_overlaps" in c else 0.0
                if c_overlap >= min_topical_overlap:
                    sc = float(c.get("score") or 0.0)
                    if sc > best_cand_score:
                        best_cand_score = sc
                        best_cand_for_clause = c
            if best_cand_for_clause:
                cand_key = f"{best_cand_for_clause.get('doc_id')}_{best_cand_for_clause.get('chunk_index')}"
                selected_for_clauses[cand_key] = best_cand_for_clause

        final_hits = sorted(list(selected_for_clauses.values()), key=lambda c: float(c.get("score") or 0.0), reverse=True)

        # Temizlik: yardımcı alanları kaldır
        clean_final_hits = []
        for c in final_hits:
            c_clean = dict(c)
            c_clean.pop("_clause_overlaps", None)
            clean_final_hits.append(c_clean)

        return clean_final_hits[:top_k]

    def format_context_from_payloads(self, results: List[Dict[str, Any]]) -> str:
        """
        Verilen arama sonuçları listesinden zengin ve okunabilir LLM bağlamı üretir.
        Sonuç yoksa modelin halüsinasyon görmesini engelleyecek açık negatif ifade döner.
        """
        if not results:
            return "İlgili kurumsal politika belgelerinde bu konuyla ilgili herhangi bir hüküm veya kural bulunamadı. Lütfen varsayımda bulunmadan bu kuralın politikalarda yer almadığını açıkça belirtiniz."

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
            clean_text = self.normalize_retrieved_text(payload.get("text", ""), sec_title)
            context_parts.append(f"[{header_str}]\n{clean_text}\n")

        return "\n".join(context_parts)

    async def retrieve_context(
        self, 
        organization_id: str, 
        query: str, 
        top_k: int = 3
    ) -> str:
        """
        Sorulan soruya en yakın adayları bulup adaptif filtreleme uygulayarak
        LLM'in okuyabileceği tek bir metin (context) olarak birleştirir.
        """
        try:
            results = await self.vector_store.search(
                organization_id=organization_id,
                query=query,
                limit=max(top_k * 3, 10)
            )
            filtered = self.filter_and_rank_hits(results, top_k=top_k, query=query)
            return self.format_context_from_payloads(filtered)
        except Exception as exc:
            import logging
            logging.getLogger("app.rag").warning(
                "Qdrant retrieve_context altyapı kesintisi/zaman aşımı (%s): %s",
                type(exc).__name__,
                str(exc)[:200]
            )
            return (
                "UYARI: Kurumsal politika veritabanına (Qdrant) altyapı kesintisi veya zaman aşımı nedeniyle ulaşılamadı. "
                "Politika hükümleri sorgulanamamıştır. Lütfen politika uyumunu varsaymayınız ve insan incelemesini zorunlu tutunuz."
            )
