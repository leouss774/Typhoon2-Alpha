import type {
  DashboardResponse,
  RecommandationsResponse,
  ChatRequest,
  ChatResponse,
  AnalyzeRequest,
  AnalyzeResponse,
  DiagnosticResponse,
} from "../types/api";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
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
  // Nouveau diagnostic (format Typhoon2-Alpha)
  diagnostic: (adresse: string, formulaire?: Record<string, unknown>) =>
    request<DiagnosticResponse>("/diagnostic", {
      method: "POST",
      body: JSON.stringify({ adresse, formulaire, bank_mode: false }),
    }),

  // Nouveau diagnostic bancaire (format Typhoon2-Alpha)
  diagnosticBank: (adresse: string, formulaire?: Record<string, unknown>) =>
    request<DiagnosticResponse>("/diagnostic", {
      method: "POST",
      body: JSON.stringify({ adresse, formulaire, bank_mode: true }),
    }),

  // Legacy : analyse complète (compatibilité)
  analyze: (data: AnalyzeRequest) =>
    request<AnalyzeResponse>("/api/analyze", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Legacy : analyse bancaire async
  bankAnalyze: (data: AnalyzeRequest) =>
    request<{ status: string; session_id: string; status_analysis: string }>("/api/bank/analyze", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Legacy : polling analyse
  getAnalysis: (sessionId: string) =>
    request<Record<string, unknown>>(`/api/analysis/${sessionId}`),

  // Legacy : dashboard
  getDashboard: (sessionId: string) =>
    request<DashboardResponse>(`/api/dashboard/${sessionId}`),

  // Legacy : recommandations
  getRecommendations: (sessionId: string) =>
    request<RecommandationsResponse>(`/api/recommendations/${sessionId}`),

  // Legacy : chat
  chat: (sessionId: string, data: ChatRequest) =>
    request<ChatResponse>(`/api/chat/${sessionId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Legacy : test vulnérabilité
  vulnerabilityTest: (zoneName: string, zoneData: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/jumeau/vulnerability-test", {
      method: "POST",
      body: JSON.stringify({ zone_name: zoneName, zone_data: zoneData }),
    }),
};
