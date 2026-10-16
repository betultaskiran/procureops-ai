const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    return localStorage.getItem("access_token") || localStorage.getItem("token") || null;
  }
  return null;
}

export function setAuthToken(token: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("access_token", token);
    // Dispatch event so active listeners can immediately sync
    window.dispatchEvent(new Event("auth:login"));
  }
}

export function removeAuthToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    localStorage.removeItem("token");
    // Dispatch event so active listeners can immediately sync
    window.dispatchEvent(new Event("auth:logout"));
  }
}

function getAuthHeaders(): Record<string, string> {
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
    const res = await fetch(`${BASE_URL}${path}`, {
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
    const res = await fetch(`${BASE_URL}${path}`, {
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
    const res = await fetch(`${BASE_URL}${path}`, {
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
    const res = await fetch(`${BASE_URL}${path}`, {
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
    const res = await fetch(`${BASE_URL}${path}`, {
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
