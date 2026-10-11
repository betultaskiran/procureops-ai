import { apiClient } from "./client";
import { RFQ, Quote, DashboardRFQResponse, AnalysisResponse, PurchaseOrderResponse, ReviewRequest, RFQCreateRequest, SupplierResponse, UploadResponse } from "./types";

export const rfqsApi = {
  // Real endpoint for Dashboard UI
  async getRecentRfqs(): Promise<DashboardRFQResponse[]> {
    return apiClient.get<DashboardRFQResponse[]>("/api/v1/dashboard/recent-rfqs");
  },

  async getRfqs(): Promise<RFQ[]> {
    return apiClient.get<RFQ[]>("/api/v1/rfqs");
  },
  
  async createRfq(req: RFQCreateRequest): Promise<RFQ> {
    return apiClient.post<RFQ>("/api/v1/rfqs", req);
  },

  async getRfq(id: string): Promise<RFQ> {
    return apiClient.get<RFQ>(`/api/v1/rfqs/${id}`);
  },

  async getRfqQuotes(id: string): Promise<Quote[]> {
    return apiClient.get<Quote[]>(`/api/v1/rfqs/${id}/quotes`);
  },
  
  async uploadQuoteDocument(rfqId: string, supplierId: string, file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append("supplier_id", supplierId);
    formData.append("file", file);
    
    // Using fetch directly since apiClient might not support FormData easily
    const res = await fetch(`http://localhost:8000/api/v1/rfqs/${rfqId}/quote-documents`, {
      method: "POST",
      body: formData,
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || "Upload failed");
    }
    
    return res.json();
  },
  
  async analyzeRfq(rfqId: string): Promise<AnalysisResponse> {
    return apiClient.post<AnalysisResponse>(`/api/v1/rfqs/${rfqId}/analyze`, {
      rules: {} // Use default rules
    });
  },

  async getAnalysis(id: string): Promise<AnalysisResponse> {
    return apiClient.get<AnalysisResponse>(`/api/v1/rfqs/${id}/analysis`);
  },
  
  async getPurchaseOrders(id: string): Promise<PurchaseOrderResponse[]> {
    return apiClient.get<PurchaseOrderResponse[]>(`/api/v1/rfqs/${id}/purchase-orders`);
  },
  
  async reviewAnalysis(analysisId: string, req: ReviewRequest): Promise<any> {
    return apiClient.post(`/api/v1/analyses/${analysisId}/review`, req);
  },
  
  async getRfqQuote(rfqId: string, quoteId: string): Promise<Quote> {
    return apiClient.get<Quote>(`/api/v1/rfqs/${rfqId}/quotes/${quoteId}`);
  },

  async getSuppliers(): Promise<SupplierResponse[]> {
    return apiClient.get<SupplierResponse[]>("/api/v1/suppliers");
  },

  async createSupplier(req: import("./types").SupplierCreateRequest): Promise<SupplierResponse> {
    return apiClient.post<SupplierResponse>("/api/v1/suppliers", req);
  }
};
