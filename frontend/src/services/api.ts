import type {
  DashboardResponse,
  RecommandationsResponse,
  ChatRequest,
  ChatResponse,
  AnalyzeRequest,
  AnalyzeResponse,
} from "../types/api";

const API_BASE = "/api";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Erreur réseau" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export const api = {
  analyze: (data: AnalyzeRequest) =>
    request<AnalyzeResponse>("/analyze", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getDashboard: (sessionId: string) =>
    request<DashboardResponse>(`/dashboard/${sessionId}`),

  getRecommendations: (sessionId: string) =>
    request<RecommandationsResponse>(`/recommendations/${sessionId}`),

  chat: (sessionId: string, data: ChatRequest) =>
    request<ChatResponse>(`/chat/${sessionId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
