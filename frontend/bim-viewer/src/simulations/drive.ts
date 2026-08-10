/**
 * drive — conversion des données réelles du rapport (aléas + BDNB) en
 * paramètres de simulation. AUCUNE donnée inventée : l'intensité de chaque
 * simulation est dérivée de `aleas[*].niveau` (bandes D03) et de la
 * géométrie BDNB déjà affichée par le viewer.
 */

import {
  BuildingInfo,
  HazardKind,
  HazardLevel,
  HAZARD_LEVELS,
  SimPayload
} from "./types";

/** Normalise un libellé : minuscules, sans accents ni tirets. */
export function stripAccents(s: string): string {
  return s
    .toLowerCase()
    .replace(/[àâä]/g, "a")
    .replace(/[éèêë]/g, "e")
    .replace(/[îï]/g, "i")
    .replace(/[ôö]/g, "o")
    .replace(/[ùûü]/g, "u")
    .replace(/ç/g, "c")
    .replace(/-/g, "_")
    .replace(/\s+/g, "_");
}

/** Normalise une valeur `niveau` D03 (robuste aux accents / tirets). */
export function normalizeLevel(raw?: string | null): HazardLevel | null {
  if (!raw) {
    return null;
  }
  const s = stripAccents(String(raw));
  if ((HAZARD_LEVELS as string[]).indexOf(s) !== -1) {
    return s as HazardLevel;
  }
  // Tolérance : "faiblement" → faible, "très-faible" → tres_faible...
  if (s.indexOf("faible") !== -1) {
    return s.startsWith("tres") ? "tres_faible" : "faible";
  }
  if (s.indexOf("modere") !== -1) {
    return "modere";
  }
  if (s.indexOf("eleve") !== -1) {
    return "eleve";
  }
  if (s.indexOf("critique") !== -1) {
    return "critique";
  }
  return null;
}

/** Position d'un niveau sur l'échelle 0..1 (tres_faible → 0.05…critique → 1). */
export function levelIntensity(level: HazardLevel): number {
  return (HAZARD_LEVELS.indexOf(level) + 1) / HAZARD_LEVELS.length;
}

/**
 * Code d'aléa backend (inondation, sismicite, feu_foret, mouvement_terrain…)
 * → simulation concernée. Retourne null pour les aléas non simulables
 * (radon, rga, cavite, ppr, ssp, icpe, canalisations, avalanche…).
 */
export function hazardForCode(code?: string | null): HazardKind | null {
  if (!code) {
    return null;
  }
  const c = stripAccents(String(code));
  if (
    c.indexOf("inondation") !== -1 ||
    c.indexOf("submersion") !== -1 ||
    c.indexOf("ruissellement") !== -1 ||
    c.indexOf("coulee") !== -1 ||
    c.indexOf("crue") !== -1
  ) {
    return "flood";
  }
  if (c.indexOf("feu") !== -1 || c.indexOf("incendie") !== -1) {
    return "fire";
  }
  if (
    c.indexOf("seisme") !== -1 ||
    c.indexOf("sism") !== -1 ||
    c.indexOf("seismic") !== -1
  ) {
    return "seismic";
  }
  return null;
}

export interface DrivenState {
  /** niveau dérivé du rapport (null si l'aléa n'est pas présent/renseigné) */
  level: HazardLevel | null;
  /** l'aléa est recensé comme présent dans le rapport */
  present: boolean;
}

/**
 * Extrait, pour chaque simulation, le niveau et la présence depuis le
 * payload du rapport. L'intensité VISUELLE suit donc exactement les bandes
 * D03 calculées par le backend.
 */
export function driveFromPayload(payload: SimPayload | null): Record<HazardKind, DrivenState> {
  const out: Record<HazardKind, DrivenState> = {
    flood: { level: null, present: false },
    fire: { level: null, present: false },
    seismic: { level: null, present: false }
  };
  const aleas = payload && payload.aleas ? payload.aleas : [];
  for (const alea of aleas) {
    const kind = hazardForCode(alea && alea.code);
    if (!kind) {
      continue;
    }
    const level = normalizeLevel(alea && alea.niveau);
    const present = alea && alea.present === true;
    if (out[kind].level === null && level) {
      out[kind].level = level;
    }
    if (present) {
      out[kind].present = true;
    }
  }
  return out;
}

/** Infos géométriques du bâtiment depuis le payload BDNB + la scène. */
export function buildingInfoFromPayload(payload: SimPayload | null): Partial<BuildingInfo> {
  const b = payload && payload.batiment ? payload.batiment : {};
  const info: Partial<BuildingInfo> = {};
  const h = b.hauteur_mean;
  if (typeof h === "number" && h > 0) {
    info.height = h;
  }
  const n = b.nb_niveau;
  if (typeof n === "number" && n > 0) {
    info.floors = Math.min(Math.max(Math.round(n), 1), 12);
  }
  return info;
}

/** Légende pédagogique : hauteur d'eau cible par niveau (mètres). */
export const FLOOD_HEIGHTS: Record<HazardLevel, number> = {
  tres_faible: 0.05,
  faible: 0.2,
  modere: 0.6,
  eleve: 1.2,
  critique: 2.2
};

/** Légende pédagogique : hauteur de flamme indicative par niveau (mètres). */
export const FIRE_HEIGHTS: Record<HazardLevel, number> = {
  tres_faible: 1.2,
  faible: 2.0,
  modere: 3.2,
  eleve: 5.0,
  critique: 8.0
};

/** Légende pédagogique : amplitude du cisaillement sismique (mètres). */
export const SEISMIC_SWAY: Record<HazardLevel, number> = {
  tres_faible: 0.02,
  faible: 0.06,
  modere: 0.14,
  eleve: 0.28,
  critique: 0.45
};

/** Durée d'une secousse complète (s) — critique dure plus longtemps. */
export function seismicDuration(level: HazardLevel): number {
  return level === "critique" ? 24 : level === "eleve" ? 16 : 10;
}
