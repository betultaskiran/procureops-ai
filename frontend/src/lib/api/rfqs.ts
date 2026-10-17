import { apiClient } from "./client";
import { 
  RFQ, 
  Quote, 
  DashboardRFQResponse, 
  AnalysisResponse, 
  PurchaseOrderResponse, 
  ReviewRequest, 
  RFQCreateRequest, 
  SupplierResponse, 
  UploadResponse,
  PaginatedRFQResponse
} from "./types";

export interface GetRfqsOptions {
  page?: number;
  pageSize?: number;
  limit?: number;
  status?: string;
  search?: string;
  isArchived?: boolean;
  includeArchived?: boolean;
  archivedOnly?: boolean;
  organizationId?: string;
}

export const rfqsApi = {
  // Real endpoint for Dashboard UI
  async getRecentRfqs(): Promise<DashboardRFQResponse[]> {
    return apiClient.get<DashboardRFQResponse[]>("/api/v1/dashboard/recent-rfqs");
  },

  async getRfqs(options?: GetRfqsOptions): Promise<PaginatedRFQResponse> {
    const params = new URLSearchParams();
    if (options?.page) params.append("page", options.page.toString());
    if (options?.pageSize) params.append("page_size", options.pageSize.toString());
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.status && options.status !== "all") {
      params.append("status", options.status);
    }
    if (options?.search && options.search.trim()) {
      params.append("search", options.search.trim());
    }
    if (options?.isArchived !== undefined) {
      params.append("is_archived", options.isArchived.toString());
    } else if (options?.archivedOnly) {
      params.append("archived_only", "true");
    } else if (options?.includeArchived) {
      params.append("include_archived", "true");
    }
    if (options?.organizationId) params.append("organization_id", options.organizationId);

    const queryString = params.toString() ? `?${params.toString()}` : "";
    return apiClient.get<PaginatedRFQResponse>(`/api/v1/rfqs${queryString}`);
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
    
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const token = typeof window !== "undefined" ? (localStorage.getItem("access_token") || localStorage.getItem("token")) : null;
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${baseUrl}/api/v1/rfqs/${rfqId}/quote-documents`, {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
    });
    
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(error.detail || "Upload failed");
    }
    
    return res.json();
  },

  async reprocessQuoteDocument(rfqId: string, documentId: string): Promise<UploadResponse> {
    return apiClient.post<UploadResponse>(`/api/v1/rfqs/${rfqId}/quote-documents/${documentId}/reprocess`, {});
  },
  
  async analyzeRfq(rfqId: string, organizationId?: string): Promise<AnalysisResponse> {
    return apiClient.post<AnalysisResponse>(`/api/v1/rfqs/${rfqId}/analyze`, {
      rules: {}, // Use default rules
      organization_id: organizationId
    });
  },

  async getAnalysis(id: string): Promise<AnalysisResponse> {
    return apiClient.get<AnalysisResponse>(`/api/v1/rfqs/${id}/analysis`);
  },
  
  async getPurchaseOrders(id: string): Promise<PurchaseOrderResponse[]> {
    return apiClient.get<PurchaseOrderResponse[]>(`/api/v1/rfqs/${id}/purchase-orders`);
  },
  
  async reviewAnalysis(analysisId: string, req: ReviewRequest): Promise<import("./types").ReviewResponse> {
    return apiClient.post<import("./types").ReviewResponse>(`/api/v1/analyses/${analysisId}/review`, req);
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
