// =============================================================================
//   TYPHOON — /usine : types partagés du pipeline d'analyse de plan d'usine
//   Contrat aligné sur le backend (app/scoring/plan_usine.py +
//   app/api/routes/usine.py).
// =============================================================================

export interface ZonePlan {
  id: string;
  nom: string;
  type: string;
  surface_m2?: number | null;
  confiance?: number;
  /* enrichi par le risk engine (compute_usine_risk) */
  vulnerabilite?: number;
  risque?: number;
  niveau?: string;
  description?: string;
  justification?: string;
  equipements?: string[];
  sources?: string[];
}

export interface Equipement {
  id: string;
  nom: string;
  type: string;
  zone?: string;
  zone_id?: string | null;
  valeur_remplacement_eur?: number | null;
  matieres_dangereuses?: boolean;
  critique_production?: boolean;
  confiance?: number;
  /* enrichi par le risk engine */
  sensibilite?: number;
  risque?: number;
  niveau?: string;
}

export interface PlanUsine {
  nom_usine: string;
  zones: ZonePlan[];
  equipements: Equipement[];
  confiance_globale?: number;
}

export interface AleasSite {
  score: number;
  libelle: string | null;
}

export interface AnalyseUsine {
  nom_usine: string;
  nb_zones: number;
  nb_equipements: number;
  score_global: number;
  aleas_site: AleasSite | null;
  zones: ZonePlan[];
  equipements: Equipement[];
  confiance: { score: number; niveau: string; message?: string };
}

/* ─────────────────────────── Vocabulaire métier ─────────────────────────── */

export const TYPE_ZONE_LABELS: Record<string, string> = {
  production: 'Production',
  stockage: 'Stockage',
  bureaux: 'Bureaux',
  cuves: 'Cuves / réservoirs',
  expedition: 'Expédition',
  laboratoire: 'Laboratoire',
  maintenance: 'Maintenance',
};

export const TYPE_EQUIP_LABELS: Record<string, string> = {
  machine_outil: 'Machine outil',
  ligne_production: 'Ligne de production',
  four: 'Four',
  compresseur: 'Compresseur',
  groupe_froid: 'Groupe froid',
  pompe: 'Pompe',
  chaudiere: 'Chaudière',
  reservoir: 'Réservoir',
  cuve: 'Cuve',
  silo: 'Silo',
  pont_roulant: 'Pont roulant',
  robot: 'Robot',
  automate: 'Automate',
  serveur: 'Serveur',
  laboratoire: 'Laboratoire',
  autre: 'Autre',
};

export const ZONE_TYPES = Object.keys(TYPE_ZONE_LABELS);
export const EQUIP_TYPES = Object.keys(TYPE_EQUIP_LABELS);

/* ─────────────────────────── Bandes de risque D03 ─────────────────────────── */

export interface RiskBand {
  key: string;
  label: string;
  color: string;
  soft: string;
  max: number;
}

export const RISK_BANDS: RiskBand[] = [
  { key: 'tres_faible', label: 'Très faible', color: '#3a7a6c', soft: 'rgba(58,122,108,0.16)', max: 20 },
  { key: 'faible', label: 'Faible', color: '#6e9e52', soft: 'rgba(110,158,82,0.16)', max: 40 },
  { key: 'modere', label: 'Modéré', color: '#d4ac3e', soft: 'rgba(212,172,62,0.16)', max: 60 },
  { key: 'eleve', label: 'Élevé', color: '#d07030', soft: 'rgba(208,112,48,0.18)', max: 80 },
  { key: 'critique', label: 'Critique', color: '#b03020', soft: 'rgba(176,48,32,0.20)', max: Infinity },
];

export function bandForScore(score?: number | null): RiskBand {
  if (score == null || Number.isNaN(score)) return RISK_BANDS[1];
  return RISK_BANDS.find((b) => (score as number) < b.max) || RISK_BANDS[RISK_BANDS.length - 1];
}

export function bandForKey(key?: string | null): RiskBand {
  return RISK_BANDS.find((b) => b.key === key) || RISK_BANDS[1];
}

/* Les niveaux renvoyés par le backend (risk_model._niveau) : "tres faible",
   "faible", "modere", "eleve", "tres eleve" → clés frontend. */
export function normalizeNiveau(niveau?: string | null): string {
  if (!niveau) return 'faible';
  const map: Record<string, string> = {
    'tres faible': 'tres_faible',
    'tres eleve': 'critique',
    tres_faible: 'tres_faible',
    critique: 'critique',
    eleve: 'eleve',
    modere: 'modere',
    faible: 'faible',
  };
  return map[niveau] || 'faible';
}
