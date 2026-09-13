import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "@/lib/tokens";

/**
 * Central API client for the Django REST Framework backend.
 */
export const API_BASE_URL = (
  (typeof import.meta !== "undefined" && import.meta.env?.["VITE_API_BASE_URL"]) ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

export const MOCK_LATENCY_MS = 400;

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status = 500, data: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

/**
 * Extracts a human-readable error message from Django REST Framework error responses.
 */
export function parseErrorMessage(errorData: unknown, fallbackMessage = "An unexpected error occurred."): string {
  if (!errorData) return fallbackMessage;
  if (typeof errorData === "string") return errorData;
  if (typeof errorData === "object") {
    const data = errorData as Record<string, unknown>;
    const detail = data["detail"];
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) return String(detail[0]);

    const nonFieldErrors = data["non_field_errors"];
    if (Array.isArray(nonFieldErrors) && nonFieldErrors.length > 0) {
      return String(nonFieldErrors[0]);
    }

    const fieldMessages: string[] = [];
    for (const [field, val] of Object.entries(data)) {
      if (Array.isArray(val) && val.length > 0) {
        fieldMessages.push(`${field}: ${val[0]}`);
      } else if (typeof val === "string") {
        fieldMessages.push(`${field}: ${val}`);
      }
    }
    if (fieldMessages.length > 0) return fieldMessages.join(" ");
  }
  return fallbackMessage;
}

// Track ongoing refresh promise to prevent duplicate refresh calls
let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

async function doRefreshToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) {
    clearTokens();
    return null;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });

    if (!res.ok) {
      clearTokens();
      return null;
    }

    const text = await res.text();
    const data = JSON.parse(text) as { access: string; refresh?: string };
    setTokens(data.access, data.refresh || refresh);
    return data.access;
  } catch {
    clearTokens();
    return null;
  }
}

/**
 * Executes a network request against the Django REST API with automatic JWT token management.
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE_URL}${path.startsWith("/") ? "" : "/"}${path}`;

  const headers = new Headers(init?.headers || {});

  // Automatically attach JSON content-type if not already specified and not FormData
  if (!headers.has("Content-Type") && !(init?.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  // Attach JWT Bearer access token
  const token = getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers });
  } catch (err) {
    throw new ApiError(
      "Unable to connect to the backend server. Please ensure the Django server is running.",
      0,
      err,
    );
  }

  // Handle 401 Unauthorized token refresh (except for login or token refresh endpoints)
  if (response.status === 401 && !path.includes("/api/auth/login/") && !path.includes("/api/auth/token/refresh/")) {
    if (!isRefreshing) {
      isRefreshing = true;
      refreshPromise = doRefreshToken().finally(() => {
        isRefreshing = false;
        refreshPromise = null;
      });
    }

    const newAccessToken = await refreshPromise;
    if (newAccessToken) {
      // Retry original request with fresh access token
      const retryHeaders = new Headers(init?.headers || {});
      if (!retryHeaders.has("Content-Type") && !(init?.body instanceof FormData)) {
        retryHeaders.set("Content-Type", "application/json");
      }
      retryHeaders.set("Authorization", `Bearer ${newAccessToken}`);

      try {
        response = await fetch(url, { ...init, headers: retryHeaders });
      } catch (err) {
        throw new ApiError("Network error during retried request.", 0, err);
      }
    } else {
      throw new ApiError("Your session has expired. Please sign in again.", 401);
    }
  }

  // Handle successful response (safely read body stream exactly once)
  if (response.ok) {
    if (response.status === 204) {
      return {} as T;
    }
    const rawText = await response.text().catch(() => "");
    if (!rawText) {
      return {} as T;
    }
    try {
      return JSON.parse(rawText) as T;
    } catch {
      return rawText as unknown as T;
    }
  }

  // Handle error response (safely read body stream exactly once)
  let errorData: unknown = null;
  try {
    const rawText = await response.text();
    if (rawText) {
      try {
        errorData = JSON.parse(rawText);
      } catch {
        errorData = rawText;
      }
    }
  } catch {
    errorData = null;
  }

  const errorMessage = parseErrorMessage(
    errorData,
    response.status === 403
      ? "You do not have permission to perform this action."
      : response.status === 404
        ? "Requested resource not found."
        : `Request failed with status ${response.status}`,
  );

  throw new ApiError(errorMessage, response.status, errorData);
}

/**
 * Simulates a network round-trip for unintegrated business mock services.
 */
export function mockRequest<T>(data: T, latency = MOCK_LATENCY_MS): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(structuredClone(data)), latency);
  });
}