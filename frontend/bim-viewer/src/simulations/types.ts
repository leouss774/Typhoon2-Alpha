/**
 * Types partagés du module « Simulations » (catastrophes naturelles dans le
 * jumeau BIM). Niveaux D03 : mêmes clés que le backend (`risque_report.py`),
 * normalisées sans accents ni tirets (`tres_faible`, `modere`, `eleve`...).
 *
 * Avertissement pédagogique (à afficher côté UI) :
 * « Simulation visuelle à but pédagogique — ne remplace pas une étude
 * d'ingénierie (modélisation hydraulique, thermique ou sismique
 * réglementaire). »
 */

export type HazardKind = "flood" | "fire" | "seismic";

export const HAZARD_KINDS: HazardKind[] = ["flood", "fire", "seismic"];

export type HazardLevel = "tres_faible" | "faible" | "modere" | "eleve" | "critique";

export const HAZARD_LEVELS: HazardLevel[] = [
  "tres_faible",
  "faible",
  "modere",
  "eleve",
  "critique"
];

export const HAZARD_LABELS: Record<HazardKind, string> = {
  flood: "Inondation",
  fire: "Feu",
  seismic: "Séisme"
};

/** État d'une simulation (activée/désactivée + niveau + vitesse temps réel). */
export interface HazardState {
  enabled: boolean;
  level: HazardLevel;
  speed: number;
}

export interface SimulationState {
  flood: HazardState;
  fire: HazardState;
  seismic: HazardState;
}

export function defaultState(): SimulationState {
  return {
    flood: { enabled: false, level: "modere", speed: 1 },
    fire: { enabled: false, level: "modere", speed: 1 },
    seismic: { enabled: false, level: "modere", speed: 1 }
  };
}

/** Sous-ensemble `aleas[*]` du rapport RisqueReport (contrat frontend). */
export interface AleaLike {
  code?: string | null;
  libelle?: string | null;
  present?: boolean | null;
  niveau?: string | null;
}

/**
 * Payload reçu du parent React (postMessage `typhoon:sim`) ou lu dans les
 * query params : les aléas réels du rapport + les données BDNB du bâtiment.
 * `source` : "rapport" (intensités dérivées des données) ou "manuel"
 * (projets d'exemple sans données typhon → niveaux réglés à la main).
 */
export interface SimPayload {
  aleas?: AleaLike[] | null;
  batiment?: Record<string, unknown> | null;
  source?: string;
}

/** Informations géométriques du bâtiment utiles aux simulations. */
export interface BuildingInfo {
  height: number;
  floors: number;
  /** demi-extensions du rectangle englobant au sol (x, z) en mètres */
  halfExtents: { x: number; z: number };
  /** hauteur d'un niveau en mètres (hauteur / nb étages, bornée) */
  levelHeight: number;
}
