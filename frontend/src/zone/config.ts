// =============================================================================
//   TYPHOON — /zone : configuration partagée (API, bandes D03, couches)
//   Reprend le contrat du legacy zone.html (backend port 8765).
// =============================================================================

export const API: string =
  (import.meta as any).env?.VITE_API_BASE ||
  (window as any).TYPHOON_API ||
  'http://127.0.0.1:8765';

// ---------------------------------------------------------------------------
// Robot companion 3D — interface branchée sur le même backend /api/chat/stream
// pour garder des réponses identiques au chatbot classique.
// ---------------------------------------------------------------------------

export const ROBOT_COMPANION_URL: string =
  (import.meta as any).env?.VITE_ROBOT_URL ||
  (window as any).TYPHOON_ROBOT_URL ||
  'http://localhost:5174';

// ---------------------------------------------------------------------------
// Assistant Rapport IA 3D — avatar TalkingHead (port 5175) branché sur le
// même backend /api/chat/stream. Le contexte du rapport est envoyé par
// postMessage depuis ReportChatbot → réponses identiques au chat « Aide ? ».
// ---------------------------------------------------------------------------

export const REPORT_TALKING_HEAD_URL: string =
  (import.meta as any).env?.VITE_TALKING_HEAD_URL ||
  (window as any).TYPHOON_TALKING_HEAD_URL ||
  'http://localhost:5175';

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
  bdnb?: BdnbAsset | null;
  recommandations?: RecommandationsIA | null;
  avertissement?: string;
}

export interface RecommandationsIA {
  resume: string;
  actions_prioritaires: string[];
  points_vigilance?: string[];
  modele?: string;
  metadata?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Fiche BDNB (étape 3 « Analyse ») — backend app/connectors/bdnb.py
// batiment_groupe_complet : 139 champs ; on ne type que ceux affichés.
// Beaucoup sont null (ex. énergie/DPE sur les bâtiments anciens) — l'UI
// affiche « donnée non renseignée » dans ce cas.
// ---------------------------------------------------------------------------

export interface BdnbBatiment {
  // Identité
  batiment_groupe_id?: string | null;
  cle_interop_adr?: string | null;
  cle_interop_adr_principale_ban?: string | null;
  libelle_adr_principale_ban?: string | null;
  // Administration
  code_commune_insee?: string | null;
  libelle_commune_insee?: string | null;
  code_departement_insee?: string | null;
  code_region_insee?: string | null;
  code_epci_insee?: string | null;
  code_iris?: string | null;
  // Construction
  annee_construction?: number | null;
  hauteur_mean?: number | null;
  nb_niveau?: number | null;
  nb_log?: number | null;
  surface_emprise_sol?: number | null;
  s_geom_groupe?: number | null;
  altitude_sol_mean?: number | null;
  mat_mur_txt?: string | null;
  mat_toit_txt?: string | null;
  usage_principal_bdnb_open?: string | null;
  usage_niveau_1_txt?: string | null;
  nb_adresse_valid_ban?: number | null;
  // Cadre / patrimoine / urbanisme
  l_parcelle_id?: string[] | null;
  l_cle_interop_adr?: string[] | null;
  zone_plu_bati_patrimonial?: boolean | null;
  contrainte_urbanisme_ac1?: boolean | null;
  perimetre_bat_historique?: boolean | null;
  denomination_monument_historique?: string | null;
  nom_batiment_historique_plus_proche?: string | null;
  distance_monument_historique?: number | null;
  distance_batiment_historique_plus_proche?: number | null;
  // Risque & fiabilité
  alea_argile?: string | null;
  contient_fictive_geom_groupe?: boolean | null;
  fiabilite_cr_adr_niv_1?: string | null;
  fiabilite_cr_adr_niv_2?: string | null;
  fiabilite_hauteur?: string | null;
  fiabilite_emprise_sol?: string | null;
  // Géométrie — GeoJSON (Polygon ou MultiPolygon), EPSG:2154 (Lambert-93)
  geom_groupe?: unknown | null;
  // Énergie / DPE (souvent null)
  classe_bilan_dpe?: string | null;
  conso_5_usages_ep_m2?: number | null;
  emission_ges_5_usages_m2?: number | null;
  date_reception_dpe?: string | null;
  type_batiment_dpe?: string | null;
  type_energie_chauffage?: string | null;
  type_generateur_chauffage?: string | null;
  type_isolation_mur_exterieur?: string | null;
  type_isolation_plancher_haut?: string | null;
  type_isolation_plancher_bas?: string | null;
  type_vitrage?: string | null;
  type_production_energie_renouvelable?: string | null;
  // ENR — potentiels BDNB (souvent renseignés même sans DPE)
  batenr_favorabilite_solaire_thermique?: boolean | null;
  batenr_favorabilite_geothermie_sonde?: boolean | null;
  batenr_favorabilite_geothermie_nappe?: boolean | null;
  batenr_potentiel_prod_solaire_thermique_annuelle?: number | null;
  batenr_potentiel_prod_solaire_thermique_ete?: number | null;
}

export interface BdnbAsset {
  cle_interop_adr?: string | null;
  batiment?: BdnbBatiment | null;
  autres_batiments_meme_adresse?: BdnbBatiment[] | null;
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
