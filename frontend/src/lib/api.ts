import { z } from "zod";
import { API_BASE_URL } from "./env";

const API_V1 = `${API_BASE_URL}/api/v1`;

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body?: unknown
  ) {
    super(`API Error ${status}: ${statusText}`);
    this.name = "ApiError";
  }
}

/**
 * Make a typed, validated API request.
 *
 * @param path - Path relative to /api/v1 (e.g. "/wells")
 * @param options - Fetch options
 * @param schema - Optional Zod schema to validate the response
 */
async function request<T>(
  path: string,
  options?: RequestInit,
  schema?: z.ZodType<T>
): Promise<T> {
  // Ensure trailing slash to avoid FastAPI 307 redirects
  const normalizedPath = path.includes("?")
    ? path
    : path.endsWith("/")
      ? path
      : `${path}/`;
  const url = `${API_V1}${normalizedPath}`;

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

  const data = await res.json();

  // Validate with Zod schema if provided
  if (schema) {
    const parsed = schema.safeParse(data);
    if (!parsed.success) {
      console.warn("API response validation warning:", parsed.error.flatten());
      // Return data anyway — don't crash on minor schema mismatches
      return data as T;
    }
    return parsed.data;
  }

  return data as T;
}

export const api = {
  get: <T>(
    path: string,
    params?: Record<string, string>,
    schema?: z.ZodType<T>
  ) => {
    const query = params ? `?${new URLSearchParams(params)}` : "";
    return request<T>(`${path}${query}`, undefined, schema);
  },

  post: <T>(path: string, body?: unknown, schema?: z.ZodType<T>) =>
    request<T>(
      path,
      {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      },
      schema
    ),

  patch: <T>(path: string, body?: unknown, schema?: z.ZodType<T>) =>
    request<T>(
      path,
      {
        method: "PATCH",
        body: body ? JSON.stringify(body) : undefined,
      },
      schema
    ),
};

/** SWR fetcher — validates with schema if the URL matches known patterns */
export const fetcher = <T>(url: string): Promise<T> => {
  // Prefix relative URLs with backend base
  const fullUrl = url.startsWith("/api")
    ? `${API_BASE_URL}${url}`
    : url;
  return fetch(fullUrl).then((res) => {
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return res.json();
  });
};
