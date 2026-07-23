export interface AleaScore {
  code: string;
  label: string;
  score: number;
  niveau: "faible" | "modéré" | "élevé" | "critique";
  projection_2050?: number;
}

export interface AnalyseRisque {
  scores_par_alea: AleaScore[];
  risques_dominants: string[];
  synthese: string;
}

export interface Recommandation {
  priorite: number;
  titre: string;
  description: string;
  cout_estime_bas: number;
  cout_estime_haut: number;
  gain_resilience_pct: number;
  aleas_adresses: string[];
}

export interface RapportAnalyse {
  session_id: string;
  score_global: number;
  niveau_risque: string;
  adresse: string;
  coordonnees: { lat: number; lng: number };
  analyse_risque: AnalyseRisque;
  recommandations: Recommandation[];
  projections_2050: Record<string, number>;
  cout_total_bas: number;
  cout_total_haut: number;
  gain_moyen: number;
  synthese: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export interface DashboardData {
  session_id: string;
  score_global: number;
  niveau_risque: string;
  adresse: string;
  coordonnees: { lat: number; lng: number };
  scores_par_alea: Record<string, { score: number; niveau: string; label: string }>;
  risques_dominants: string[];
  projections_2050: Record<string, number>;
  recommandations: Recommandation[];
  synthese: string;
}
