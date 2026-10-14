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

        # En az 2 teklif kontrolü (karşılaştırmalı çoklu analiz gereksinimi)
        if len(quotes) < 2:
            analysis.status = AnalysisStatus.FAILED
            await self.db.commit()
            raise ValueError(
                f"Karşılaştırmalı analiz için en az 2 teklif gereklidir. "
                f"Bu talep için {len(quotes)} teklif bulundu."
            )

        # Para birimi tutarlılık kontrolü (Döviz kuru doğrulaması olmadan karşılaştırma yapılamaz)
        currencies = {q.currency.strip().upper() for q in quotes if q.currency and q.currency.strip()}
        if len(currencies) > 1:
            analysis.status = AnalysisStatus.FAILED
            await self.db.commit()
            curr_str = ", ".join(sorted(currencies))
            raise ValueError(
                f"Teklifler farklı para birimleri içermektedir ({curr_str}). "
                "Doğrulanmış döviz kuru olmadan doğrudan sayısal karşılaştırmaya izin verilmez."
            )
        if any(not q.currency or not q.currency.strip() for q in quotes):
            analysis.status = AnalysisStatus.FAILED
            await self.db.commit()
            raise ValueError("Tüm tekliflerin geçerli bir para birimi belirtmesi zorunludur.")

        # Teklif belgesi parse durum kontrolü
        doc_ids = [q.quote_document_id for q in quotes if q.quote_document_id]
        if doc_ids:
            from app.models.rfq import QuoteDocument, ParseStatus
            docs_res = await self.db.execute(
                select(QuoteDocument).where(QuoteDocument.id.in_(doc_ids))
            )
            docs = docs_res.scalars().all()
            for doc in docs:
                if doc.parse_status != ParseStatus.COMPLETED and doc.parse_status != "completed":
                    analysis.status = AnalysisStatus.FAILED
                    await self.db.commit()
                    raise ValueError(
                        f"'{doc.file_name}' isimli teklif belgesinin işlenmesi henüz tamamlanmadı "
                        f"(durum: {doc.parse_status})."
                    )

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

        # Deterministik adımlar tamamlandı.
        # Analiz durumu Agent adımı sonuna kadar RUNNING olarak korunur.
        await self.db.commit()
        
        # Sonuçları tam haliyle geri döndürmek için ilişkilerle birlikte yükleyelim
        await self.db.refresh(analysis, ["tco_results", "compliance_checks"])
        
        return analysis
