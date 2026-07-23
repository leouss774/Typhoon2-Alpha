import type { DashboardData, Recommandation, ChatMessage } from "./models";

export interface ApiError {
  detail: string;
}

export interface AnalyzeRequest {
  session_id: string;
  client_form: Record<string, unknown>;
  raw_data?: Record<string, unknown>;
}

export interface AnalyzeResponse {
  session_id: string;
  status: "completed" | "validation_failed" | "error";
  score_global: number | null;
  rapport: Record<string, unknown> | null;
}

export interface ChatRequest {
  question: string;
  historique?: { role: string; content: string; timestamp?: number }[];
}

export interface ChatResponse {
  reponse: string;
  session_id: string;
}

export type DashboardResponse = DashboardData;
export type RecommandationsResponse = Recommandation[];
