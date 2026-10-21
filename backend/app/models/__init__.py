"""
app/models/__init__.py

Tüm modelleri tek noktadan export eder.

Bu dosya iki kritik iş yapar:
1. Her yerden tek import: from app.models import User, RFQ, Quote
2. Alembic autogenerate için modellerin Base.metadata'ya kaydedilmesi

Alembic env.py'de şunu yazacağız:
    from app.models import Base
    target_metadata = Base.metadata

Bu sayede Alembic tüm tabloları bilir ve migration üretebilir.
Eğer bir model dosyasını buraya import etmezsek Alembic o tabloyu görmez!
"""

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.supplier import Supplier, SupplierHistory
from app.models.policy_document import PolicyDocument, DocumentType
from app.models.rfq import RFQ, RFQItem, QuoteDocument, RFQStatus, ParseStatus, FileType
from app.models.quote import Quote, QuoteItem
from app.models.analysis import (
    Analysis,
    TCOResult,
    ComplianceCheck,
    EvidenceItem,
    Recommendation,
    Approval,
    AnalysisStatus,
    ComplianceResult,
    EvidenceSourceType,
    VerificationStatus,
    ApprovalStatus,
)
from app.models.audit import AuditEvent
from app.models.order import (
    PurchaseOrder,
    PurchaseOrderStatus,
    POApprovalStep,
    POApprovalStepStatus,
    POQualityIssue,
    IssueType,
    IssueSeverity,
    QualityIssueStatus,
)
from app.models.email_delivery import (
    EmailDelivery,
    EmailDeliveryStatus,
    EmailMessageType,
)
from app.models.exchange_rate import ExchangeRate

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    # Organization & User
    "Organization",
    "User",
    "UserRole",
    # Supplier
    "Supplier",
    "SupplierHistory",
    # Policy
    "PolicyDocument",
    "DocumentType",
    # RFQ
    "RFQ",
    "RFQItem",
    "QuoteDocument",
    "RFQStatus",
    "ParseStatus",
    "FileType",
    # Quote
    "Quote",
    "QuoteItem",
    # Analysis
    "Analysis",
    "TCOResult",
    "ComplianceCheck",
    "EvidenceItem",
    "Recommendation",
    "Approval",
    "AnalysisStatus",
    "ComplianceResult",
    "EvidenceSourceType",
    "VerificationStatus",
    "ApprovalStatus",
    # Audit
    "AuditEvent",
    # Order
    "PurchaseOrder",
    "PurchaseOrderStatus",
    "POApprovalStep",
    "POApprovalStepStatus",
    "POQualityIssue",
    "IssueType",
    "IssueSeverity",
    "QualityIssueStatus",
    # Email Delivery (Phase 9)
    "EmailDelivery",
    "EmailDeliveryStatus",
    "EmailMessageType",
    # FX Engine (Milestone 2)
    "ExchangeRate",
]
