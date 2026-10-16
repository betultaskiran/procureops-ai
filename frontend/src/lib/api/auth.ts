import { apiClient, setAuthToken, removeAuthToken, getAuthToken } from "./client";
import { 
  LoginRequest, 
  RegisterRequest, 
  TokenResponse, 
  UserResponse 
} from "./types";

export const authApi = {
  /**
   * Authenticate user with email and password.
   * On success, stores token in localStorage and returns token & user profile.
   */
  async login(payload: LoginRequest): Promise<TokenResponse> {
    const res = await apiClient.post<TokenResponse>("/api/v1/auth/login", payload);
    if (res?.access_token) {
      setAuthToken(res.access_token);
    }
    return res;
  },

  /**
   * Register a new organization and initial admin user.
   * On success, stores token in localStorage and returns token & user profile.
   */
  async register(payload: RegisterRequest): Promise<TokenResponse> {
    const res = await apiClient.post<TokenResponse>("/api/v1/auth/register", payload);
    if (res?.access_token) {
      setAuthToken(res.access_token);
    }
    return res;
  },

  /**
   * Retrieve the authenticated user's profile and active organization.
   */
  async getMe(): Promise<UserResponse> {
    return apiClient.get<UserResponse>("/api/v1/auth/me");
  },

  /**
   * Terminate user session and clear stored tokens and cookies.
   */
  logout(): void {
    apiClient.post("/api/v1/auth/logout", {}).catch(() => {});
    removeAuthToken();
  },

  /**
   * Check whether a token currently exists in storage.
   */
  hasToken(): boolean {
    return Boolean(getAuthToken());
  },
};
