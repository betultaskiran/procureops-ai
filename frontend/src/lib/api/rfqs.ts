import { apiClient } from "./client";
import { RFQ, Quote, DashboardRFQResponse, AnalysisResponse, PurchaseOrderResponse, ReviewRequest, RFQCreateRequest, SupplierResponse, UploadResponse } from "./types";

export const rfqsApi = {
  // Real endpoint for Dashboard UI
  async getRecentRfqs(): Promise<DashboardRFQResponse[]> {
    return apiClient.get<DashboardRFQResponse[]>("/api/v1/dashboard/recent-rfqs");
  },

  async getRfqs(options?: { includeArchived?: boolean; archivedOnly?: boolean; organizationId?: string }): Promise<RFQ[]> {
    const params = new URLSearchParams();
    if (options?.includeArchived) params.append("include_archived", "true");
    if (options?.archivedOnly) params.append("archived_only", "true");
    if (options?.organizationId) params.append("organization_id", options.organizationId);
    const queryString = params.toString() ? `?${params.toString()}` : "";
    return apiClient.get<RFQ[]>(`/api/v1/rfqs${queryString}`);
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
  },

  async deleteRfq(id: string, organizationId?: string): Promise<{ status: string; message: string; id: string }> {
    const query = organizationId ? `?organization_id=${organizationId}` : "";
    return apiClient.delete<{ status: string; message: string; id: string }>(`/api/v1/rfqs/${id}${query}`);
  },

  async deleteQuote(quoteId: string, rfqId?: string, organizationId?: string): Promise<{ status: string; message: string; id: string; rfq_id: string }> {
    const basePath = rfqId ? `/api/v1/rfqs/${rfqId}/quotes/${quoteId}` : `/api/v1/quotes/${quoteId}`;
    const query = organizationId ? `?organization_id=${organizationId}` : "";
    return apiClient.delete<{ status: string; message: string; id: string; rfq_id: string }>(`${basePath}${query}`);
  },

  async cancelRfq(rfqId: string, reason: string, cancelPos: boolean = true, organizationId?: string): Promise<RFQ> {
    return apiClient.post<RFQ>(`/api/v1/rfqs/${rfqId}/cancel`, {
      reason,
      cancel_pos: cancelPos,
      organization_id: organizationId
    });
  },

  async archiveRfq(rfqId: string, reason?: string, organizationId?: string): Promise<RFQ> {
    return apiClient.post<RFQ>(`/api/v1/rfqs/${rfqId}/archive`, {
      reason,
      organization_id: organizationId
    });
  },

  async unarchiveRfq(rfqId: string, organizationId?: string): Promise<RFQ> {
    return apiClient.post<RFQ>(`/api/v1/rfqs/${rfqId}/unarchive`, {
      organization_id: organizationId
    });
  },

  async cancelPurchaseOrder(rfqId: string, poId: string, reason: string, organizationId?: string): Promise<PurchaseOrderResponse> {
    return apiClient.post<PurchaseOrderResponse>(`/api/v1/rfqs/${rfqId}/purchase-orders/${poId}/cancel`, {
      reason,
      organization_id: organizationId
    });
  }
};
