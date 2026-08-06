// =============================================================================
//   TYPHOON — /zone : configuration partagée (API, bandes D03, couches)
//   Reprend le contrat du legacy zone.html (backend port 8765).
// =============================================================================

export const API: string =
  (import.meta as any).env?.VITE_API_BASE ||
  (window as any).TYPHOON_API ||
  'http://127.0.0.1:8765';

// ---------------------------------------------------------------------------
// Bandes D03 (5 niveaux — mêmes clés que le backend risque_report.py)
// ---------------------------------------------------------------------------

export interface D03Band {
  key: string;
  label: string;
  color: string;
  cls: string;
  max: number;
}

export const D03: D03Band[] = [
  { key: 'tres_faible', label: 'Très faible', color: '#3A7A6C', cls: 'd03-tres-faible', max: 20 },
  { key: 'faible',      label: 'Faible',      color: '#6E9E52', cls: 'd03-faible',      max: 40 },
  { key: 'modere',      label: 'Modéré',      color: '#D4AC3E', cls: 'd03-modere',      max: 60 },
  { key: 'eleve',       label: 'Élevé',       color: '#D07030', cls: 'd03-eleve',       max: 80 },
  { key: 'critique',    label: 'Critique',    color: '#B03020', cls: 'd03-critique',    max: Infinity },
];

export function bandForKey(key?: string | null): D03Band | undefined {
  return D03.find((b) => b.key === key);
}

export function aleaScore(a: { niveau?: string | null }): number {
  const mapping: Record<string, number> = {
    tres_faible: 10,
    faible: 30,
    modere: 50,
    eleve: 70,
    critique: 90,
  };
  return mapping[a.niveau || ''] || 0;
}

export function escHtml(s: unknown): string {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Icônes Material Symbols par aléa
// ---------------------------------------------------------------------------

export const ALEA_ICONS: Record<string, string> = {
  inondation: 'flood',
  rga: 'grass',
  sismicite: 'crisis_alert',
  radon: 'science',
  feu_foret: 'local_fire_department',
  mouvement_terrain: 'landslide',
  ppr: 'gpp_maybe',
  ssp: 'factory',
  cavite: 'landscape',
  avalanche: 'terrain',
  icpe: 'apartment',
  canalisations: 'plumbing',
  vent_cyclonique: 'cyclone',
  territoires: 'map',
};
export const ALEA_ICON_FALLBACK = 'warning';

// ---------------------------------------------------------------------------
// Couches cartographiques (WMS BRGM confirmé + WFS Géorisques)
// ---------------------------------------------------------------------------

export const WMS_BASE = 'https://mapsref.brgm.fr/wxs/georisques/risques';

export const WMS_LAYER_MAP: Record<string, string> = {
  rga: 'ALEARG',
  inondation: 'LIMITETRI_FXX',
  sismicite: 'SIS_INTENSITE_MAXCOM',
  avalanche: 'PPRN_COMMUNE_AVALANCHE_APPROUV',
  cavite: 'CAVITE_LOCALISEE',
  feu_foret: 'PPRN_COMMUNE_FEU_APPROUV',
  icpe: 'INSTALLATIONS_CLASSEES_SIMPLIFIE',
  mouvement_terrain: 'MVT_LOCALISE',
  radon: 'RADON',
  canalisations: 'CANALISATIONS',
  ppr: 'PPRN_COMMUNE_GASPAR',
};

export const WFS_BASE = 'https://www.georisques.gouv.fr/services';

export const WFS_LAYER_MAP: Record<string, string[]> = {
  ssp: ['ms:SSP_CLASSIF_SIS_GE'],
};

// ---------------------------------------------------------------------------
// Types du contrat RisqueReport (backend app/schemas/risque_report.py)
// ---------------------------------------------------------------------------

export interface CatNatEvent {
  libelle_risque_jo?: string | null;
  libelle?: string | null;
  date_debut_evt?: string | null;
}

export interface AleaDetail {
  code: string;
  libelle: string;
  present: boolean | null;
  present_commune?: boolean | null;
  niveau?: string | null;
  zonage?: string | null;
  catnat_historique?: CatNatEvent[] | null;
  source?: string;
  url_detail?: string | null;
  erreur?: string | null;
}

export interface TypeBatiment {
  type: string;             // "industriel" | "residentiel" | "inconnu"
  confiance: number;        // 0-1
  tags?: Record<string, unknown>;
  nom?: string | null;
  erreur?: string | null;
}

export interface RisqueReport {
  adresse_saisie: string;
  adresse_normalisee: string;
  lat: number;
  lon: number;
  code_insee: string;
  date_generation: string;
  alea_count: number;
  aleas: AleaDetail[];
  erreurs_partielles: string[];
  type_batiment?: TypeBatiment | null;  // détection Overpass (usine vs maison)
  avertissement?: string;
}

export interface GeocodeSuggestion {
  label: string;
  city: string;
  context?: string;
  citycode?: string;
  postcode?: string;
  score?: number;
  lat?: number;
  lon?: number;
}

// ---------------------------------------------------------------------------
// Types du rapport narratif IA (backend app/recommandations/rapport_narratif.py)
// Endpoint POST /diagnostic/adresse/rapport — body = RisqueReport → RapportNarratif
// ---------------------------------------------------------------------------

export interface SectionRapport {
  titre: string;
  contenu: string;
  aleas_associes?: string[];
}

export interface RapportNarratif {
  introduction: string;
  sections: SectionRapport[];
  synthese_finale: string;
  obligations_reglementaires?: string[] | null;
  genere_par?: string;
  metadata?: Record<string, unknown>;
  avertissement_ia?: string;
}
