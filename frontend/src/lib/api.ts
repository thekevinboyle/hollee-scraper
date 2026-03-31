const API_BASE =
  typeof window !== "undefined"
    ? "http://localhost:8000/api/v1"
    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body?: unknown
  ) {
    super(`API Error ${status}: ${statusText}`);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // Ensure trailing slash to avoid FastAPI 307 redirects
  const normalizedPath = path.includes("?") ? path : (path.endsWith("/") ? path : `${path}/`);
  const url = `${API_BASE}${normalizedPath}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, res.statusText, body);
  }

  return res.json();
}

export const api = {
  get: <T>(path: string, params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params)}` : "";
    return request<T>(`${path}${query}`);
  },

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    }),
};

export const fetcher = <T>(url: string): Promise<T> => {
  // If url starts with /api, prefix with backend base
  const fullUrl = url.startsWith("/api") ? `http://localhost:8000${url}` : url;
  return fetch(fullUrl).then((res) => {
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return res.json();
  });
};
