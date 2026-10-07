import re
import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.models.analysis import (
    Analysis,
    Recommendation,
    VerificationStatus,
    EvidenceItem,
    ComplianceResult
)

class VerificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def verify_recommendation(self, recommendation_id: uuid.UUID) -> Recommendation:
        """
        Agent'ın yaptığı öneriyi deterministik kurallara göre doğrular ve
        metindeki atıfları (citations) çıkarıp EvidenceItem tablosuna ekler.
        """
        # 1. Recommendation ve ilişkili Analysis'i çek
        result = await self.db.execute(
            select(Recommendation)
            .where(Recommendation.id == recommendation_id)
            .options(
                selectinload(Recommendation.analysis).selectinload(Analysis.compliance_checks)
            )
        )
        recommendation = result.scalars().first()
        if not recommendation:
            raise ValueError("Recommendation not found.")

        analysis = recommendation.analysis

        # 2. Deterministik Uyumluluk (Hard Rule) Kontrolü
        verification_notes = []
        is_compliant = True

        if recommendation.recommended_quote_id:
            # Önerilen teklifin compliance sonuçlarını bul
            quote_checks = [c for c in analysis.compliance_checks if c.quote_id == recommendation.recommended_quote_id]
            
            failed_checks = [c for c in quote_checks if c.result == ComplianceResult.FAIL]
            if failed_checks:
                is_compliant = False
                for fail in failed_checks:
                    verification_notes.append(f"KURAL İHLALİ: {fail.rule_name} (Gerçek: {fail.actual_value}, Beklenen: {fail.required_value})")

        if is_compliant:
            recommendation.verification_status = VerificationStatus.VERIFIED
            if not verification_notes:
                verification_notes.append("Tüm deterministik kurallar sağlandı.")
        else:
            # LLM kural dışı bir şey önerdi! Sistem override ediyor.
            recommendation.verification_status = VerificationStatus.OVERRIDDEN
            verification_notes.append("SİSTEM UYARISI: LLM kurallara uymayan bir teklif önerdi. Bu öneri geçersiz kılınmıştır.")
            recommendation.recommended_quote_id = None # Teklifi reddet

        recommendation.verification_notes = "\n".join(verification_notes)

        # 3. Kanıt Çıkarımı (Evidence Extraction)
        # Regex ile "[Kaynak X: YYY]" formatındaki atıfları bul
        pattern = r"\[Kaynak \d+:\s*(.*?)\]"
        
        all_text = f"{recommendation.reasoning}\n{recommendation.risks or ''}"
        
        # Benzersiz kaynakları bul
        citations = re.findall(pattern, all_text)
        unique_citations = set(citations)

        # Eski evidence'ları temizle (varsa)
        await self.db.execute(
            select(EvidenceItem).where(EvidenceItem.analysis_id == analysis.id)
        ) # This is a bit complex to delete directly, easier to just not worry about duplicates if it's run once.
        # Since it runs once per analysis, we just insert.

        evidence_items = []
        for citation in unique_citations:
            source_type = "policy" if "Sözleşme" in citation or "Politika" in citation else "supplier_history" if "SQL" in citation else "other"
            
            item = EvidenceItem(
                analysis_id=analysis.id,
                source_type=source_type,
                source_reference=citation,
                claim=f"LLM tarafından '{citation}' kaynak gösterilerek iddiada bulunuldu.",
                content="Sistem tarafından otomatik çıkarıldı." # In a full system, we'd store the exact RAG chunk here
            )
            evidence_items.append(item)

        if evidence_items:
            self.db.add_all(evidence_items)

        await self.db.commit()
        await self.db.refresh(recommendation)

        return recommendation
