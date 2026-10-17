export function getBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    // If browser is accessing via 127.0.0.1 and env is localhost (or vice versa), align hostnames
    // to preserve same-origin / same-site cookie and CORS credentials behavior.
    if (window.location.hostname === "127.0.0.1" && envUrl?.includes("localhost")) {
      return envUrl.replace("localhost", "127.0.0.1");
    }
    if (window.location.hostname === "localhost" && envUrl?.includes("127.0.0.1")) {
      return envUrl.replace("127.0.0.1", "localhost");
    }
    if (envUrl) {
      return envUrl;
    }
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return envUrl || "http://localhost:8000";
}

const BASE_URL = getBaseUrl();

export class ApiError extends Error {
  public status: number;
  public data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = "ApiError";
  }
}

export function getAuthToken(): string | null {
  if (typeof window !== "undefined") {
    // 1. Check primary and fallback localStorage keys
    const local =
      localStorage.getItem("access_token") ||
      localStorage.getItem("token") ||
      localStorage.getItem("auth_token") ||
      localStorage.getItem("jwt");
    if (local) return local;

    // 2. Check sessionStorage
    const session =
      sessionStorage.getItem("access_token") ||
      sessionStorage.getItem("token") ||
      sessionStorage.getItem("auth_token");
    if (session) return session;

    // 3. Check JSON auth objects in localStorage
    for (const key of ["auth", "user", "session", "procureops_auth"]) {
      const val = localStorage.getItem(key);
      if (val && (val.startsWith("{") || val.startsWith("["))) {
        try {
          const parsed = JSON.parse(val);
          const t = parsed.access_token || parsed.token || parsed.user?.token;
          if (t && typeof t === "string") return t;
        } catch {}
      }
    }

    // 4. Check document.cookie for dual-transport non-HttpOnly client cookie
    if (typeof document !== "undefined" && document.cookie) {
      const match = document.cookie.match(/(?:^|;\s*)(?:access_token|token|jwt|auth_token)=([^;]+)/);
      if (match && match[1]) {
        return decodeURIComponent(match[1]);
      }
    }
  }
  return null;
}

export function setAuthToken(token: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("access_token", token);
    localStorage.setItem("token", token);
    sessionStorage.setItem("access_token", token);
    // Also set a client-accessible cookie for dual-transport fallback
    if (typeof document !== "undefined") {
      document.cookie = `access_token=${encodeURIComponent(token)}; path=/; max-age=86400; SameSite=Lax`;
    }
    // Dispatch event so active listeners can immediately sync
    window.dispatchEvent(new Event("auth:login"));
  }
}

export function removeAuthToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    localStorage.removeItem("token");
    localStorage.removeItem("auth_token");
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("token");
    if (typeof document !== "undefined") {
      document.cookie = "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    }
    // Dispatch event so active listeners can immediately sync
    window.dispatchEvent(new Event("auth:logout"));
  }
}

export function getAuthHeaders(): Record<string, string> {
  const token = getAuthToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

async function handleResponse<T>(response: Response, path?: string): Promise<T> {
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await response.json() : null;

  if (!response.ok) {
    // If a protected route fails with 401 Unauthorized (and not a login attempt),
    // clear the invalid/expired token and inform auth subscribers
    if (response.status === 401 && path !== "/api/v1/auth/login") {
      removeAuthToken();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("auth:unauthorized", { detail: { path } }));
      }
    }

    throw new ApiError(
      response.status,
      data?.detail || response.statusText || "An API error occurred",
      data
    );
  }

  return data as T;
}

export const apiClient = {
  async get<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${getBaseUrl()}${path}`, {
      credentials: "include",
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...options?.headers,
      },
    });
    return handleResponse<T>(res, path);
  },

  async post<T>(path: string, body: any, options?: RequestInit): Promise<T> {
    const res = await fetch(`${getBaseUrl()}${path}`, {
      credentials: "include",
      ...options,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...options?.headers,
      },
      body: JSON.stringify(body),
    });
    return handleResponse<T>(res, path);
  },

  async patch<T>(path: string, body: any, options?: RequestInit): Promise<T> {
    const res = await fetch(`${getBaseUrl()}${path}`, {
      credentials: "include",
      ...options,
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...options?.headers,
      },
      body: JSON.stringify(body),
    });
    return handleResponse<T>(res, path);
  },

  // Added for file uploads (FormData)
  async postForm<T>(path: string, body: FormData, options?: RequestInit): Promise<T> {
    const res = await fetch(`${getBaseUrl()}${path}`, {
      credentials: "include",
      ...options,
      method: "POST",
      // Do NOT set Content-Type header manually when using FormData, 
      // the browser sets it automatically with the correct boundary
      headers: {
        ...getAuthHeaders(),
        ...options?.headers,
      },
      body,
    });
    return handleResponse<T>(res, path);
  },

  async delete<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${getBaseUrl()}${path}`, {
      credentials: "include",
      ...options,
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...options?.headers,
      },
    });
    return handleResponse<T>(res, path);
  }
};
