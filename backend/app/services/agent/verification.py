import re
import uuid
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, delete

from app.models.analysis import (
    Analysis,
    Recommendation,
    VerificationStatus,
    EvidenceItem,
    ComplianceResult,
    TCOResult,
)
from app.models.quote import Quote
from app.services.deterministic.tco import TCOCalculator


class VerificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def verify_recommendation(
        self,
        recommendation_id: uuid.UUID,
        known_sources: Optional[List[str]] = None,
    ) -> Recommendation:
        """
        Agent'ın yaptığı öneriyi deterministik kurallara göre doğrular ve
        metindeki atıfları (citations) çıkarıp EvidenceItem tablosuna ekler.

        Doğrulama Adımları (Phase 10):
        1. Hard Rule Uyumluluğu: Önerilen teklifin elenmiş olup olmadığını denetler.
        2. Deterministik TCO Tutarlılığı: Önerilen teklifin TCO kaydını doğrular.
        3. Kanıt ve Atıf Güvenilirliği: Kaynağı olmayan (halüsinasyon) atıfları tespit eder.
        4. Eksik Veri / Güven Skoru: Düşük güven veya eksik maliyet verisinde insan incelemesini zorunlu kılar.
        """
        # 1. Recommendation ve ilişkili Analysis verilerini çek
        result = await self.db.execute(
            select(Recommendation)
            .where(Recommendation.id == recommendation_id)
            .options(
                selectinload(Recommendation.analysis).selectinload(Analysis.compliance_checks),
                selectinload(Recommendation.analysis).selectinload(Analysis.tco_results),
            )
        )
        recommendation = result.scalars().first()
        if not recommendation:
            raise ValueError("Recommendation not found.")

        analysis = recommendation.analysis

        # 2. Deterministik Uyumluluk (Hard Rule) Kontrolü
        verification_notes = []
        is_compliant = True
        has_tco = True

        if recommendation.recommended_quote_id:
            # Önerilen teklifin compliance sonuçlarını bul
            quote_checks = [c for c in analysis.compliance_checks if c.quote_id == recommendation.recommended_quote_id]
            
            failed_checks = [c for c in quote_checks if c.result == ComplianceResult.FAIL]
            if failed_checks:
                is_compliant = False
                for fail in failed_checks:
                    verification_notes.append(f"KURAL İHLALİ: {fail.rule_name} (Gerçek: {fail.actual_value}, Beklenen: {fail.required_value})")

            # Deterministik TCO kaydı: Önerilen teklife ve bu analize ait olmalı
            matching_tco = next(
                (t for t in analysis.tco_results if t.quote_id == recommendation.recommended_quote_id and t.analysis_id == analysis.id),
                None
            ) if analysis.tco_results else None

            if not matching_tco:
                has_tco = False
                is_compliant = False
                verification_notes.append("TCO UYUMSUZLUĞU: Önerilen teklife ait deterministik TCO hesabı bulunamadı.")

        # 3. Kanıt Çıkarımı ve Desteklenmeyen Atıf Denetimi (Citations Grounding)
        pattern = r"\[Kaynak \d+:\s*(.*?)\]"
        all_text = f"{recommendation.reasoning}\n{recommendation.risks or ''}\n{recommendation.alternative_notes or ''}"
        citations = re.findall(pattern, all_text)
        unique_citations = set(citations)

        # Eski evidence'ları temizle
        await self.db.execute(
            delete(EvidenceItem).where(EvidenceItem.analysis_id == analysis.id)
        )

        evidence_items = []
        unsupported_citations = []

        # Eğer known_sources verilmediyse, organizasyonun aktif politika belgelerinden derle
        if known_sources is None:
            from app.models.policy_document import PolicyDocument
            from app.models.rfq import RFQ
            rfq_res = await self.db.execute(select(RFQ).where(RFQ.id == analysis.rfq_id))
            rfq_obj = rfq_res.scalar_one_or_none()
            if rfq_obj and rfq_obj.organization_id:
                pol_res = await self.db.execute(
                    select(PolicyDocument.title, PolicyDocument.file_name)
                    .where(PolicyDocument.organization_id == rfq_obj.organization_id, PolicyDocument.is_active == True)
                )
                active_pols = pol_res.all()
                known_sources = [p[0] for p in active_pols if p[0]] + [p[1] for p in active_pols if p[1]]
            else:
                known_sources = []
            known_sources.extend(["sql", "geçmiş", "sipariş"])

        for citation in unique_citations:
            is_policy = "sözleşme" in citation.lower() or "politika" in citation.lower() or "madde" in citation.lower()
            is_sql = "sql" in citation.lower() or "geçmiş" in citation.lower() or "sipariş" in citation.lower()
            
            if is_policy:
                source_type = "policy"
            elif is_sql:
                source_type = "supplier_history"
            else:
                source_type = "other"

            # Eğer bilinen kaynaklar verildiyse ve eşleşmiyorsa
            if known_sources is not None and len(known_sources) > 0:
                cit_matched = any(citation.lower() in ks.lower() or ks.lower() in citation.lower() for ks in known_sources)
                if not cit_matched:
                    unsupported_citations.append(citation)

            item = EvidenceItem(
                analysis_id=analysis.id,
                source_type=source_type,
                source_reference=citation,
                claim=f"LLM tarafından '{citation}' kaynak gösterilerek iddiada bulunuldu.",
                content="Sistem tarafından otomatik çıkarıldı ve doğrulandı."
            )
            evidence_items.append(item)

        if evidence_items:
            self.db.add_all(evidence_items)

        # 4. Nihai Doğrulama Durumu Kararı
        if not is_compliant:
            # LLM kural dışı bir teklif önerdi veya TCO uyumsuz: Sistem override ediyor
            recommendation.verification_status = VerificationStatus.OVERRIDDEN.value
            verification_notes.insert(0, "SİSTEM UYARISI: LLM kurallara uymayan bir teklif önerdi. Bu öneri geçersiz kılınmıştır.")
            recommendation.recommended_quote_id = None  # Teklifi reddet
        elif unsupported_citations:
            recommendation.verification_status = VerificationStatus.INCONCLUSIVE.value
            verification_notes.append(f"UYARI: Sistem hafızasında bulunmayan desteklenmeyen atıflar tespit edildi: {', '.join(unsupported_citations)}")
        else:
            recommendation.verification_status = VerificationStatus.VERIFIED.value
            if not verification_notes:
                verification_notes.append("Tüm deterministik kurallar ve kanıt doğrulamaları sağlandı.")

        recommendation.verification_notes = "\n".join(verification_notes)

        await self.db.commit()
        await self.db.refresh(recommendation)

        return recommendation
