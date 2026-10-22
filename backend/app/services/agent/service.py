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
from sqlalchemy import select, func

from app.models.analysis import Analysis, ComplianceResult, Recommendation, AnalysisStatus
from app.models.quote import Quote
from app.models.rfq import RFQ
from app.models.supplier import SupplierHistory
from app.services.deterministic.tco import TCOCalculator
from app.services.llm import get_llm_provider
from app.services.llm.base import ExtractionConfig
from app.services.rag.service import RAGService
from app.services.agent.schemas import AgentRecommendationSchema


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_provider()
        self.rag = RAGService()

    def _build_dynamic_rag_query(self, rfq: RFQ | None, quotes: List[Quote]) -> str:
        """
        RFQ başlığı, talep edilen kalemler ve ticari gereksinimlerden kurumsal politikalara yönelik
        çoklu niyetli (multi-intent) ve hedefe odaklı bir RAG arama sorgusu oluşturur.
        """
        clauses = []
        clean_title = ""
        if rfq and rfq.title:
            clean_title = rfq.title.strip()

        category = clean_title or "Donanım ve hizmet"

        # Kalem isimleri
        item_names = []
        if rfq and hasattr(rfq, "items") and rfq.items:
            item_names = [it.description for it in rfq.items if it.description][:3]

        # 1. Garanti ve SLA kuralı
        warranty_str = f"{rfq.min_warranty_months} ay" if (rfq and rfq.min_warranty_months) else "asgari"
        clauses.append(f"{category} alımında garanti süresi {warranty_str} ve SLA şartı nedir")

        # 2. Kalemler / donanım standartları (varsa)
        if item_names:
            items_str = ", ".join(item_names)
            clauses.append(f"talep edilen {items_str} için teknik şartlar ve standartlar nedir")

        # 3. Teslimat ve lojistik kuralları
        if rfq and rfq.max_delivery_days:
            clauses.append(f"azami teslimat süresi {rfq.max_delivery_days} gün ve gecikme cezası kuralı nedir")
        else:
            clauses.append("teslimat süresi ve gecikme cezası kuralı nedir")

        # 4. Satın alma onay yetki matrisi ve bütçe limiti
        clauses.append("satın alma onay yetki limiti ve bütçe yetki matrisi nedir")

        # 5. Ödeme vadeleri ve ticari koşullar (varsa)
        if rfq and rfq.payment_terms:
            clauses.append(f"ödeme vadesi {rfq.payment_terms} ve ticari şartlar nedir")

        return " ve ".join(clauses)

    async def generate_recommendation(self, analysis_id: uuid.UUID, organization_id: str, locale: str = "tr") -> Recommendation:
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

        # RFQ ve kalemlerini çek
        rfq_res = await self.db.execute(
            select(RFQ)
            .where(RFQ.id == analysis.rfq_id)
            .options(selectinload(RFQ.items))
        )
        rfq = rfq_res.scalars().first()

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
                missing = TCOCalculator.get_missing_financial_fields(quote)
                warnings = [c.notes for c in checks if c.result == ComplianceResult.WARNING]
                eligible_quotes.append({
                    "quote_id": str(quote.id),
                    "supplier_name": quote.supplier.name,
                    "total_tco": float(tco.total_tco) if tco else 0.0,
                    "delivery_days": quote.delivery_days,
                    "warranty_months": quote.warranty_months,
                    "payment_terms": quote.payment_terms,
                    "has_incomplete_financial_data": len(missing) > 0,
                    "missing_fields": missing,
                    "warnings": warnings,
                    "extraction_confidence": float(quote.extraction_confidence) if quote.extraction_confidence is not None else None,
                    "items": [{"desc": i.description, "qty": float(i.quantity), "price": float(i.unit_price)} for i in quote.items]
                })

        # 3. RAG'dan kurumsal hafızayı (Context) çek (Tenant-safe dinamik sorgu)
        effective_org_id = str(rfq.organization_id) if rfq and rfq.organization_id else organization_id
        if not effective_org_id or effective_org_id == "None":
            rag_context = ""
        else:
            rag_query = self._build_dynamic_rag_query(rfq, quotes)
            rag_context = await self.rag.retrieve_context(
                organization_id=effective_org_id,
                query=rag_query,
                top_k=3,
                locale=locale
            )

        # 3.5 SQL'den Tedarikçi Geçmişini (Supplier Memory) çek (Phase 8)
        supplier_ids = list(set([quote.supplier_id for quote in quotes]))
        
        sql_context = ""
        if supplier_ids:
            # Aggregate metrics for each supplier
            history_query = (
                select(
                    SupplierHistory.supplier_id,
                    func.count(SupplierHistory.id).label("total_orders"),
                    func.avg(SupplierHistory.delay_days).label("avg_delay"),
                    func.sum(SupplierHistory.quality_issues).label("total_quality_issues")
                )
                .where(SupplierHistory.supplier_id.in_(supplier_ids))
                .group_by(SupplierHistory.supplier_id)
            )
            history_result = await self.db.execute(history_query)
            metrics = history_result.all()

            if metrics:
                sql_context = "--- SQL TEDARİKÇİ GEÇMİŞİ (SUPPLIER MEMORY) ---\n"
                for metric in metrics:
                    # Find supplier name
                    supplier_name = next(
                        (q.supplier.name for q in quotes if q.supplier_id == metric.supplier_id), 
                        "Bilinmeyen Tedarikçi"
                    )
                    sql_context += f"Tedarikçi: {supplier_name}\n"
                    sql_context += f"- Toplam Geçmiş Sipariş: {metric.total_orders}\n"
                    # Handle None values
                    avg_d = round(float(metric.avg_delay), 1) if metric.avg_delay is not None else 0.0
                    sql_context += f"- Ortalama Gecikme (Gün): {avg_d}\n"
                    sql_context += f"- Toplam Kalite Sorunu: {metric.total_quality_issues or 0}\n\n"

        # 4. LLM Promptunu oluştur
        prompt = self._build_prompt(eligible_quotes, eliminated_quotes, rag_context, sql_context, locale=locale)

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
        trade_off_header = "**Trade-off Analysis:**" if locale == "en" else "**Trade-off Analizi:**"
        clean_trade_off = agent_output.trade_off_analysis.strip()
        for prefix in ["**Trade-off Analysis:**", "**Trade-off Analizi:**", "Trade-off Analysis:", "Trade-off Analizi:"]:
            if clean_trade_off.startswith(prefix):
                clean_trade_off = clean_trade_off[len(prefix):].strip()
                break
        combined_reasoning = f"{agent_output.justification}\n\n{trade_off_header}\n{clean_trade_off}"
        
        human_review_text = (
            ("Yes" if agent_output.is_human_review_required else "No")
            if locale == "en"
            else ("Evet" if agent_output.is_human_review_required else "Hayır")
        )
        alt_notes = (
            f"Confidence Score: {agent_output.confidence_score}/100. Human Review Required: {human_review_text}"
            if locale == "en"
            else f"Güven Skoru: {agent_output.confidence_score}/100. İnsan Onayı Gerekli mi: {human_review_text}"
        )
        
        recommendation = Recommendation(
            analysis_id=analysis.id,
            recommended_quote_id=agent_output.recommended_quote_id,
            reasoning=combined_reasoning,
            risks=json.dumps(agent_output.risk_factors, ensure_ascii=False),
            alternative_notes=alt_notes,
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
        rag_context: str,
        sql_context: str = "",
        locale: str = "tr"
    ) -> str:
        if locale == "en":
            prompt = (
                "You are a Senior Procurement Specialist and AI Agent. "
                "Review the data below and recommend the most suitable supplier quote for the company.\n\n"
                "IMPORTANT RULE 1: When writing your analysis, NEVER use technical IDs such as 'quote_id' or UUIDs. "
                "Always refer to suppliers naturally using their 'supplier_name' (e.g., 'DEF New\\'s quote...').\n"
                "IMPORTANT RULE 2: You are strictly an advisory consultant. Never use definitive assertions such as 'This quote is approved' or 'Purchased'. "
                "Always use recommendation phrasing such as 'I recommend this quote' or 'It is advised to evaluate'. Final decisions are made by human approvers.\n"
                "IMPORTANT RULE 3 (EVIDENCE INTEGRITY & VERBATIM CITATIONS): When citing information from the 'CORPORATE MEMORY (RAG CONTEXT)' section "
                "(e.g., delay risks, ISO requirements, approval thresholds) or historical performance metrics from 'SQL SUPPLIER MEMORY' "
                "(e.g., average delay days, quality issues), you MUST explicitly cite the source using the exact format '[Source X: <document or section title>]' or '[Kaynak X: <document or section title>]'. "
                "DO NOT translate, rewrite, or alter official policy titles, article numbers (e.g., 'Madde 2.1'), or regulatory quotations—preserve the source quotation verbatim in its original language. "
                "Do not invent any corporate or historical information without citation (zero hallucinations).\n\n"
                "IMPORTANT RULE 4 (SECURITY & INCOMPLETE DATA): If the chosen quote has 'has_incomplete_financial_data' as true, "
                "or if there are warnings, or if 'extraction_confidence' is below 0.70, "
                "you MUST mark 'is_human_review_required' as true and clearly disclose this deficiency or warning in your risk factors.\n\n"
                "IMPORTANT RULE 5 (LANGUAGE): Provide your narrative, justification, trade-off analysis, and risk factors in English. "
                "However, keep official policy citations, document titles, and article numbers verbatim in their original language.\n\n"
            )
            prompt += "--- CORPORATE MEMORY (RAG CONTEXT) ---\n"
            prompt += f"{rag_context}\n\n"
            if sql_context:
                prompt += f"{sql_context}\n"
            prompt += "--- ELIMINATED QUOTES (HARD FAIL) ---\n"
            prompt += "These quotes failed deterministic compliance rules. NEVER select them. Only reference them in trade-off comparisons.\n"
            prompt += json.dumps(eliminated_quotes, indent=2, ensure_ascii=False) + "\n\n"
            prompt += "--- ELIGIBLE QUOTES (ELIGIBLE) ---\n"
            prompt += "These quotes passed all rules. Make your selection among these quotes.\n"
            prompt += json.dumps(eligible_quotes, indent=2, ensure_ascii=False) + "\n\n"
            prompt += "Task: Analyze all data, conduct a trade-off analysis, and select the best quote. Adhere strictly to the requested JSON schema."
            return prompt

        prompt = (
            "Sen kıdemli bir Satın Alma Uzmanı ve AI Agent'sın. "
            "Aşağıdaki verileri inceleyerek şirket için en uygun tedarikçi teklifini önermelisin.\n\n"
            "ÖNEMLİ KURAL 1: Analizini yazarken ASLA 'quote_id' veya UUID gibi teknik kimlik numaralarını kullanma. "
            "Her zaman 'supplier_name' (Tedarikçi Adı) alanını kullanarak akıcı bir dil kullan (Örn: 'DEF Elektronik'in teklifi...').\n"
            "ÖNEMLİ KURAL 2: Sen sadece bir danışmansın. Asla 'Bu teklif onaylanmıştır' veya 'Satın alınmıştır' gibi kesin yargılar kullanma. "
            "Her zaman 'Bu teklifi öneriyorum' veya 'Değerlendirilmesi tavsiye edilir' gibi öneri dilini kullan. Nihai kararı insanlar verecektir.\n"
            "ÖNEMLİ KURAL 3 (KANITLANABİLİRLİK): Eğer 'KURUMSAL HAFIZA (RAG CONTEXT)' bölümündeki bir bilgiyi (Örn: gecikme riski, ISO kuralları) "
            "veya 'SQL TEDARİKÇİ GEÇMİŞİ' bölümündeki geçmiş performans verilerini (Örn: ortalama gecikme günü, kalite sorunu) "
            "analizinde kullanıyorsan, bunu KESİNLİKLE kaynağına atıf yaparak yaz. Örn: '...zorunludur [Kaynak 1: Eski Sözleşme]' veya '...5 gün gecikme yaşanmıştır [Kaynak 2: SQL Geçmişi]'. "
            "Kaynağı belirtilmeyen hiçbir kurumsal veya geçmiş bilgi üretme (Halüsinasyon yapma).\n\n"
            "ÖNEMLİ KURAL 4 (GÜVENLİK VE EKSİK VERİ): Eğer seçtiğin teklifin 'has_incomplete_financial_data' değeri true ise, "
            "veya teklifte uyarılar ('warnings') varsa, ya da 'extraction_confidence' 0.70'in altındaysa, "
            "kesinlikle 'is_human_review_required' alanını true olarak işaretle ve risk faktörlerinde bu eksikliği veya uyarıyı açıkça belirt.\n\n"
            "ÖNEMLİ KURAL 5 (DİL): Gerekçe, ödünleşim (trade-off) analizi ve risk faktörleri dahil tüm analiz açıklamalarını Türkçe olarak yaz. Ancak resmî politika başlıklarını, madde numaralarını (Örn: 'Madde 2.1') ve kaynak atıflarını orijinal hâliyle koru.\n\n"
        )
        
        prompt += "--- KURUMSAL HAFIZA (RAG CONTEXT) ---\n"
        prompt += f"{rag_context}\n\n"
        
        if sql_context:
            prompt += f"{sql_context}\n"

        prompt += "--- ELENEN TEKLİFLER (HARD FAIL) ---\n"
        prompt += "Bu teklifler deterministik kural motorundan geçemedi. Bunları ASLA seçme. Sadece kıyaslama (trade-off) analizinde kullanabilirsin (Örn: A daha ucuzdu ama kurallara uymadığı için eledik).\n"
        prompt += json.dumps(eliminated_quotes, indent=2, ensure_ascii=False) + "\n\n"

        prompt += "--- UYGUN TEKLİFLER (ELIGIBLE) ---\n"
        prompt += "Bu teklifler kuralları geçti. Seçimini bu teklifler arasından yap.\n"
        prompt += json.dumps(eligible_quotes, indent=2, ensure_ascii=False) + "\n\n"

        prompt += "Görev: Tüm verileri analiz et, trade-off (ödünleşim) analizi yap ve en iyi teklifi seç. Format olarak istenen JSON şemasına kesinlikle uy."
        
        return prompt
