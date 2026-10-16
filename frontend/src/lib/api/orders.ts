import { apiClient } from "./client";
import {
  PurchaseOrderDetailResponse,
  DeliverPORequest,
  CompletePORequest,
  POQualityIssueResponse,
  POQualityIssueCreate,
  POQualityIssueUpdate,
} from "./types";

export const ordersApi = {
  async getOrder(poId: string): Promise<PurchaseOrderDetailResponse> {
    return apiClient.get<PurchaseOrderDetailResponse>(`/api/v1/orders/${poId}`);
  },

  async deliverOrder(poId: string, req: DeliverPORequest = {}): Promise<PurchaseOrderDetailResponse> {
    return apiClient.post<PurchaseOrderDetailResponse>(`/api/v1/orders/${poId}/deliver`, req);
  },

  async completeOrder(poId: string, req: CompletePORequest = {}): Promise<PurchaseOrderDetailResponse> {
    return apiClient.post<PurchaseOrderDetailResponse>(`/api/v1/orders/${poId}/complete`, req);
  },

  async cancelOrder(poId: string, reason: string): Promise<PurchaseOrderDetailResponse> {
    return apiClient.post<PurchaseOrderDetailResponse>(`/api/v1/orders/${poId}/cancel`, { reason });
  },

  async addQualityIssue(poId: string, req: POQualityIssueCreate): Promise<POQualityIssueResponse> {
    return apiClient.post<POQualityIssueResponse>(`/api/v1/orders/${poId}/quality-issues`, req);
  },

  async updateQualityIssue(
    poId: string,
    issueId: string,
    req: POQualityIssueUpdate
  ): Promise<POQualityIssueResponse> {
    return apiClient.patch<POQualityIssueResponse>(`/api/v1/orders/${poId}/quality-issues/${issueId}`, req);
  },

  async getQualityIssues(poId: string): Promise<POQualityIssueResponse[]> {
    return apiClient.get<POQualityIssueResponse[]>(`/api/v1/orders/${poId}/quality-issues`);
  },
};
