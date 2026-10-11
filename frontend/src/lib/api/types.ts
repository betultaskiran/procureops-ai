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
  // We may join these from the backend eventually
  quotes_count?: number; 
  total_value?: number;
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
  vat_rate: number;
  vat_amount: number;
  shipping_cost: number;
  discount_amount: number;
  other_costs: number;
  total_price: number;
  delivery_days: number | null;
  payment_terms: string | null;
  warranty_months: number | null;
  extraction_confidence: number | null;
  is_compliant: boolean | null;
  items: QuoteItem[];
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
  calculation_notes: string;
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

export interface AnalysisResponse {
  id: string;
  rfq_id: string;
  status: string;
  tco_results: TCOResultResponse[];
  compliance_checks: ComplianceCheckResponse[];
  recommendation: RecommendationResponse | null;
  evidence_items: EvidenceItemResponse[];
}


export interface PurchaseOrderResponse {
  id: string;
  po_number: string;
  quote_id: string;
  approval_id: string;
  status: string;
  email_sent: boolean;
  created_at: string;
}

export interface ReviewRequest {
  status: string;
  comment?: string;
  selected_quote_id?: string;
  acknowledged_policy_violation?: boolean;
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

