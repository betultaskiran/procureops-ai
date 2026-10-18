"""
app/services/orchestration/pipeline.py

Phase 10: AI Workflow & Agent Orchestration Ana Orkestratörü (Master Pipeline).

Tüm RFQ analizi sürecini sıralı, izlenebilir ve test edilebilir 6 aşamada yürütür:
1. Extraction / Input Validation (Deterministik)
2. Deterministic TCO & Hard-Rule Evaluation (Deterministik)
3. Policy Compliance Analysis (Qdrant RAG + Hassas Filtreleme)
4. Supplier Recommendation (LLM Ajanı)
5. Independent Verification (Bağımsız Doğrulama)
6. Human Review (Onay / Sipariş Emri Kapısı)
"""

import uuid
import time
from datetime import datetime, timezone
from typing import List, Tuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func

from app.models.analysis import Analysis, AnalysisStatus
from app.models.audit import AuditEvent
from app.models.user import User
from app.services.deterministic.schemas import PolicyRules
from app.schemas.orchestration import (
    StageName,
    StageStatus,
    StageResultResponse,
)
from app.services.orchestration.stages import (
    PipelineStageError,
    ExtractionValidationStage,
    DeterministicEvaluationStage,
    PolicyComplianceStage,
    SupplierRecommendationStage,
    IndependentVerificationStage,
)


class AnalysisPipelineOrchestrator:
    """
    RFQ Analiz Boru Hattı Orkestratörü.
    Her aşamayı açık giriş/çıkış sözleşmeleriyle birbirine bağlar.
    Bir aşama başarısız olduğunda sonraki aşamaların çalıştırılmasını kesin olarak engeller.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_pipeline(
        self,
        rfq_id: uuid.UUID,
        rules: PolicyRules,
        current_user: User,
        llm_provider = None,
        rag_service = None,
    ) -> Tuple[Analysis, List[StageResultResponse]]:
        pipeline_start_mono = time.monotonic()
        stage_results: List[StageResultResponse] = []

        # 1. Analiz Kaydını Başlat
        analysis = Analysis(
            rfq_id=rfq_id,
            created_by_id=current_user.id,
            status=AnalysisStatus.RUNNING.value,
        )
        self.db.add(analysis)
        await self.db.flush()

        try:
            # ── AŞAMA 1: Extraction & Input Validation ────────────────────────
            s1_res, s1_out, quotes, rfq = await ExtractionValidationStage.execute(
                db=self.db,
                rfq_id=rfq_id,
                organization_id=current_user.organization_id,
            )
            stage_results.append(s1_res)

            # ── AŞAMA 2: Deterministic TCO & Hard-Rule Evaluation ─────────────
            s2_res, s2_out, eligible_quotes, eliminated_quotes, tco_results, compliance_checks = await DeterministicEvaluationStage.execute(
                db=self.db,
                analysis_id=analysis.id,
                quotes=quotes,
                rules=rules,
            )
            stage_results.append(s2_res)

            # ── AŞAMA 3: Policy Compliance Analysis (RAG) ─────────────────────
            s3_res, s3_out, rag_context, evidence_refs = await PolicyComplianceStage.execute(
                organization_id=str(current_user.organization_id),
                rfq=rfq,
                quotes=quotes,
                rag_service=rag_service,
            )
            stage_results.append(s3_res)

            # ── AŞAMA 4: Supplier Recommendation (LLM Agent) ──────────────────
            s4_res, s4_out, recommendation_schema = await SupplierRecommendationStage.execute(
                db=self.db,
                analysis_id=analysis.id,
                rfq=rfq,
                quotes=quotes,
                eligible_quotes=eligible_quotes,
                eliminated_quotes=eliminated_quotes,
                tco_results=tco_results,
                compliance_checks=compliance_checks,
                rag_context=rag_context,
                llm_provider=llm_provider,
                policy_output=s3_out,
            )
            stage_results.append(s4_res)

            # ── AŞAMA 5: Independent Verification ─────────────────────────────
            s5_res, s5_out, recommendation_record = await IndependentVerificationStage.execute(
                db=self.db,
                analysis_id=analysis.id,
                recommendation_schema=recommendation_schema,
                quotes=quotes,
                eligible_quotes=eligible_quotes,
                eliminated_quotes=eliminated_quotes,
                tco_results=tco_results,
                compliance_checks=compliance_checks,
                policy_evidence_refs=evidence_refs,
                policy_output=s3_out,
            )
            stage_results.append(s5_res)

            # Başarılı Boru Hattı Tamamlama
            analysis.status = AnalysisStatus.COMPLETED.value
            analysis.created_at = func.now()
            analysis.updated_at = func.now()
            rfq.status = "pending_approval"

            # Audit Trail Kaydı
            total_duration_ms = round((time.monotonic() - pipeline_start_mono) * 1000, 2)
            self.db.add(AuditEvent(
                organization_id=rfq.organization_id,
                actor_id=current_user.id,
                event_type="analysis_pipeline_completed",
                entity_type="analysis",
                entity_id=analysis.id,
                payload={
                    "rfq_id": str(rfq.id),
                    "total_duration_ms": total_duration_ms,
                    "stages_count": len(stage_results),
                    "verification_outcome": s5_out.verification_status.value,
                    "quote_count": len(quotes),
                    "eligible_count": len(eligible_quotes),
                    "eliminated_count": len(eliminated_quotes),
                    "stage_summaries": [
                        {"stage": sr.stage.value, "status": sr.status.value, "duration_ms": sr.duration_ms}
                        for sr in stage_results
                    ]
                }
            ))

            await self.db.commit()
            await self.db.refresh(analysis, ["tco_results", "compliance_checks", "evidence_items", "recommendation", "created_at", "updated_at"])
            return analysis, stage_results

        except PipelineStageError as pse:
            # Aşama hatası: sonraki aşamalar ASLA çalıştırılmaz.
            analysis.status = AnalysisStatus.FAILED.value
            analysis.error_message = pse.message

            # Başarısız olan aşamayı kaydet
            failed_stage_res = StageResultResponse(
                stage=pse.stage,
                status=StageStatus.FAILED,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                duration_ms=0.0,
                summary=f"Aşama başarısız oldu: {pse.message}",
                error_code=pse.error_code,
                error_message=pse.message,
            )
            stage_results.append(failed_stage_res)

            # Audit log
            self.db.add(AuditEvent(
                organization_id=current_user.organization_id,
                actor_id=current_user.id,
                event_type="analysis_pipeline_failed",
                entity_type="analysis",
                entity_id=analysis.id,
                payload={
                    "rfq_id": str(rfq_id),
                    "failed_stage": pse.stage.value,
                    "error_code": pse.error_code,
                    "error_message": pse.message,
                }
            ))
            await self.db.commit()
            raise pse

        except Exception as exc:
            # Beklenmeyen hata
            analysis.status = AnalysisStatus.FAILED.value
            analysis.error_message = str(exc)
            await self.db.commit()
            raise exc
