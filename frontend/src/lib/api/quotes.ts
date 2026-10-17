import { apiClient } from "./client";
import { UploadResponse, Quote } from "./types";

/**
 * quotesApi
 * Dedicated API service for RFQ Supplier Quote management and document upload.
 * Guarantees dual-transport authentication (HttpOnly cookie + Authorization: Bearer token).
 */
export const quotesApi = {
  /**
   * Upload a supplier quote document (PDF, Excel .xlsx, PNG, JPG).
   * Sends multipart/form-data via apiClient.postForm with credentials: 'include' and Authorization header.
   */
  async uploadQuoteDocument(rfqId: string, supplierId: string, file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append("supplier_id", supplierId);
    formData.append("file", file);

    return apiClient.postForm<UploadResponse>(`/api/v1/rfqs/${rfqId}/quote-documents`, formData);
  },

  /**
   * Alias: uploadQuote
   */
  async uploadQuote(rfqId: string, supplierId: string, file: File): Promise<UploadResponse> {
    return this.uploadQuoteDocument(rfqId, supplierId, file);
  },

  /**
   * Alias: upload
   */
  async upload(rfqId: string, supplierId: string, file: File): Promise<UploadResponse> {
    return this.uploadQuoteDocument(rfqId, supplierId, file);
  },

  /**
   * Reprocess an existing uploaded quote document through the extraction pipeline
   */
  async reprocessQuoteDocument(rfqId: string, documentId: string): Promise<UploadResponse> {
    return apiClient.post<UploadResponse>(`/api/v1/rfqs/${rfqId}/quote-documents/${documentId}/reprocess`, {});
  },

  /**
   * Get all quotes submitted for an RFQ
   */
  async getRfqQuotes(rfqId: string): Promise<Quote[]> {
    return apiClient.get<Quote[]>(`/api/v1/rfqs/${rfqId}/quotes`);
  },

  /**
   * Alias: getQuotes
   */
  async getQuotes(rfqId: string): Promise<Quote[]> {
    return this.getRfqQuotes(rfqId);
  },

  /**
   * Get a specific quote by RFQ ID and Quote ID
   */
  async getRfqQuote(rfqId: string, quoteId: string): Promise<Quote> {
    return apiClient.get<Quote>(`/api/v1/rfqs/${rfqId}/quotes/${quoteId}`);
  },

  /**
   * Alias: getQuote
   */
  async getQuote(rfqId: string, quoteId: string): Promise<Quote> {
    return this.getRfqQuote(rfqId, quoteId);
  },

  /**
   * Delete a quote
   */
  async deleteQuote(
    quoteId: string, 
    rfqId?: string, 
    organizationId?: string
  ): Promise<{ status: string; message: string; id: string; rfq_id: string }> {
    const basePath = rfqId ? `/api/v1/rfqs/${rfqId}/quotes/${quoteId}` : `/api/v1/quotes/${quoteId}`;
    const query = organizationId ? `?organization_id=${organizationId}` : "";
    return apiClient.delete<{ status: string; message: string; id: string; rfq_id: string }>(`${basePath}${query}`);
  }
};
