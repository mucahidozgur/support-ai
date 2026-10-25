// Backend ile iletişim: ince fetch wrapper + tipler.

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";
const TOKEN_KEY = "support_token";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
    throw new ApiError("Oturum süresi doldu, tekrar giriş yapın", 401);
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // Yanıt JSON değilse detay alınamaz; genel hata mesajı yeterli.
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

// Token helpers
export function getToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(TOKEN_KEY);
}

// Types
export interface Document {
  id: string;
  title: string;
  content: string;
  owner_id: string;
  source: string;
  created_at: string;
  updated_at: string | null;
}

export interface DocumentListItem {
  id: string;
  title: string;
  source: string;
  created_at: string;
  content_preview: string;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserInfo {
  id: string;
  username: string;
}

export interface ChatSource {
  document_id: string;
  document_title: string;
  chunk_id: string;
  chunk_index: number;
  similarity: number;
}

export interface AnalyticsStats {
  total_queries: number;
  avg_faithfulness: number;
  insufficient_context_rate: number;
  avg_latency_ms: number;
  feedback_positive: number;
  feedback_negative: number;
}

export interface RecentQueryItem {
  id: string;
  query: string;
  faithfulness: number | null;
  feedback: number | null;
  had_context: boolean;
  latency_ms: number | null;
  created_at: string;
}

export interface TopQueryItem {
  query: string;
  count: number;
}

// API methods
export const api = {
  async login(username: string, password: string): Promise<LoginResponse> {
    const res = await apiFetch<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(res.access_token);
    return res;
  },

  me(): Promise<UserInfo> {
    return apiFetch<UserInfo>("/api/auth/me");
  },

  logout(): void {
    clearToken();
  },

  listDocuments(limit = 20, offset = 0): Promise<DocumentListResponse> {
    return apiFetch<DocumentListResponse>(`/api/documents?limit=${limit}&offset=${offset}`);
  },

  getDocument(id: string): Promise<Document> {
    return apiFetch<Document>(`/api/documents/${id}`);
  },

  createDocument(data: { title: string; content: string }): Promise<Document> {
    return apiFetch<Document>("/api/documents", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  updateDocument(
    id: string,
    data: { title?: string; content?: string }
  ): Promise<Document> {
    return apiFetch<Document>(`/api/documents/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  deleteDocument(id: string): Promise<void> {
    return apiFetch<void>(`/api/documents/${id}`, { method: "DELETE" });
  },

  indexDocument(id: string): Promise<{ chunks_created: number; chunks_deleted: number }> {
    return apiFetch<{ chunks_created: number; chunks_deleted: number }>(
      `/api/documents/${id}/index`,
      { method: "POST" }
    );
  },

  getAnalyticsStats(): Promise<AnalyticsStats> {
    return apiFetch<AnalyticsStats>("/api/analytics/stats");
  },

  getRecentQueries(limit = 20): Promise<RecentQueryItem[]> {
    return apiFetch<RecentQueryItem[]>(`/api/analytics/recent-queries?limit=${limit}`);
  },

  getTopQueries(): Promise<TopQueryItem[]> {
    return apiFetch<TopQueryItem[]>("/api/analytics/top-queries");
  },
};
