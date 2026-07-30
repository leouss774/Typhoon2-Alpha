/* =========================================================================
   Types pour le Matching Artisans
   ========================================================================= */

/* ---- Entrée : recommandation à chercher ---- */
export interface RecommandationInput {
  cle?: string | null;
  mesure?: string | null;
  zone?: string | null;
  risques?: string[] | null;
  priorite?: string | null;
}

/* ---- Sortie : une entreprise trouvée ---- */
export interface Entreprise {
  nom_entreprise?: string;
  siret?: string;
  siren?: string;
  adresse?: string;
  code_postal?: string;
  commune?: string;
  telephone?: string;
  email?: string;
  site_internet?: string;
  lien_fiche_officielle?: string | null;
  score_objectif_sur_100?: number;
  qualification_valide?: boolean;
  details_score?: string[];
  domaine?: string;
  organisme?: string;
  date_creation?: string;
  distance_km?: number | null;
  anciennete_rge_ans?: number | null;
}

/* ---- Sortie : une recommandation traitée ---- */
export interface RecommandationTraitee {
  cle?: string;
  categorie: "rge" | "non_rge" | "inconnue";
  priorite?: string;
  libelle?: string;
  domaine_recherche?: string;
  code_naf_recherche?: string;
  entreprises: Entreprise[];
  annuaire_reference?: {
    organisme?: string;
    url?: string;
    note?: string;
  };
  erreur?: string;
  zone_origine?: string;
  risques_origine?: string[];
  mesure_originale?: string;
  cout_estime?: {
    montant_min?: number;
    montant_max?: number;
    devise?: string;
    unite?: string;
    hypotheses?: string;
    fiabilite?: string;
  };
}

/* ---- Résumé de la recherche ---- */
export interface ResumeMatching {
  total_recommandations_traitees: number;
  total_entreprises_trouvees: number;
  details_categories: Record<string, number>;
}

/* ---- Informations de géocodage ---- */
export interface GeocodingInfo {
  label: string;
  city: string;
  citycode: string;
  postcode: string;
  lat: number;
  lon: number;
  score: number;
}

/* ---- Réponse complète de l'API ---- */
export interface ArtisanMatchingResponse {
  adresse: string;
  code_postal: string;
  recommandations_traitees: RecommandationTraitee[];
  resume: ResumeMatching;
  geocoding?: GeocodingInfo | null;
}

/* ---- Domaine disponible ---- */
export interface DomaineInfo {
  libelle: string;
  categorie: "rge" | "non_rge";
  code_naf?: string;
  annuaire?: string;
}

/* ---- État du formulaire ---- */
export interface ArtisanFormState {
  adresse: string;
  codePostal: string;
  recosRaw: string;
  loading: boolean;
}
