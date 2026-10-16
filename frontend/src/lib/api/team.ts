import { apiClient } from "./client";
import { 
  TeamMember, 
  CreateTeamMemberInput, 
  UpdateMemberRoleInput, 
  AuthMeResponse 
} from "./types";

export const teamApi = {
  /**
   * List all team members in the authenticated user's organization.
   */
  async getMembers(): Promise<TeamMember[]> {
    return apiClient.get<TeamMember[]>("/api/v1/team/members");
  },

  /**
   * Add / invite a new member to the organization (Admin only).
   */
  async createMember(input: CreateTeamMemberInput): Promise<TeamMember> {
    return apiClient.post<TeamMember>("/api/v1/team/members", input);
  },

  /**
   * Update a team member's role (Admin only).
   */
  async updateRole(userId: string, input: UpdateMemberRoleInput): Promise<TeamMember> {
    return apiClient.patch<TeamMember>(`/api/v1/team/members/${userId}/role`, input);
  },

  /**
   * Deactivate a team member (Admin only).
   */
  async deactivateMember(userId: string): Promise<TeamMember> {
    return apiClient.post<TeamMember>(`/api/v1/team/members/${userId}/deactivate`, {});
  },

  /**
   * Reactivate a deactivated team member (Admin only).
   */
  async reactivateMember(userId: string): Promise<TeamMember> {
    return apiClient.post<TeamMember>(`/api/v1/team/members/${userId}/reactivate`, {});
  },

  /**
   * Get details of the currently authenticated user.
   */
  async getCurrentUser(): Promise<AuthMeResponse> {
    return apiClient.get<AuthMeResponse>("/api/v1/auth/me");
  },
};
