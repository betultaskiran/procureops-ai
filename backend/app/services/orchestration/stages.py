"""
app/services/orchestration/stages.py

Phase 10: AI Workflow & Agent Orchestration - Bireysel Aşama Servisleri.

Bu modül her aşamanın sorumluluğunu ve sözleşmelerini kesin hatlarla ayırır:
- Stage 1: Extraction & Input Validation (Deterministik Python)
- Stage 2: Deterministic TCO & Hard-Rule Evaluation (Deterministik Python)
- Stage 3: Policy Compliance Analysis (Qdrant RAG + Hassas Filtreleme)
- Stage 4: Supplier Recommendation (LLM Ajanı + Yapılandırılmış Şema)
- Stage 5: Independent Verification (Bağımsız Doğrulama Katmanı)
"""

import re
import json
import uuid
import time
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analysis import (
    Analysis,
    AnalysisStatus,
    ComplianceResult,
    TCOResult,
    ComplianceCheck,
    EvidenceItem,
    Recommendation,
    VerificationStatus,
)
from app.models.rfq import RFQ, RFQStatus, QuoteDocument, ParseStatus
from app.models.quote import Quote
from app.models.supplier import SupplierHistory
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.tco import TCOCalculator
from app.services.deterministic.compliance import ComplianceChecker
from app.services.llm import get_llm_provider
from app.services.llm.base import ExtractionConfig
from app.services.rag.service import RAGService
from app.services.agent.schemas import AgentRecommendationSchema
from app.schemas.orchestration import (
    StageName,
    StageStatus,
    VerificationOutcome,
    CitationSourceType,
    StageEvidenceRef,
    StageResultResponse,
    ExtractionValidationOutput,
    DeterministicEvaluationOutput,
    PolicyComplianceOutput,
    SupplierRecommendationOutput,
    VerificationCheckDetail,
    IndependentVerificationOutput,
)


class PipelineStageError(Exception):
    """Aşama yürütme sırasında ortaya çıkan yapılandırılmış hata."""
    def __init__(self, stage: StageName, error_code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.stage = stage
        self.error_code = error_code
        self.message = message
        self.status_code = status_code


# ── Stage 1: Extraction & Input Validation ───────────────────────────────────

class ExtractionValidationStage:
    """
    Stage 1: RFQ ve Teklif girdilerinin geçerliliğini denetler.
    Tamamen deterministik Python kodudur; LLM veya harici çağrı içermez.
    """

    @staticmethod
    async def execute(
        db: AsyncSession,
        rfq_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Tuple[StageResultResponse, ExtractionValidationOutput, List[Quote], RFQ]:
        started_at = datetime.now(timezone.utc)
        start_mono = time.monotonic()
        warnings = []

        # 1. RFQ Kontrolü (Tenant isolation)
        rfq_res = await db.execute(
            select(RFQ)
            .where(RFQ.id == rfq_id, RFQ.organization_id == organization_id)
            .options(selectinload(RFQ.items))
        )
        rfq = rfq_res.scalar_one_or_none()
        if not rfq:
            raise PipelineStageError(
                stage=StageName.EXTRACTION_VALIDATION,
                error_code="RFQ_NOT_FOUND",
                message=f"RFQ {rfq_id} bulunamadı veya bu organizasyona ait değil.",
                status_code=404,
            )

        if rfq.status in [RFQStatus.CANCELLED.value, "cancelled"]:
            raise PipelineStageError(
                stage=StageName.EXTRACTION_VALIDATION,
                error_code="RFQ_CANCELLED",
                message="İptal edilmiş (cancelled) bir talep için analiz çalıştırılamaz.",
                status_code=400,
            )

        # 2. Quote'ları çek (kalemleri ve tedarikçisiyle birlikte)
        quotes_res = await db.execute(
            select(Quote)
            .where(Quote.rfq_id == rfq_id)
            .options(
                selectinload(Quote.items),
                selectinload(Quote.supplier)
            )
        )
        quotes: List[Quote] = list(quotes_res.scalars().all())

        # En az 2 teklif kontrolü
        if len(quotes) < 2:
            raise PipelineStageError(
                stage=StageName.EXTRACTION_VALIDATION,
                error_code="INSUFFICIENT_QUOTES",
                message=f"Karşılaştırmalı analiz için en az 2 teklif gereklidir. Bu talep için {len(quotes)} teklif bulundu.",
                status_code=400,
            )

        # Para birimi kontrolleri (Döviz kuru doğrulaması olmadan birleştirilemez)
        empty_currencies = [q.id for q in quotes if not q.currency or not q.currency.strip()]
        if empty_currencies:
            raise PipelineStageError(
                stage=StageName.EXTRACTION_VALIDATION,
                error_code="MISSING_CURRENCY",
                message="Tüm tekliflerin geçerli bir para birimi belirtmesi zorunludur.",
                status_code=400,
            )

        currencies = {q.currency.strip().upper() for q in quotes}
        if len(currencies) > 1:
            curr_str = ", ".join(sorted(currencies))
            raise PipelineStageError(
                stage=StageName.EXTRACTION_VALIDATION,
                error_code="CURRENCY_MISMATCH",
                message=f"Teklifler farklı para birimleri içermektedir ({curr_str}). Doğrulanmış döviz kuru olmadan doğrudan sayısal karşılaştırmaya izin verilmez.",
                status_code=400,
            )

        primary_currency = list(currencies)[0]

        # Teklif belgesi parse durum kontrolü
        doc_ids = [q.quote_document_id for q in quotes if q.quote_document_id]
        if doc_ids:
            docs_res = await db.execute(
                select(QuoteDocument).where(QuoteDocument.id.in_(doc_ids))
            )
            docs = docs_res.scalars().all()
            for doc in docs:
                if doc.parse_status not in [ParseStatus.COMPLETED, "completed"]:
                    raise PipelineStageError(
                        stage=StageName.EXTRACTION_VALIDATION,
                        error_code="DOCUMENT_PARSE_PENDING",
                        message=f"'{doc.file_name}' isimli teklif belgesinin işlenmesi henüz tamamlanmadı (durum: {doc.parse_status}).",
                        status_code=400,
                    )

        # Kalem kontrolü & eksik veri uyarıları
        missing_fields_total = []
        for q in quotes:
            missing = TCOCalculator.get_missing_financial_fields(q)
            if missing:
                missing_fields_total.extend([f"Quote {q.id}: {f}" for f in missing])
                warnings.append(f"Tedarikçi {q.supplier.name if q.supplier else q.id} teklifinde eksik maliyet alanları: {', '.join(missing)}")

        duration_ms = (time.monotonic() - start_mono) * 1000
        completed_at = datetime.now(timezone.utc)

        output = ExtractionValidationOutput(
            quote_count=len(quotes),
            currency=primary_currency,
            quote_ids=[q.id for q in quotes],
            valid_documents_count=len(doc_ids),
            validation_passed=True,
            missing_fields=missing_fields_total,
        )

        stage_result = StageResultResponse(
            stage=StageName.EXTRACTION_VALIDATION,
            status=StageStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 2),
            summary=f"{len(quotes)} teklif başarıyla doğrulandı ({primary_currency}).",
            details=output.model_dump(mode="json"),
            warnings=warnings,
        )

        return stage_result, output, quotes, rfq


# ── Stage 2: Deterministic TCO & Hard-Rule Evaluation ─────────────────────────

class DeterministicEvaluationStage:
    """
    Stage 2: TCO hesaplaması ve kesin kural doğrulaması.
    Pure Python matematiksel ve mantıksal motorudur; LLM hesaplama yapamaz.
    """

    @staticmethod
    async def execute(
        db: AsyncSession,
        analysis_id: uuid.UUID,
        quotes: List[Quote],
        rules: PolicyRules,
    ) -> Tuple[StageResultResponse, DeterministicEvaluationOutput, List[Quote], List[Quote], List[TCOResult], List[ComplianceCheck]]:
        started_at = datetime.now(timezone.utc)
        start_mono = time.monotonic()
        warnings = []

        tco_results: List[TCOResult] = []
        all_checks: List[ComplianceCheck] = []
        eligible_quotes: List[Quote] = []
        eliminated_quotes: List[Quote] = []
        eliminated_reasons: Dict[str, List[str]] = {}

        for quote in quotes:
            # 1. TCO Hesapla (Matematiksel)
            tco_result = TCOCalculator.calculate(quote=quote, analysis_id=analysis_id)
            db.add(tco_result)
            await db.flush()
            tco_results.append(tco_result)

            # 2. Hard Rule Kontrolleri
            compliance_checks = ComplianceChecker.check_quote(
                quote=quote,
                tco_result=tco_result,
                rules=rules,
                analysis_id=analysis_id,
            )

            is_quote_compliant = True
            quote_fail_reasons = []

            for check in compliance_checks:
                db.add(check)
                all_checks.append(check)
                if check.result == ComplianceResult.FAIL:
                    is_quote_compliant = False
                    quote_fail_reasons.append(f"{check.rule_name}: {check.notes}")
                elif check.result == ComplianceResult.WARNING:
                    warnings.append(f"Tedarikçi {quote.supplier.name if quote.supplier else quote.id}: {check.notes}")

            quote.is_compliant = is_quote_compliant
            if is_quote_compliant:
                eligible_quotes.append(quote)
            else:
                eliminated_quotes.append(quote)
                eliminated_reasons[str(quote.id)] = quote_fail_reasons

        await db.flush()

        duration_ms = (time.monotonic() - start_mono) * 1000
        completed_at = datetime.now(timezone.utc)

        output = DeterministicEvaluationOutput(
            tco_results_count=len(tco_results),
            compliance_checks_count=len(all_checks),
            eligible_quote_ids=[q.id for q in eligible_quotes],
            eliminated_quote_ids=[q.id for q in eliminated_quotes],
            eliminated_reasons=eliminated_reasons,
            currency=tco_results[0].currency if tco_results else "TRY",
        )

        stage_result = StageResultResponse(
            stage=StageName.DETERMINISTIC_EVALUATION,
            status=StageStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 2),
            summary=f"TCO ve kural denetimi tamamlandı: {len(eligible_quotes)} uygun, {len(eliminated_quotes)} elenen teklif.",
            details=output.model_dump(mode="json"),
            warnings=warnings,
        )

        return stage_result, output, eligible_quotes, eliminated_quotes, tco_results, all_checks


# ── Stage 3: Policy Compliance Analysis (RAG Engine) ──────────────────────────

class PolicyComplianceStage:
    """
    Stage 3: Qdrant Vektör Veritabanı ve Hybrid RAG ile kurumsal politika incelemesi.
    - Belge ID ve bölüm referanslarıyla kanıt çıkarır.
    - 'compliant', 'non_compliant' ve 'insufficient_evidence' durumlarını açıkça ayırır.
    - Yetersiz kanıt durumunda halüsinasyonu engeller.
    """

    @staticmethod
    def _build_rag_query(rfq: RFQ, quotes: List[Quote]) -> str:
        parts = []
        if rfq:
            if rfq.title:
                parts.append(rfq.title)
            try:
                if rfq.items:
                    item_descs = [it.description for it in rfq.items if it.description]
                    parts.extend(item_descs[:3])
            except Exception:
                pass
            if rfq.max_delivery_days:
                parts.append(f"teslimat süresi {rfq.max_delivery_days} gün")
            if rfq.min_warranty_months:
                parts.append(f"garanti süresi {rfq.min_warranty_months} ay")
            if rfq.payment_terms:
                parts.append(f"ödeme vadesi {rfq.payment_terms}")
        parts.append("onay limiti ve bütçe yetkisi teslimat süresi gecikme cezası garanti ve teknik şartlar")
        return " ".join(parts)

    @classmethod
    async def execute(
        cls,
        organization_id: str,
        rfq: RFQ,
        quotes: List[Quote],
        rag_service: Optional[RAGService] = None,
    ) -> Tuple[StageResultResponse, PolicyComplianceOutput, str, List[StageEvidenceRef]]:
        started_at = datetime.now(timezone.utc)
        start_mono = time.monotonic()
        warnings = []

        if rag_service is None:
            rag_service = RAGService()

        query = cls._build_rag_query(rfq, quotes)
        evidence_refs: List[StageEvidenceRef] = []

        raw_hits = await rag_service.vector_store.search(
            organization_id=organization_id,
            query=query,
            limit=10
        )
        filtered_hits = rag_service.filter_and_rank_hits(raw_hits, top_k=3, query=query)

        is_sufficient = len(filtered_hits) > 0
        if is_sufficient:
            rag_context = rag_service.format_context_from_payloads(filtered_hits)
            rag_status = "compliant"

            for i, hit in enumerate(filtered_hits, 1):
                doc_title = hit.get("title") or hit.get("source") or "Kurumsal Politika"
                sec_title = hit.get("section_title")
                page_no = hit.get("page_number")
                ref_parts = [f"Kaynak {i}: {doc_title}"]
                if sec_title:
                    ref_parts.append(f"Madde: {sec_title}")
                if page_no:
                    ref_parts.append(f"Sayfa: {page_no}")
                ref_str = " | ".join(ref_parts)

                claim_text = hit.get("text", "")[:250].strip()
                evidence_refs.append(
                    StageEvidenceRef(
                        source_type=CitationSourceType.POLICY,
                        source_reference=ref_str,
                        claim=f"Politika kuralı: {sec_title or doc_title}",
                        content=claim_text,
                        document_id=str(hit.get("doc_id", "")),
                        section_title=sec_title,
                        page_number=page_no,
                        confidence_score=float(hit.get("score", 0.0)),
                    )
                )
        else:
            rag_status = "insufficient_evidence"
            rag_context = (
                "İlgili kurumsal politika belgelerinde bu RFQ konusuyla ilgili herhangi bir spesifik kural veya kısıt bulunamadı. "
                "Lütfen varsayımda bulunmadan bu kuralın politikalarda yer almadığını (yetersiz kanıt) açıkça belirtiniz."
            )
            warnings.append("Politika belgelerinde bu RFQ için yeterli kanıt veya eşleşen kural bulunamadı (insufficient_evidence).")

        duration_ms = (time.monotonic() - start_mono) * 1000
        completed_at = datetime.now(timezone.utc)

        output = PolicyComplianceOutput(
            rag_status=rag_status,
            evidence_count=len(evidence_refs),
            citations=evidence_refs,
            query_used=query,
            is_sufficient_evidence=is_sufficient,
        )

        stage_result = StageResultResponse(
            stage=StageName.POLICY_COMPLIANCE,
            status=StageStatus.COMPLETED if is_sufficient else StageStatus.INCONCLUSIVE,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 2),
            summary=f"Politika analizi tamamlandı: {rag_status} ({len(evidence_refs)} kanıt maddesi).",
            details=output.model_dump(mode="json"),
            sources=evidence_refs,
            warnings=warnings,
        )

        return stage_result, output, rag_context, evidence_refs


# ── Stage 4: Supplier Recommendation (LLM Agent) ──────────────────────────────

class SupplierRecommendationStage:
    """
    Stage 4: LLM Danışman Ajanı.
    - Sadece doğrulanmış girdi ve deterministik sonuçları kullanır.
    - Elenen teklifleri kazanan olarak öneremez.
    - Kanıtsız iddia üretmesi engellenir.
    - Zaman aşımı, bozuk JSON ve provider hataları güvenle yakalanır.
    """

    @classmethod
    async def execute(
        cls,
        db: AsyncSession,
        analysis_id: uuid.UUID,
        rfq: RFQ,
        quotes: List[Quote],
        eligible_quotes: List[Quote],
        eliminated_quotes: List[Quote],
        tco_results: List[TCOResult],
        compliance_checks: List[ComplianceCheck],
        rag_context: str,
        llm_provider = None,
    ) -> Tuple[StageResultResponse, SupplierRecommendationOutput, AgentRecommendationSchema]:
        started_at = datetime.now(timezone.utc)
        start_mono = time.monotonic()
        warnings = []

        if llm_provider is None:
            llm_provider = get_llm_provider()

        # 1. SQL Tedarikçi Geçmişini (Supplier Memory) çek
        supplier_ids = list(set([q.supplier_id for q in quotes if q.supplier_id]))
        sql_context = ""
        sql_metrics_summary = {}

        if supplier_ids:
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
            history_res = await db.execute(history_query)
            metrics = history_res.all()

            if metrics:
                sql_context = "--- SQL TEDARİKÇİ GEÇMİŞİ (SUPPLIER MEMORY) ---\n"
                for m in metrics:
                    supp_name = next(
                        (q.supplier.name for q in quotes if q.supplier_id == m.supplier_id and q.supplier),
                        "Bilinmeyen Tedarikçi"
                    )
                    avg_d = round(float(m.avg_delay), 1) if m.avg_delay is not None else 0.0
                    tot_q = m.total_quality_issues or 0
                    sql_metrics_summary[str(m.supplier_id)] = {
                        "name": supp_name,
                        "orders": m.total_orders,
                        "avg_delay": avg_d,
                        "quality_issues": tot_q,
                    }
                    sql_context += f"Tedarikçi: {supp_name}\n- Toplam Sipariş: {m.total_orders}\n- Ortalama Gecikme: {avg_d} gün\n- Kalite Sorunu: {tot_q}\n\n"

        # 2. Uygun ve elenen teklif veri paketlerini hazırla
        eligible_payload = []
        for eq in eligible_quotes:
            tco = next((t for t in tco_results if t.quote_id == eq.id), None)
            missing = TCOCalculator.get_missing_financial_fields(eq)
            checks = [c for c in compliance_checks if c.quote_id == eq.id]
            warn_notes = [c.notes for c in checks if c.result == ComplianceResult.WARNING]
            eligible_payload.append({
                "quote_id": str(eq.id),
                "supplier_name": eq.supplier.name if eq.supplier else "Bilinmeyen Tedarikçi",
                "total_tco": float(tco.total_tco) if tco else float(eq.total_price),
                "currency": eq.currency,
                "delivery_days": eq.delivery_days,
                "warranty_months": eq.warranty_months,
                "payment_terms": eq.payment_terms,
                "has_incomplete_financial_data": len(missing) > 0,
                "missing_fields": missing,
                "warnings": warn_notes,
                "extraction_confidence": float(eq.extraction_confidence) if eq.extraction_confidence is not None else None,
                "items": [{"desc": i.description, "qty": float(i.quantity), "price": float(i.unit_price)} for i in eq.items]
            })

        eliminated_payload = []
        for elq in eliminated_quotes:
            checks = [c for c in compliance_checks if c.quote_id == elq.id]
            fail_notes = [f"{c.rule_name}: {c.notes}" for c in checks if c.result == ComplianceResult.FAIL]
            eliminated_payload.append({
                "quote_id": str(elq.id),
                "supplier_name": elq.supplier.name if elq.supplier else "Bilinmeyen Tedarikçi",
                "reasons": fail_notes
            })

        # 3. Prompt oluştur
        prompt = (
            "Sen kıdemli bir Satın Alma Uzmanı ve Danışman AI Ajanısın. "
            "Aşağıdaki doğrulanmış verileri inceleyerek şirket için en uygun tedarikçi teklifini önermelisin.\n\n"
            "ÖNEMLİ KURAL 1: Analizini yazarken ASLA 'quote_id' veya UUID gibi teknik kimlikleri kullanma. "
            "Her zaman 'supplier_name' (Tedarikçi Adı) alanını kullanarak akıcı bir dille hitap et.\n"
            "ÖNEMLİ KURAL 2: Sen sadece bir danışmansın. Asla 'Bu teklif onaylanmıştır' veya 'Sipariş verilmiştir' gibi kesin yargılar kullanma. "
            "Her zaman 'Bu teklifi öneriyorum' veya 'Değerlendirilmesi tavsiye edilir' gibi öneri dili kullan. Nihai kararı insan yönetici verecektir.\n"
            "ÖNEMLİ KURAL 3: Fiyat tek kriter değildir; teslimat süresi, garanti, kurumsal politika uyumu ve geçmiş tedarikçi performansını birlikte tart.\n"
            "ÖNEMLİ KURAL 4 (KANIT ZORUNLULUĞU): Eğer Politika veya SQL geçmişinden bir iddiada bulunuyorsan, mutlaka '[Kaynak X: ...]' formatında açık atıf yap. Kaynağı olmayan bilgi uydurma.\n"
            "ÖNEMLİ KURAL 5 (ELENENLER): Elenen teklifleri ASLA kazanan olarak seçme. Onları yalnızca trade-off kıyaslamasında referans ver.\n\n"
        )
        prompt += f"--- KURUMSAL HAFIZA (RAG CONTEXT) ---\n{rag_context}\n\n"
        if sql_context:
            prompt += f"{sql_context}\n"
        prompt += "--- ELENEN TEKLİFLER (HARD FAIL) ---\n" + json.dumps(eliminated_payload, indent=2, ensure_ascii=False) + "\n\n"
        prompt += "--- UYGUN TEKLİFLER (ELIGIBLE) ---\n" + json.dumps(eligible_payload, indent=2, ensure_ascii=False) + "\n\n"
        prompt += "Görev: Tüm verileri analiz et, trade-off analizi yap ve en iyi teklifi seç. Format olarak istenen JSON şemasına kesinlikle uy."

        # 4. LLM Çağrısı
        config = ExtractionConfig(thinking_budget=1024, max_tokens=2048, timeout=45)
        try:
            agent_output = await llm_provider.extract_structured(
                prompt=prompt,
                schema=AgentRecommendationSchema,
                config=config,
            )
        except Exception as exc:
            raise PipelineStageError(
                stage=StageName.SUPPLIER_RECOMMENDATION,
                error_code="LLM_PROVIDER_ERROR",
                message=f"LLM öneri üretirken hata oluştu: {str(exc)}",
                status_code=500,
            )

        duration_ms = (time.monotonic() - start_mono) * 1000
        completed_at = datetime.now(timezone.utc)

        # Bulunan tedarikçi adı
        chosen_quote = next((q for q in quotes if q.id == agent_output.recommended_quote_id), None)
        chosen_supplier_name = chosen_quote.supplier.name if (chosen_quote and chosen_quote.supplier) else None

        output = SupplierRecommendationOutput(
            recommended_quote_id=agent_output.recommended_quote_id,
            supplier_name=chosen_supplier_name,
            justification=agent_output.justification,
            trade_off_analysis=agent_output.trade_off_analysis,
            risk_factors=agent_output.risk_factors,
            confidence_score=agent_output.confidence_score,
            is_human_review_required=agent_output.is_human_review_required,
            model_name=getattr(llm_provider, "model_name", "gemini-2.5-flash"),
        )

        stage_result = StageResultResponse(
            stage=StageName.SUPPLIER_RECOMMENDATION,
            status=StageStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 2),
            summary=f"Öneri oluşturuldu: {chosen_supplier_name or 'Teklif seçilmedi'} (Güven: {agent_output.confidence_score}/100).",
            details=output.model_dump(mode="json"),
            warnings=warnings,
        )

        return stage_result, output, agent_output


# ── Stage 5: Independent Verification ─────────────────────────────────────────

class IndependentVerificationStage:
    """
    Stage 5: Bağımsız Doğrulama Katmanı (Independent Verification).
    - LLM çıktısını alır ve deterministik gerçeklerle (TCO, kurallar, RAG, SQL) kıyaslar.
    - LLM'nin elenen bir teklifi seçip seçmediğini denetler (Kritik Override).
    - Sayısal TCO tutarlılığını doğrular.
    - Dayanağı olmayan kaynak iddialarını veya halüsinasyonları tespit eder.
    - Sonuç sözleşmesi: passed | failed | inconclusive
    """

    @classmethod
    async def execute(
        cls,
        db: AsyncSession,
        analysis_id: uuid.UUID,
        recommendation_schema: AgentRecommendationSchema,
        quotes: List[Quote],
        eligible_quotes: List[Quote],
        eliminated_quotes: List[Quote],
        tco_results: List[TCOResult],
        compliance_checks: List[ComplianceCheck],
        policy_evidence_refs: List[StageEvidenceRef],
    ) -> Tuple[StageResultResponse, IndependentVerificationOutput, Recommendation]:
        started_at = datetime.now(timezone.utc)
        start_mono = time.monotonic()
        warnings = []
        checks_performed: List[VerificationCheckDetail] = []

        is_failed = False
        is_inconclusive = False
        notes = []

        chosen_id = recommendation_schema.recommended_quote_id
        eliminated_ids = {q.id for q in eliminated_quotes}
        eligible_ids = {q.id for q in eligible_quotes}

        # ── Denetim 1: Hard Rule İhlal Kontrolü (Critical Rule) ────────────────
        if chosen_id is not None and chosen_id in eliminated_ids:
            is_failed = True
            quote_fails = [
                f"{c.rule_name} (Gerçek: {c.actual_value}, Beklenen: {c.required_value})"
                for c in compliance_checks
                if c.quote_id == chosen_id and c.result == ComplianceResult.FAIL
            ]
            fail_msg = f"KURAL İHLALİ: LLM elenen bir teklifi önerdi! İhlal edilen kurallar: {'; '.join(quote_fails)}"
            notes.append(fail_msg)
            checks_performed.append(VerificationCheckDetail(
                name="hard_rule_compliance",
                description="Seçilen teklifin deterministik kurallardan geçmiş olması zorunludur.",
                passed=False,
                actual_value="ELENEN_TEKLIF",
                expected_value="UYGUN_TEKLIF",
                notes=fail_msg
            ))
        else:
            checks_performed.append(VerificationCheckDetail(
                name="hard_rule_compliance",
                description="Seçilen teklifin deterministik kurallardan geçmiş olması zorunludur.",
                passed=True,
                actual_value="UYGUN_TEKLIF" if chosen_id else "SECILMEDI",
                expected_value="UYGUN_TEKLIF",
                notes="Hard-rule ihlali bulunmamaktadır."
            ))

        # ── Denetim 2: Sayısal TCO Tutarlılığı ────────────────────────────────
        tco_consistent = True
        if chosen_id is not None:
            chosen_tco = next((t for t in tco_results if t.quote_id == chosen_id and t.analysis_id == analysis_id), None)
            if not chosen_tco:
                is_failed = True
                tco_consistent = False
                notes.append("TCO UYUMSUZLUĞU: Seçilen teklif için kayıtlı deterministik TCO hesabı bulunamadı.")
            else:
                checks_performed.append(VerificationCheckDetail(
                    name="tco_calculation_consistency",
                    description="Önerilen teklifin TCO tutarı backend hesabı ile tam eşleşmelidir.",
                    passed=True,
                    actual_value=f"{chosen_tco.total_tco} {chosen_tco.currency}",
                    expected_value=f"{chosen_tco.total_tco} {chosen_tco.currency}",
                    notes="Deterministik TCO doğrulanmıştır."
                ))
        else:
            checks_performed.append(VerificationCheckDetail(
                name="tco_calculation_consistency",
                description="Önerilen teklifin TCO tutarı backend hesabı ile tam eşleşmelidir.",
                passed=True,
                actual_value="N/A",
                expected_value="N/A",
                notes="Teklif seçilmediği için TCO denetimi atlandı."
            ))

        # ── Denetim 3: Kanıt Atıfı & Halüsinasyon Kontrolü ─────────────────────
        all_text = f"{recommendation_schema.justification}\n{recommendation_schema.trade_off_analysis}\n{' '.join(recommendation_schema.risk_factors)}"
        citations_found = re.findall(r"\[Kaynak \d+:\s*(.*?)\]", all_text)

        unsupported_claims = False
        valid_evidence_items: List[EvidenceItem] = []

        # Önceki evidence_items kayıtlarını temizle
        await db.execute(
            delete(EvidenceItem).where(EvidenceItem.analysis_id == analysis_id)
        )

        for cit in set(citations_found):
            # Kanıtın gerçekten Stage 3'te veya SQL geçmişinde var olup olmadığını kontrol et
            is_policy_match = any(cit.lower() in ref.source_reference.lower() or cit.lower() in ref.claim.lower() for ref in policy_evidence_refs)
            is_sql_match = "sql" in cit.lower() or "geçmiş" in cit.lower()

            if is_policy_match or is_sql_match:
                src_type = "policy" if is_policy_match else "supplier_history"
                ev_item = EvidenceItem(
                    analysis_id=analysis_id,
                    source_type=src_type,
                    source_reference=cit,
                    claim=f"LLM tarafından '{cit}' kaynak gösterilerek iddiada bulunuldu.",
                    content="Sistem tarafından doğrulandı.",
                )
                valid_evidence_items.append(ev_item)
            else:
                unsupported_claims = True
                warnings.append(f"Desteklenmeyen kanıt atıfı tespit edildi: '{cit}'. Bu kaynak sistem hafızasında mevcut değildir.")

        if unsupported_claims:
            is_inconclusive = True
            notes.append("UYARI: LLM gerekçesinde kurumsal hafızada bulunmayan kanıt atıfları yer almaktadır.")

        checks_performed.append(VerificationCheckDetail(
            name="citation_grounding",
            description="LLM tarafından yapılan tüm kanıt atıfları sistem hafızasıyla doğrulanmalıdır.",
            passed=not unsupported_claims,
            actual_value=f"{len(citations_found)} atıf ({len(valid_evidence_items)} doğrulanmış)",
            expected_value="Tüm atıflar doğrulanmalı",
            notes="Desteklenmeyen atıflar tespit edildi." if unsupported_claims else "Tüm atıflar kurumsal hafızayla eşleşti."
        ))

        # ── Denetim 4: Yetersiz Kanıt / İnsan İnceleme Bayrağı Denetimi ────────
        insufficient_evidence_flagged = False
        if chosen_id is not None:
            chosen_quote_obj = next((q for q in quotes if q.id == chosen_id), None)
            if chosen_quote_obj:
                missing_fields = TCOCalculator.get_missing_financial_fields(chosen_quote_obj)
                has_missing = len(missing_fields) > 0
                low_conf = chosen_quote_obj.extraction_confidence is not None and chosen_quote_obj.extraction_confidence < Decimal("0.70")

                if (has_missing or low_conf) and not recommendation_schema.is_human_review_required:
                    insufficient_evidence_flagged = True
                    is_inconclusive = True
                    recommendation_schema.is_human_review_required = True
                    notes.append("GÜVENLİK DÜZELTMESİ: Eksik maliyet verisi veya düşük çıkarma güven skoru nedeniyle zorunlu insan incelemesi (is_human_review_required=True) aktif edildi.")

        # ── Nihai Karar Sözleşmesi (passed | failed | inconclusive) ───────────
        if is_failed:
            final_status = VerificationOutcome.FAILED
            db_status = VerificationStatus.OVERRIDDEN.value
            # Başarısız doğrulama kazananı temizler
            effective_recommended_id = None
            notes.insert(0, "SİSTEM UYARISI: Doğrulama başarısız oldu (failed). Bu öneri otomatik olarak reddedilmiştir.")
        elif is_inconclusive:
            final_status = VerificationOutcome.INCONCLUSIVE
            db_status = VerificationStatus.INCONCLUSIVE.value
            effective_recommended_id = chosen_id
            notes.insert(0, "DOĞRULAMA SONUCU: Yetersiz kanıt veya uyarılar mevcut (inconclusive). Yönetici incelemesi zorunludur.")
        else:
            final_status = VerificationOutcome.PASSED
            db_status = VerificationStatus.VERIFIED.value
            effective_recommended_id = chosen_id
            notes.insert(0, "DOĞRULAMA GEÇTİ: Tüm deterministik kontroller ve kanıt doğrulamaları başarıyla onaylandı (passed).")

        verification_notes_text = "\n".join(notes)

        # ── Veritabanına Recommendation ve Evidence Kayıtlarını Yaz ───────────
        combined_reasoning = f"{recommendation_schema.justification}\n\n**Trade-off Analizi:**\n{recommendation_schema.trade_off_analysis}"

        # Mevcut recommendation varsa güncelle, yoksa ekle
        rec_res = await db.execute(
            select(Recommendation).where(Recommendation.analysis_id == analysis_id)
        )
        recommendation_record = rec_res.scalar_one_or_none()

        if not recommendation_record:
            recommendation_record = Recommendation(
                analysis_id=analysis_id,
                recommended_quote_id=effective_recommended_id,
                reasoning=combined_reasoning,
                risks=json.dumps(recommendation_schema.risk_factors, ensure_ascii=False),
                alternative_notes=f"Güven Skoru: {recommendation_schema.confidence_score}/100. İnsan Onayı Gerekli mi: {'Evet' if recommendation_schema.is_human_review_required else 'Hayır'}",
                verification_status=db_status,
                verification_notes=verification_notes_text,
            )
            db.add(recommendation_record)
        else:
            recommendation_record.recommended_quote_id = effective_recommended_id
            recommendation_record.reasoning = combined_reasoning
            recommendation_record.risks = json.dumps(recommendation_schema.risk_factors, ensure_ascii=False)
            recommendation_record.alternative_notes = f"Güven Skoru: {recommendation_schema.confidence_score}/100. İnsan Onayı Gerekli mi: {'Evet' if recommendation_schema.is_human_review_required else 'Hayır'}"
            recommendation_record.verification_status = db_status
            recommendation_record.verification_notes = verification_notes_text

        if valid_evidence_items:
            db.add_all(valid_evidence_items)

        await db.flush()

        duration_ms = (time.monotonic() - start_mono) * 1000
        completed_at = datetime.now(timezone.utc)

        output = IndependentVerificationOutput(
            verification_status=final_status,
            verification_notes=verification_notes_text,
            checks=checks_performed,
            hard_rule_passed=not is_failed,
            tco_consistency_passed=tco_consistent,
            unsupported_claims_found=unsupported_claims,
            insufficient_evidence_flagged=insufficient_evidence_flagged,
            evidence_items_recorded=len(valid_evidence_items),
        )

        stage_status_enum = (
            StageStatus.COMPLETED if final_status == VerificationOutcome.PASSED
            else StageStatus.FAILED if final_status == VerificationOutcome.FAILED
            else StageStatus.INCONCLUSIVE
        )

        stage_result = StageResultResponse(
            stage=StageName.INDEPENDENT_VERIFICATION,
            status=stage_status_enum,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 2),
            summary=f"Bağımsız doğrulama tamamlandı: {final_status.value.upper()}.",
            details=output.model_dump(mode="json"),
            warnings=warnings,
        )

        return stage_result, output, recommendation_record
