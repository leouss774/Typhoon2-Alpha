// =============================================================================
//   TYPHOON — /usine : appels API du pipeline d'analyse de plan d'usine
//   Endpoints backend : POST /diagnostic/usine/analyze (VLM + JSON/GeoJSON)
//   et POST /diagnostic/usine (risk engine par zone/équipement).
// =============================================================================

import { API } from '../zone/config';
import type { AnalyseUsine, PlanUsine } from './types';

function detailMessage(detail: unknown): string {
  if (!detail) return 'Erreur inconnue';
  if (typeof detail === 'string') return detail;
  const d = detail as Record<string, unknown>;
  if (d.detail) return String(d.detail);
  if (d.error) return String(d.error);
  return JSON.stringify(detail);
}

/** Analyse un fichier de plan (image via Mistral Vision, JSON/GeoJSON parsé). */
export async function analyzePlanFile(file: File): Promise<PlanUsine> {
  const formData = new FormData();
  formData.append('file', file);

  const resp = await fetch(`${API}/diagnostic/usine/analyze`, {
    method: 'POST',
    body: formData,
  });

  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(detailMessage(data.detail));
  }

  const data = await resp.json();

  const zones = (data.zones || []).map((z: any, i: number) => ({
    id: z.id || `z_${i}`,
    nom: z.nom || `Zone ${i + 1}`,
    type: z.type || 'production',
    surface_m2: z.surface_m2,
    confiance: z.confiance,
  }));

  const equipements = (data.equipements || []).map((e: any, i: number) => ({
    id: e.id || `e_${i}`,
    nom: e.nom || `Équipement ${i + 1}`,
    type: e.type || 'autre',
    zone: e.zone || zones[0]?.nom || '',
    valeur_remplacement_eur: e.valeur_remplacement_eur,
    matieres_dangereuses: !!e.matieres_dangereuses,
    critique_production: !!e.critique_production,
    confiance: e.confiance,
  }));

  return {
    nom_usine: data.nom_usine || 'Mon usine',
    zones,
    equipements,
    confiance_globale: data.confiance_globale,
  };
}

/** Calcule le risque de l'usine (risk engine) par zone et équipement. */
export async function computeUsineRisk(plan: PlanUsine, adresse?: string): Promise<AnalyseUsine> {
  const resp = await fetch(`${API}/diagnostic/usine`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ adresse: adresse || null, plan }),
  });

  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(detailMessage(data.detail));
  }

  return (await resp.json()) as AnalyseUsine;
}

/** Fichier de démonstration : usine fictive pour découvrir le pipeline sans backend. */
export function demoPlan(): PlanUsine {
  return {
    nom_usine: 'Usine de démonstration',
    confiance_globale: 0.8,
    zones: [
      { id: 'z1', nom: 'Hall de production A', type: 'production', surface_m2: 3200, confiance: 0.95 },
      { id: 'z2', nom: 'Stockage matières', type: 'stockage', surface_m2: 1400, confiance: 0.92 },
      { id: 'z3', nom: 'Parc cuves', type: 'cuves', surface_m2: 900, confiance: 0.9 },
      { id: 'z4', nom: 'Bureaux & laboratoire', type: 'bureaux', surface_m2: 500, confiance: 0.94 },
      { id: 'z5', nom: 'Zone d\'expédition', type: 'expedition', surface_m2: 1100, confiance: 0.88 },
    ],
    equipements: [
      { id: 'e1', nom: 'Ligne d\'assemblage 1', type: 'ligne_production', zone: 'Hall de production A', valeur_remplacement_eur: 900000, critique_production: true, confiance: 0.95 },
      { id: 'e2', nom: 'Machine CNC 3 axes', type: 'machine_outil', zone: 'Hall de production A', valeur_remplacement_eur: 420000, critique_production: true, confiance: 0.9 },
      { id: 'e3', nom: 'Four industriel', type: 'four', zone: 'Hall de production A', valeur_remplacement_eur: 280000, matieres_dangereuses: true, confiance: 0.85 },
      { id: 'e4', nom: 'Cuve solvant 50 m³', type: 'cuve', zone: 'Parc cuves', valeur_remplacement_eur: 180000, matieres_dangereuses: true, confiance: 0.9 },
      { id: 'e5', nom: 'Réservoir hydraulique', type: 'reservoir', zone: 'Parc cuves', valeur_remplacement_eur: 95000, confiance: 0.8 },
      { id: 'e6', nom: 'Compresseur air', type: 'compresseur', zone: 'Hall de production A', valeur_remplacement_eur: 65000, critique_production: true, confiance: 0.82 },
      { id: 'e7', nom: 'Serveurs labo', type: 'serveur', zone: 'Bureaux & laboratoire', valeur_remplacement_eur: 120000, confiance: 0.88 },
      { id: 'e8', nom: 'Pont roulant 10 t', type: 'pont_roulant', zone: 'Zone d\'expédition', valeur_remplacement_eur: 210000, critique_production: true, confiance: 0.86 },
      { id: 'e9', nom: 'Silo granulés', type: 'silo', zone: 'Stockage matières', valeur_remplacement_eur: 150000, matieres_dangereuses: false, confiance: 0.84 },
    ],
  };
}
