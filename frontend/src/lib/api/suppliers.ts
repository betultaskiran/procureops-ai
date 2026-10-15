import { apiClient } from "./client";
import { 
  SupplierPerformanceResponse, 
  PaginatedSupplierHistoryResponse,
  SupplierResponse,
  SupplierCreateRequest
} from "./types";

export const suppliersApi = {
  async getPerformance(supplierId: string, signal?: AbortSignal): Promise<SupplierPerformanceResponse> {
    return apiClient.get<SupplierPerformanceResponse>(`/api/v1/suppliers/${supplierId}/performance`, { signal });
  },

  async getHistory(
    supplierId: string,
    page: number = 1,
    pageSize: number = 20,
    signal?: AbortSignal
  ): Promise<PaginatedSupplierHistoryResponse> {
    return apiClient.get<PaginatedSupplierHistoryResponse>(
      `/api/v1/suppliers/${supplierId}/history?page=${page}&page_size=${pageSize}`,
      { signal }
    );
  },

  async getSuppliers(): Promise<SupplierResponse[]> {
    return apiClient.get<SupplierResponse[]>("/api/v1/suppliers");
  },

  async createSupplier(req: SupplierCreateRequest): Promise<SupplierResponse> {
    return apiClient.post<SupplierResponse>("/api/v1/suppliers", req);
  },
};
