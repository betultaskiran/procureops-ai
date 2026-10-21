import { apiClient, getBaseUrl } from "./client";

export interface PolicyDocument {
  id: string;
  organization_id: string;
  title: string;
  file_name: string;
  file_path: string;
  document_type: string;
  is_active: boolean;
  is_chunked: boolean;
  chunk_count: number | null;
  qdrant_collection: string | null;
  processing_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PolicySearchHit {
  source: string;
  doc_id: string;
  chunk_index: number;
  text: string;
  title?: string;
  document_type?: string;
  section_title?: string;
  page_number?: number;
  file_name?: string;
  file_url?: string;
  score?: number;
  is_header?: boolean;
}

export interface PolicySearchResponse {
  query: string;
  context: string;
  hits: PolicySearchHit[];
}

export const policiesApi = {
  async listPolicies(organizationId?: string): Promise<PolicyDocument[]> {
    const url = organizationId 
      ? `/api/v1/policies?organization_id=${organizationId}`
      : `/api/v1/policies`;
    return apiClient.get<PolicyDocument[]>(url);
  },

  async uploadPolicy(formData: FormData): Promise<PolicyDocument> {
    return apiClient.postForm<PolicyDocument>("/api/v1/policies/upload", formData);
  },

  async deletePolicy(policyId: string): Promise<{ message: string; id: string }> {
    return apiClient.delete<{ message: string; id: string }>(`/api/v1/policies/${policyId}`);
  },

  async testSearch(query: string, topK: number = 3): Promise<PolicySearchResponse> {
    return apiClient.post<PolicySearchResponse>("/api/v1/policies/search", {
      query,
      top_k: topK
    });
  },

  getFileUrl(docId: string, pageNumber?: number): string {
    const base = getBaseUrl();
    const pageHash = pageNumber ? `#page=${pageNumber}` : "";
    return `${base}/api/v1/policies/${docId}/file${pageHash}`;
  }
};
