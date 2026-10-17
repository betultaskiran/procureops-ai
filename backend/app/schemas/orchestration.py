"""
app/schemas/orchestration.py

Phase 10: AI Workflow & Agent Orchestration aşama sözleşmeleri (Stage Contracts).

RFQ Analizi 6 açık aşamadan oluşur:
1. Extraction / Input Validation
2. Deterministic TCO & Hard-Rule Evaluation
3. Policy Compliance Analysis
4. Supplier Recommendation
5. Independent Verification
6. Human Review
"""

import enum
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class StageName(str, enum.Enum):
    EXTRACTION_VALIDATION = "extraction_validation"
    DETERMINISTIC_EVALUATION = "deterministic_evaluation"
    POLICY_COMPLIANCE = "policy_compliance"
    SUPPLIER_RECOMMENDATION = "supplier_recommendation"
    INDEPENDENT_VERIFICATION = "independent_verification"
    HUMAN_REVIEW = "human_review"


class StageStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"


class VerificationOutcome(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class CitationSourceType(str, enum.Enum):
    QUOTE = "quote"
    POLICY = "policy"
    SUPPLIER_HISTORY = "supplier_history"
    CALCULATION = "calculation"


class StageEvidenceRef(BaseModel):
    """
    Her aşamada kullanılan veya üretilen doğrulanabilir kanıt referansı.
    """
    source_type: CitationSourceType
    source_reference: str
    claim: str
    content: str = ""
    document_id: Optional[str] = None
    section_title: Optional[str] = None
    page_number: Optional[int] = None
    confidence_score: Optional[float] = None

    model_config = {"from_attributes": True}


class StageResultResponse(BaseModel):
    """
    Aşama yürütme çıktısı ve izlenebilirlik sözleşmesi.
    """
    stage: StageName
    status: StageStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)
    sources: List[StageEvidenceRef] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


# ── Stage-Specific Schema Outputs ─────────────────────────────────────────────

class ExtractionValidationOutput(BaseModel):
    quote_count: int
    currency: str
    quote_ids: List[uuid.UUID]
    valid_documents_count: int
    validation_passed: bool
    missing_fields: List[str] = Field(default_factory=list)


class DeterministicEvaluationOutput(BaseModel):
    tco_results_count: int
    compliance_checks_count: int
    eligible_quote_ids: List[uuid.UUID]
    eliminated_quote_ids: List[uuid.UUID]
    eliminated_reasons: Dict[str, List[str]] = Field(default_factory=dict)
    currency: str


class PolicyComplianceOutput(BaseModel):
    rag_status: str  # "compliant" | "non_compliant" | "insufficient_evidence"
    evidence_count: int
    citations: List[StageEvidenceRef] = Field(default_factory=list)
    query_used: str
    is_sufficient_evidence: bool


class SupplierRecommendationOutput(BaseModel):
    recommended_quote_id: Optional[uuid.UUID] = None
    supplier_name: Optional[str] = None
    justification: str
    trade_off_analysis: str
    risk_factors: List[str] = Field(default_factory=list)
    confidence_score: int
    is_human_review_required: bool
    model_name: Optional[str] = None


class VerificationCheckDetail(BaseModel):
    name: str
    description: str
    passed: bool
    actual_value: Optional[str] = None
    expected_value: Optional[str] = None
    notes: Optional[str] = None


class IndependentVerificationOutput(BaseModel):
    verification_status: VerificationOutcome
    verification_notes: str
    checks: List[VerificationCheckDetail] = Field(default_factory=list)
    hard_rule_passed: bool
    tco_consistency_passed: bool
    unsupported_claims_found: bool
    insufficient_evidence_flagged: bool
    evidence_items_recorded: int
