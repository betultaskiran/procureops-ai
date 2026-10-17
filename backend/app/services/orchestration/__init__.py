"""
app/services/orchestration

AI Workflow & Agent Orchestration module for ProcureOps AI.
Decomposes analysis into 6 explicit stages with observable contracts,
strict deterministic calculation boundaries, RAG evidence grounding,
and independent verification gates.
"""

from app.schemas.orchestration import (
    StageName,
    StageStatus,
    VerificationOutcome,
    StageEvidenceRef,
    StageResultResponse,
)

__all__ = [
    "StageName",
    "StageStatus",
    "VerificationOutcome",
    "StageEvidenceRef",
    "StageResultResponse",
]
