// Types matching the FastAPI backend schemas

export type RFQStatus = "draft" | "collecting_quotes" | "analyzing" | "pending_approval" | "approved" | "rejected" | "cancelled";

export interface RFQItem {
  id: string;
  line_number: number;
  description: string;
  quantity: number;
  unit: string | null;
}

export interface RFQ {
  id: string;
  title: string;
  description: string | null;
  status: RFQStatus;
  created_at: string;
  required_quantity: number | null;
  required_date: string | null;
  budget: number | null;
  max_delivery_days: number | null;
  min_warranty_months: number | null;
  payment_terms: string | null;
  items: RFQItem[];
  quotes_count?: number; 
  total_value?: number;
  can_delete?: boolean;
  delete_block_reason?: string | null;
  has_po?: boolean;
  is_archived?: boolean;
  created_by_name?: string | null;
  organization_id?: string | null;
}

export interface PaginatedRFQResponse {
  items: RFQ[];
  total_count: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface QuoteItem {
  id: string;
  line_number: number;
  description: string;
  quantity: number;
  unit: string | null;
  unit_price: number;
  total_price: number;
}

export interface Quote {
  id: string;
  rfq_id: string;
  supplier_id: string;
  supplier_name?: string; // Hydrated from backend if joined
  extracted_supplier_name?: string | null;
  quote_document_id?: string | null;
  currency: string;
  subtotal: number;
  vat_rate: number | null;
  vat_amount: number | null;
  shipping_cost: number | null;
  discount_amount: number | null;
  other_costs: number | null;
  total_price: number;
  delivery_days: number | null;
  payment_terms: string | null;
  warranty_months: number | null;
  extraction_confidence: number | null;
  is_compliant: boolean | null;
  items: QuoteItem[];
  can_delete?: boolean;
  delete_block_reason?: string | null;
}


export interface DashboardRFQResponse {
  id: string;
  title: string;
  status: string;
  created_at: string;
  recommended_supplier_name: string | null;
  recommended_tco: number | null;
  recommendation_status: string | null;
}


export interface TCOResultResponse {
  quote_id: string;
  total_tco: number;
  currency: string;
  calculation_notes: string | null;
}

export interface ComplianceCheckResponse {
  quote_id: string;
  rule_name: string;
  rule_description: string;
  result: string;
  actual_value: string;
  required_value: string;
  notes: string;
}

export interface RecommendationResponse {
  recommended_quote_id: string | null;
  reasoning: string;
  risks: string | null;
  alternative_notes: string | null;
  verification_status: string;
  verification_notes: string | null;
}

export interface EvidenceItemResponse {
  source_type: string;
  source_reference: string;
  claim: string;
}

export interface StageEvidenceRef {
  source_type: "quote" | "policy" | "supplier_history" | "calculation";
  source_reference: string;
  claim: string;
  content?: string;
  document_id?: string | null;
  section_title?: string | null;
  page_number?: number | null;
  confidence_score?: number | null;
}

export interface StageResultResponse {
  stage: "extraction_validation" | "deterministic_evaluation" | "policy_compliance" | "supplier_recommendation" | "independent_verification" | "human_review";
  status: "pending" | "running" | "completed" | "failed" | "inconclusive" | "skipped";
  started_at: string;
  completed_at: string;
  duration_ms: number;
  summary: string;
  details?: Record<string, any>;
  sources?: StageEvidenceRef[];
  warnings?: string[];
  error_code?: string | null;
  error_message?: string | null;
}

export interface AnalysisResponse {
  id: string;
  rfq_id: string;
  status: string;
  tco_results: TCOResultResponse[];
  compliance_checks: ComplianceCheckResponse[];
  recommendation: RecommendationResponse | null;
  evidence_items: EvidenceItemResponse[];
  stage_results?: StageResultResponse[];
  is_stale?: boolean;
}


export interface PurchaseOrderResponse {
  id: string;
  po_number: string;
  quote_id: string;
  approval_id: string;
  status: string;
  email_sent: boolean;
  email_sent_at?: string | null;
  cancellation_reason?: string | null;
  cancelled_at?: string | null;
  expected_delivery_date?: string | null;
  actual_delivery_date?: string | null;
  delivered_at?: string | null;
  final_amount?: number | null;
  delivery_notes?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface POQualityIssueResponse {
  id: string;
  organization_id: string;
  purchase_order_id: string;
  supplier_id: string;
  reported_by_id?: string | null;
  reported_by_name?: string | null;
  issue_type: string;
  severity: string;
  description: string;
  rejection_count: number;
  status: "open" | "resolved" | "dismissed";
  resolution_notes?: string | null;
  resolved_at?: string | null;
  created_at: string;
}

export interface POQualityIssueCreate {
  issue_type: string;
  severity?: string;
  description: string;
  rejection_count?: number;
}

export interface POQualityIssueUpdate {
  status: "open" | "resolved" | "dismissed";
  resolution_notes?: string;
}

export interface DeliverPORequest {
  actual_delivery_date?: string | null;
  delivery_notes?: string | null;
}

export interface CompletePORequest {
  final_amount?: number | null;
  completion_notes?: string | null;
}

export interface PurchaseOrderDetailResponse extends PurchaseOrderResponse {
  rfq_id: string;
  rfq_title: string;
  supplier_id: string;
  supplier_name: string;
  currency: string;
  quoted_amount: number;
  quality_issues: POQualityIssueResponse[];
  allowed_actions: string[];
}

export interface ReviewRequest {
  status: string;
  comment?: string;
  reviewer_id?: string;
  selected_quote_id?: string;
  acknowledged_policy_violation?: boolean;
  organization_id?: string;
}

export interface ReviewResponse {
  id: string;
  analysis_id: string;
  status: string;
  comment: string | null;
  selected_quote_id: string | null;
  acknowledged_policy_violation: boolean;
}

export interface RFQItemCreate {
  description: string;
  quantity: number;
  unit?: string | null;
}

export interface RFQCreateRequest {
  title: string;
  description?: string;
  required_quantity?: number;
  required_date?: string | null;
  budget?: number | null;
  max_delivery_days?: number | null;
  min_warranty_months?: number | null;
  payment_terms?: string | null;
  items?: RFQItemCreate[];
}

export interface SupplierResponse {
  id: string;
  organization_id?: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  city?: string | null;
  country?: string | null;
  notes?: string | null;
  is_active?: boolean;
}

export interface SupplierCreateRequest {
  name: string;
  email?: string;
  phone?: string;
  city?: string;
  country?: string;
  notes?: string;
}

export interface UploadResponse {
  quote_document_id: string;
  parse_status: string;
  parse_error: string | null;
  quote: Quote | null;
  extracted_supplier_name?: string | null;
  supplier_mismatch?: boolean;
  warning?: string | null;
  message: string;
}

// ── Phase 4: Supplier Performance & History Types ───────────────────

export interface OrderSummary {
  total_orders_count: number;
  completed_orders_count: number;
  delivered_orders_count: number;
  cancelled_orders_count: number;
  active_orders_count: number;
  draft_orders_count: number;
}

export interface DeliveryReliability {
  is_available: boolean;
  confidence: "insufficient" | "low" | "high";
  eligible_orders_count: number;
  on_time_orders_count: number | null;
  late_orders_count: number | null;
  early_orders_count: number | null;
  on_time_percentage: number | null;
  average_delay_days: number | null;
  notes: string | null;
}

export interface CurrencyFinancialSummary {
  currency: string;
  total_spend: number;
  average_order_value: number;
  min_order_value: number;
  max_order_value: number;
  orders_count: number;
  final_amount_orders_count: number;
  quoted_amount_orders_count: number;
  historical_amount_orders_count: number;
}

export interface QualityMetrics {
  is_tracked: boolean;
  tracked_orders_count: number;
  total_quality_issues: number | null;
  total_rejections: number | null;
  notes: string | null;
}

export interface SupplierPerformanceResponse {
  supplier_id: string;
  supplier_name: string;
  organization_id: string;
  order_summary: OrderSummary;
  delivery_reliability: DeliveryReliability;
  financial_summary: Record<string, CurrencyFinancialSummary>;
  quality_metrics: QualityMetrics;
  evaluated_orders_count: number;
  confidence_level: "insufficient" | "low" | "high";
  has_conflicts: boolean;
  conflict_notes: string | null;
}

export interface SupplierHistoryItemResponse {
  id: string;
  source_type: "purchase_order" | "external_history";
  source_record_id: string;
  order_reference: string;
  order_date: string;
  expected_delivery_date: string | null;
  actual_delivery_date: string | null;
  delay_days: number | null;
  status: string;
  amount: number;
  currency: string;
  amount_type: "final_po_amount" | "quoted_amount" | "historical_amount";
  quality_issues: number | null;
  rejection_count: number | null;
  has_collision: boolean;
  collision_note: string | null;
  notes: string | null;
  created_at: string;
}

export interface PaginatedSupplierHistoryResponse {
  items: SupplierHistoryItemResponse[];
  total_count: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── Team Management & Auth Types ─────────────────────────────────────────────

export type UserRole = "admin" | "manager" | "employee" | "viewer";

export interface OrganizationResponse {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface UserResponse {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
  organization?: OrganizationResponse | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserResponse;
}

export interface RegisterRequest {
  company_name: string;
  full_name: string;
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export type AuthMeResponse = UserResponse;

export interface TeamMember {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface CreateTeamMemberInput {
  full_name: string;
  email: string;
  role: UserRole;
  password: string;
}

export interface UpdateMemberRoleInput {
  role: UserRole;
}

// ── Phase 9: Email & Outbox Delivery Types ─────────────────────────────────────
export interface EmailDeliveryResponse {
  id: string;
  organization_id: string;
  rfq_id: string | null;
  supplier_id: string | null;
  purchase_order_id?: string | null;
  recipient_email: string;
  recipient_name: string | null;
  subject: string;
  message_type: string;
  idempotency_key: string;
  status: "queued" | "sending" | "sent" | "delivered" | "failed";
  attempt_count: number;
  max_attempts: number;
  last_error: string | null;
  next_retry_at: string | null;
  provider_message_id: string | null;
  queued_at: string;
  sent_at: string | null;
  delivered_at: string | null;
  is_revoked?: boolean;
  submitted_at?: string | null;
  submitted_quote_id?: string | null;
  portal_url?: string | null;
}

export interface SendRFQInvitationRequest {
  recipient_email: string;
  supplier_id?: string | null;
  recipient_name?: string | null;
  custom_message?: string | null;
  idempotency_key?: string | null;
}

// ── Phase 13: Supplier Portal Types ───────────────────────────────────────────
export interface PortalRFQItem {
  line_number: number;
  description: string;
  quantity: number;
  unit?: string | null;
}

export interface PortalExistingQuoteItem {
  line_number: number;
  description: string;
  quantity: number;
  unit?: string | null;
  unit_price: number;
  total_price: number;
}

export interface PortalExistingQuote {
  id: string;
  currency: string;
  subtotal: number;
  vat_rate?: number | null;
  vat_amount?: number | null;
  shipping_cost?: number | null;
  discount_amount?: number | null;
  other_costs?: number | null;
  total_price: number;
  delivery_days?: number | null;
  payment_terms?: string | null;
  warranty_months?: number | null;
  valid_until?: string | null;
  notes?: string | null;
  items: PortalExistingQuoteItem[];
  created_at: string;
  updated_at?: string | null;
}

export interface PortalRFQResponse {
  invitation_id: string;
  organization_name: string;
  supplier_name: string;
  supplier_email: string;
  rfq_id: string;
  rfq_title: string;
  rfq_description?: string | null;
  required_quantity?: number | null;
  required_date?: string | null;
  max_delivery_days?: number | null;
  min_warranty_months?: number | null;
  payment_terms?: string | null;
  items: PortalRFQItem[];
  can_submit: boolean;
  deadline_passed: boolean;
  expires_at: string;
  is_revoked: boolean;
  existing_quote?: PortalExistingQuote | null;
}

export interface PortalQuoteItemSubmit {
  line_number: number;
  description: string;
  quantity: number;
  unit?: string;
  unit_price: number;
  total_price: number;
}

export interface PortalQuoteSubmitRequest {
  currency: string;
  subtotal: number;
  vat_rate?: number;
  vat_amount?: number;
  shipping_cost?: number;
  discount_amount?: number;
  other_costs?: number;
  delivery_days: number;
  warranty_months: number;
  payment_terms?: string;
  valid_until?: string;
  notes?: string;
  items?: PortalQuoteItemSubmit[];
}

export interface PortalQuoteSubmitResponse {
  success: boolean;
  message: string;
  quote_id: string;
  total_price: number;
  currency: string;
  submitted_at: string;
}



