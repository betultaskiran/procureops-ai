"""
app/services/deterministic/orchestrator.py

Deterministik analiz sürecini (TCO ve Hard Rules) yöneten orkestratör.
"""

import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analysis import Analysis, AnalysisStatus, ComplianceResult
from app.models.quote import Quote
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.tco import TCOCalculator
from app.services.deterministic.compliance import ComplianceChecker


class DeterministicEngine:
    """
    Bir RFQ'ya ait tüm teklifleri alır, TCO hesaplar ve şirket kurallarına
    (PolicyRules) göre doğrular.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_analysis(
        self, 
        rfq_id: uuid.UUID, 
        rules: PolicyRules
    ) -> Analysis:
        """
        1. Yeni bir Analysis kaydı oluşturur.
        2. İlgili RFQ'nun tüm Quote'larını çeker.
        3. Her Quote için TCO hesaplar.
        4. Her Quote için Hard Rule (Compliance) kontrolleri yapar.
        5. Quote'un is_compliant alanını günceller.
        """
        # 1. Yeni Analysis kaydı
        analysis = Analysis(
            rfq_id=rfq_id,
            status=AnalysisStatus.RUNNING
        )
        self.db.add(analysis)
        await self.db.flush() # analysis.id oluşturulması için

        # 2. Quote'ları çek (kalemleriyle beraber)
        result = await self.db.execute(
            select(Quote)
            .where(Quote.rfq_id == rfq_id)
            .options(selectinload(Quote.items))
        )
        quotes: List[Quote] = list(result.scalars().all())

        if not quotes:
            analysis.status = AnalysisStatus.FAILED
            await self.db.commit()
            raise ValueError(f"No quotes found for RFQ {rfq_id}")

        # 3 & 4. TCO ve Compliance adımları
        for quote in quotes:
            # TCO Hesapla
            tco_result = TCOCalculator.calculate(quote=quote, analysis_id=analysis.id)
            self.db.add(tco_result)
            await self.db.flush() # TCOResult'a ait ID'nin üretilmesi için

            # Hard Rule Kontrolleri
            compliance_checks = ComplianceChecker.check_quote(
                quote=quote,
                tco_result=tco_result,
                rules=rules,
                analysis_id=analysis.id
            )
            
            is_quote_compliant = True
            for check in compliance_checks:
                self.db.add(check)
                if check.result == ComplianceResult.FAIL:
                    is_quote_compliant = False
            
            # 5. Quote'un uyumluluk durumunu güncelle
            quote.is_compliant = is_quote_compliant

        # Tüm deterministik işlemler bitti, statüyü (şimdilik) completed yapıyoruz.
        # Phase 9'da bu "LLM Reasoning" adımına devredecek.
        analysis.status = AnalysisStatus.COMPLETED
        await self.db.commit()
        
        # Sonuçları tam haliyle geri döndürmek için ilişkilerle birlikte yükleyelim
        await self.db.refresh(analysis, ["tco_results", "compliance_checks"])
        
        return analysis
