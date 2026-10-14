import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderSummary(BaseModel):
    total_orders_count: int = Field(description="Total orders across all statuses (completed + delivered + cancelled + active + draft)")
    completed_orders_count: int = Field(description="Orders fully completed/settled")
    delivered_orders_count: int = Field(description="Delivered orders pending completion/closure")
    cancelled_orders_count: int = Field(description="Cancelled or disputed orders")
    active_orders_count: int = Field(description="Active/issued orders in progress")
    draft_orders_count: int = Field(default=0, description="Draft orders (excluded from completed/active totals and performance aggregates)")


class DeliveryReliability(BaseModel):
    is_available: bool = Field(description="True if at least one eligible delivery record exists; False otherwise")
    confidence: Literal["insufficient", "low", "high"] = Field(description="Confidence rating based on eligible record count")
    eligible_orders_count: int = Field(description="Count of orders with both expected and actual delivery dates")
    on_time_orders_count: int | None = Field(default=None, description="Total orders delivered on or before promised date (delay <= 0). Includes early deliveries (early_orders_count + exact_on_time_count). Mutually exclusive from late_orders_count.")
    late_orders_count: int | None = Field(default=None, description="Orders delivered strictly after promised date (delay > 0). Mutually exclusive from on_time_orders_count.")
    early_orders_count: int | None = Field(default=None, description="Orders delivered strictly before promised date (delay < 0). Subset of on_time_orders_count.")
    on_time_percentage: float | None = Field(default=None, description="Percentage of eligible orders delivered on time: (on_time_orders_count / eligible_orders_count) * 100")
    average_delay_days: float | None = Field(default=None, description="Average delay in days across all eligible orders (negative = early, positive = late)")
    notes: str | None = Field(default=None, description="Explanatory notes regarding delivery sample or availability")


class CurrencyFinancialSummary(BaseModel):
    currency: str = Field(description="ISO 4217 Currency Code (e.g. TRY, USD, EUR)")
    total_spend: Decimal = Field(description="Total spend across evaluated non-cancelled orders")
    average_order_value: Decimal = Field(description="Average order value")
    min_order_value: Decimal = Field(description="Minimum order value")
    max_order_value: Decimal = Field(description="Maximum order value")
    orders_count: int = Field(description="Number of orders in this currency")
    final_amount_orders_count: int = Field(description="Number of orders using verified final PO amounts")
    quoted_amount_orders_count: int = Field(description="Number of orders using quoted amounts")
    historical_amount_orders_count: int = Field(default=0, description="Number of orders using legacy historical amounts")


class QualityMetrics(BaseModel):
    is_tracked: bool = Field(description="True if quality tracking exists for at least one order; False if not tracked")
    tracked_orders_count: int = Field(description="Number of orders with quality tracking data")
    total_quality_issues: int | None = Field(default=None, description="Total recorded quality issues (None if untracked)")
    total_rejections: int | None = Field(default=None, description="Total rejected items/orders (None if untracked)")
    notes: str | None = Field(default=None, description="Notes on quality data coverage")


class SupplierPerformanceResponse(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str
    organization_id: uuid.UUID
    order_summary: OrderSummary
    delivery_reliability: DeliveryReliability
    financial_summary: dict[str, CurrencyFinancialSummary] = Field(
        description="Financial metrics grouped strictly by currency code. Currencies are never mixed."
    )
    quality_metrics: QualityMetrics
    evaluated_orders_count: int = Field(description="Total non-draft transactions evaluated")
    confidence_level: Literal["insufficient", "low", "high"] = Field(
        description="Overall statistical confidence based on evaluated sample size"
    )
    has_conflicts: bool = Field(default=False, description="True if reference collisions between PO and external history were found")
    conflict_notes: str | None = Field(default=None, description="Details of any reference collisions detected")

    model_config = ConfigDict(from_attributes=True)


class SupplierHistoryItemResponse(BaseModel):
    id: uuid.UUID
    source_type: Literal["purchase_order", "external_history"] = Field(description="Source of the historical record")
    source_record_id: uuid.UUID = Field(description="ID of the underlying PurchaseOrder or SupplierHistory record")
    order_reference: str = Field(description="PO number or external order reference")
    order_date: date = Field(description="Date the order was placed")
    expected_delivery_date: date | None = Field(default=None, description="Promised/expected delivery date")
    actual_delivery_date: date | None = Field(default=None, description="Actual delivery date")
    delay_days: int | None = Field(default=None, description="Days delayed (negative = early, 0 = on-time, positive = late)")
    status: str = Field(description="Order status: completed, delivered, cancelled, issued, draft, etc.")
    amount: Decimal = Field(description="Monetary amount of the transaction")
    currency: str = Field(description="ISO 4217 Currency Code")
    amount_type: Literal["final_po_amount", "quoted_amount", "historical_amount"] = Field(
        description="Provenance of the monetary amount"
    )
    quality_issues: int | None = Field(default=None, description="Quality defects recorded (None if untracked)")
    rejection_count: int | None = Field(default=None, description="Rejected items recorded (None if untracked)")
    has_collision: bool = Field(default=False, description="True if an unlinked external record shares a reference with a platform PO")
    collision_note: str | None = Field(default=None, description="Notes describing the collision if present")
    notes: str | None = Field(default=None, description="Delivery or operational notes")
    created_at: datetime = Field(description="Record creation timestamp")

    model_config = ConfigDict(from_attributes=True)


class PaginatedSupplierHistoryResponse(BaseModel):
    items: list[SupplierHistoryItemResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)
