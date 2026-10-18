import { apiClient } from "./client";
import {
  PortalRFQResponse,
  PortalQuoteSubmitRequest,
  PortalQuoteSubmitResponse,
} from "./types";

export interface PortalUploadResponse {
  quote_document_id: string;
  file_name: string;
  file_size_bytes: number;
  parse_status: string;
  message: string;
}

export interface PortalPOViewResponse {
  po_number: string;
  status: string;
  organization_name: string;
  supplier_name: string;
  total_amount: number;
  currency: string;
  created_at: string;
  expected_delivery_date?: string | null;
}

export const portalApi = {
  /**
   * Fetches the RFQ details and specification requirements for the invited supplier.
   */
  async getRfq(token: string): Promise<PortalRFQResponse> {
    return apiClient.get<PortalRFQResponse>(`/api/v1/portal/rfq?token=${encodeURIComponent(token)}`);
  },

  /**
   * Submits a structured quote from the invited supplier.
   */
  async submitQuote(token: string, req: PortalQuoteSubmitRequest): Promise<PortalQuoteSubmitResponse> {
    return apiClient.post<PortalQuoteSubmitResponse>(
      `/api/v1/portal/rfq/quote?token=${encodeURIComponent(token)}`,
      req
    );
  },

  /**
   * Uploads an official quotation document (PDF/Excel) directly through the portal.
   */
  async uploadQuoteDocument(token: string, file: File): Promise<PortalUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient.postForm<PortalUploadResponse>(
      `/api/v1/portal/rfq/upload?token=${encodeURIComponent(token)}`,
      formData
    );
  },

  /**
   * Views awarded purchase order details for the supplier.
   */
  async getPurchaseOrder(poId: string, token?: string): Promise<PortalPOViewResponse> {
    const query = token ? `?token=${encodeURIComponent(token)}` : "";
    return apiClient.get<PortalPOViewResponse>(`/api/v1/portal/orders/${poId}${query}`);
  },
};
