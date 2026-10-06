"""
app/services/agent/service.py

Sistemin "Beyni". Deterministik sonuçları ve RAG bağlamını alıp
büyük dil modeline (LLM) karar verdiren servis.
"""

import uuid
import json
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.models.analysis import Analysis, ComplianceResult, Recommendation, AnalysisStatus
from app.models.quote import Quote
from app.services.llm import get_llm_provider
from app.services.llm.base import ExtractionConfig
from app.services.rag.service import RAGService
from app.services.agent.schemas import AgentRecommendationSchema


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_provider()
        self.rag = RAGService()

    async def generate_recommendation(self, analysis_id: uuid.UUID, organization_id: str) -> Recommendation:
        """
        Analizi alır, RAG'dan context çeker ve LLM'den trade-off analizi ister.
        """
        # 1. Analizi ve ilişkili verileri çek
        result = await self.db.execute(
            select(Analysis)
            .where(Analysis.id == analysis_id)
            .options(
                selectinload(Analysis.tco_results),
                selectinload(Analysis.compliance_checks)
            )
        )
        analysis = result.scalars().first()
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found.")

        # Tekliflerin asıl detayları (Items vs) için Quote'ları çek
        quotes_res = await self.db.execute(
            select(Quote)
            .where(Quote.rfq_id == analysis.rfq_id)
            .options(
                selectinload(Quote.items),
                selectinload(Quote.supplier)
            )
        )
        quotes: List[Quote] = list(quotes_res.scalars().all())
        quote_map = {q.id: q for q in quotes}

        # 2. Uygun (Eligible) ve Elenen (Eliminated) teklifleri ayır
        eligible_quotes = []
        eliminated_quotes = []

        for quote in quotes:
            # Quote'un compliance sonuçlarını bul
            checks = [c for c in analysis.compliance_checks if c.quote_id == quote.id]
            
            # Eğer quote.is_compliant False ise (Deterministik adımda elendiyse)
            if not quote.is_compliant:
                fail_reasons = [f"{c.rule_name}: {c.notes}" for c in checks if c.result == ComplianceResult.FAIL]
                eliminated_quotes.append({
                    "quote_id": str(quote.id),
                    "supplier_name": quote.supplier.name,
                    "reasons": fail_reasons
                })
            else:
                # Uygun teklifler için detaylı TCO ve kalem verilerini hazırla
                tco = next((t for t in analysis.tco_results if t.quote_id == quote.id), None)
                eligible_quotes.append({
                    "quote_id": str(quote.id),
                    "supplier_name": quote.supplier.name,
                    "total_tco": float(tco.total_tco) if tco else 0.0,
                    "delivery_days": quote.delivery_days,
                    "warranty_months": quote.warranty_months,
                    "payment_terms": quote.payment_terms,
                    "items": [{"desc": i.description, "qty": float(i.quantity), "price": float(i.unit_price)} for i in quote.items]
                })

        # 3. RAG'dan kurumsal hafızayı (Context) çek
        # Şimdilik genel bir arama yapıyoruz. Phase 8'de supplier geçmişini SQL'den çekeceğiz.
        rag_query = "Tedarikçi riskleri, satın alma yönergeleri ve ödeme kısıtlamaları."
        rag_context = await self.rag.retrieve_context(
            organization_id=organization_id,
            query=rag_query,
            top_k=3
        )

        # 4. LLM Promptunu oluştur
        prompt = self._build_prompt(eligible_quotes, eliminated_quotes, rag_context)

        # 5. LLM'den Yapılandırılmış Çıktı İste (Structured Output)
        config = ExtractionConfig(thinking_budget=1024)
        
        try:
            agent_output = await self.llm.extract_structured(
                prompt=prompt,
                schema=AgentRecommendationSchema,
                config=config
            )
        except Exception as e:
            analysis.status = AnalysisStatus.FAILED
            await self.db.commit()
            raise ValueError(f"Agent failed to generate recommendation: {str(e)}")

        # 6. Recommendation Kaydını Oluştur ve Veritabanına Yaz
        combined_reasoning = f"{agent_output.justification}\n\n**Trade-off Analizi:**\n{agent_output.trade_off_analysis}"
        
        recommendation = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=agent_output.recommended_quote_id,
            reasoning=combined_reasoning,
            risks=json.dumps(agent_output.risk_factors, ensure_ascii=False),
            alternative_notes=f"Güven Skoru: {agent_output.confidence_score}/100. İnsan Onayı Gerekli mi: {'Evet' if agent_output.is_human_review_required else 'Hayır'}",
        )
        self.db.add(recommendation)
        
        analysis.status = AnalysisStatus.COMPLETED
        await self.db.commit()
        await self.db.refresh(recommendation)

        return recommendation

    def _build_prompt(
        self, 
        eligible_quotes: List[Dict[str, Any]], 
        eliminated_quotes: List[Dict[str, Any]],
        rag_context: str
    ) -> str:
        prompt = (
            "Sen kıdemli bir Satın Alma Uzmanı ve AI Agent'sın. "
            "Aşağıdaki verileri inceleyerek şirket için en uygun tedarikçi teklifini önermelisin.\n\n"
            "ÖNEMLİ KURAL 1: Analizini yazarken ASLA 'quote_id' veya UUID gibi teknik kimlik numaralarını kullanma. "
            "Her zaman 'supplier_name' (Tedarikçi Adı) alanını kullanarak akıcı bir dil kullan (Örn: 'DEF Elektronik'in teklifi...').\n"
            "ÖNEMLİ KURAL 2: Sen sadece bir danışmansın. Asla 'Bu teklif onaylanmıştır' veya 'Satın alınmıştır' gibi kesin yargılar kullanma. "
            "Her zaman 'Bu teklifi öneriyorum' veya 'Değerlendirilmesi tavsiye edilir' gibi öneri dilini kullan. Nihai kararı insanlar verecektir.\n"
            "ÖNEMLİ KURAL 3 (KANITLANABİLİRLİK): Eğer 'KURUMSAL HAFIZA (RAG CONTEXT)' bölümündeki bir bilgiyi (Örn: gecikme riski, ISO kuralları) "
            "analizinde kullanıyorsan, bunu KESİNLİKLE kaynağına atıf yaparak yaz. Örn: '...zorunludur [Kaynak 1: Eski Sözleşme]'. "
            "Kaynağı belirtilmeyen hiçbir kurumsal bilgi üretme (Halüsinasyon yapma).\n\n"
        )
        
        prompt += "--- KURUMSAL HAFIZA (RAG CONTEXT) ---\n"
        prompt += f"{rag_context}\n\n"

        prompt += "--- ELENEN TEKLİFLER (HARD FAIL) ---\n"
        prompt += "Bu teklifler deterministik kural motorundan geçemedi. Bunları ASLA seçme. Sadece kıyaslama (trade-off) analizinde kullanabilirsin (Örn: A daha ucuzdu ama kurallara uymadığı için eledik).\n"
        prompt += json.dumps(eliminated_quotes, indent=2, ensure_ascii=False) + "\n\n"

        prompt += "--- UYGUN TEKLİFLER (ELIGIBLE) ---\n"
        prompt += "Bu teklifler kuralları geçti. Seçimini bu teklifler arasından yap.\n"
        prompt += json.dumps(eligible_quotes, indent=2, ensure_ascii=False) + "\n\n"

        prompt += "Görev: Tüm verileri analiz et, trade-off (ödünleşim) analizi yap ve en iyi teklifi seç. Format olarak istenen JSON şemasına kesinlikle uy."
        
        return prompt
