/* =========================================================================
   Types du volet économique — contrat de sortie de
   POST /diagnostic/retour-investissement (cf. docs/STRATEGIE_RETOUR_INVESTISSEMENT.md §6)
   ========================================================================= */

export type StatutEconomique = "calcule" | "fourchette" | "null";

export interface SourceRef {
  id: string;
  reference: string;
}

/** Bloc standard : chaque montant est {valeur|min|max, statut, sources, hypotheses}. */
export interface BlocEconomique {
  statut: StatutEconomique | "cadre_reglementaire_a_venir";
  valeur?: number | null;
  min?: number | null;
  max?: number | null;
  sources: SourceRef[];
  hypotheses: string[];
  confidence?: number | null;
  raison?: string | null;
}

export interface MesureEffet {
  mesure: string;
  zone: string;
  cible?: string;
  efficacite?: number;
  risque_avant?: number;
  risque_apres?: number;
  delta?: number;
  statut: StatutEconomique;
  sources?: SourceRef[];
  hypotheses?: string[];
  confidence?: number | null;
  raison?: string | null;
}

export interface ZoneEffet {
  zone: string;
  risque_avant: number;
  risque_apres: number;
  delta: number;
  n_mesures_appliquees: number;
  mesures: MesureEffet[];
}

export interface NiveauA {
  score_global_avant: number | null;
  score_global_apres: number | null;
  delta_global: number;
  par_zone: ZoneEffet[];
  par_mesure: MesureEffet[];
  statut: StatutEconomique;
  raison?: string | null;
}

export interface BeneficeAlea {
  alea: string;
  label: string;
  nb_arretes: number;
  probabilite_annuelle: number;
  benefice: BlocEconomique;
  statut: StatutEconomique;
}

export interface BeneficeAssurance {
  par_alea: Record<string, BeneficeAlea>;
  total: BlocEconomique;
  modulation_surprime: {
    statut: string;
    valeur: number;
    sources: SourceRef[];
    raison: string;
  };
}

export interface MesureCout {
  zone: string;
  mesure: string;
  cout_brut_min: number;
  cout_brut_max: number;
  eligible_fprnm: boolean;
  subvention_taux: number;
  sources: SourceRef[];
}

export interface CoutTravaux {
  par_mesure: MesureCout[];
  total_brut: BlocEconomique;
  subvention_fprnm: BlocEconomique;
  cout_net: BlocEconomique;
  statut: StatutEconomique;
  n_recommandations: number;
  n_avec_cout: number;
}

export interface NiveauB {
  benefice_assurance: BeneficeAssurance;
  cout_travaux: CoutTravaux;
}

export interface ValeurBien {
  surface_m2: number | null;
  nb_transactions_dvf: number;
  prix_m2_median: BlocEconomique | null;
  valeur_reconstruction: BlocEconomique;
  statut: StatutEconomique;
}

export interface Roi {
  temps_de_retour: BlocEconomique;
  benefice_annuel_total: BlocEconomique;
  regle: string;
}

export interface EtudeValeur {
  source_id: string;
  resultat: string;
  limites: string;
}

export interface ValeurImmobiliere {
  exclu_du_roi: boolean;
  raison: string;
  etudes: EtudeValeur[];
}

export interface Confidence {
  score: number;
  niveau: string;
  composantes: Record<string, number>;
}

export interface EconomieContract {
  schema_version: string;
  niveau_a: NiveauA;
  niveau_b: NiveauB;
  niveau_c: BlocEconomique;
  valeur: ValeurBien;
  roi: Roi;
  valeur_immobiliere: ValeurImmobiliere;
  confidence: Confidence;
}

/* ---- Données intermédiaires du pipeline diagnostic ---- */
export interface ResumeDiagnostic {
  building_data: Record<string, unknown>;
  risk_scores: {
    zones: Record<string, any>;
    score_global?: number | null;
  };
  formulaire?: Record<string, unknown> | null;
}

export interface DiagnosticFastResponse extends Record<string, unknown> {
  adresse?: string;
  geometry?: { surface_emprise_m2?: number; largeur_m?: number; longueur_m?: number };
  _resume?: ResumeDiagnostic;
}

export interface ResultatEconomie {
  contract: EconomieContract;
  adresse: string;
  surface_m2?: number | null;
}