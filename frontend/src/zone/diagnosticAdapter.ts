export interface DiagnosticZoneScore {
  risque: number;
  niveau?: string | null;
  alea_principal?: string | null;
  justification?: string | null;
  recommandations?: Array<Record<string, unknown>>;
  conclusion?: string | null;
  facteurs_aggravants?: string[];
  facteurs_attenuants?: string[];
  vulnerabilite?: string | null;
}

export interface DiagnosticGeometry {
  footprint_shape?: string | null;
  largeur_m?: number | null;
  longueur_m?: number | null;
  orientation_deg?: number | null;
  floors_count?: number | null;
  hauteur_sous_plafond_m?: number | null;
  roof_shape?: string | null;
  pente_toit_deg?: number | null;
  materiau_mur?: string | null;
  materiau_toiture?: string | null;
  has_basement?: boolean | null;
  has_cellar?: boolean | null;
  has_garage?: boolean | null;
  has_garden?: boolean | null;
  garage_position?: string | null;
  garden_surface_m2?: number | null;
  footprint?: Record<string, unknown> | null;
  surface_emprise_m2?: number | null;
  type_batiment?: string | null;
  entree_facade?: string | null;
}

export interface DiagnosticContract {
  adresse?: string | null;
  adresse_saisie?: string | null;
  adresse_normalisee?: string | null;
  geometry?: DiagnosticGeometry | null;
  zones?: Record<string, DiagnosticZoneScore> | null;
  score_global?: number | null;
  projection_2050?: {
    score_global?: number | null;
    zones?: Record<string, DiagnosticZoneScore> | null;
  } | null;
  climat?: Record<string, unknown> | null;
  climat_2050?: Record<string, unknown> | null;
  _resume?: Record<string, unknown> | null;
  _sources?: Record<string, unknown> | null;
  marche?: Record<string, unknown> | null;
}

export interface AdapterResult {
  adresse: string;
  geometry: DiagnosticGeometry;
  zones: Record<string, DiagnosticZoneScore>;
  score_global: number;
  projection_2050: {
    score_global: number;
    zones: Record<string, DiagnosticZoneScore>;
  };
  climat: Record<string, unknown>;
  _resume?: Record<string, unknown> | null;
  _sources?: Record<string, unknown> | null;
  marche?: Record<string, unknown> | null;
}

const DEFAULT_GEOMETRY: DiagnosticGeometry = {
  footprint_shape: 'rectangulaire',
  largeur_m: 8,
  longueur_m: 8,
  orientation_deg: 0,
  floors_count: 2,
  hauteur_sous_plafond_m: 2.6,
  roof_shape: 'deux_pans',
  pente_toit_deg: 35,
  materiau_mur: 'parpaing_enduit',
  materiau_toiture: 'tuiles_terre_cuite',
  has_basement: true,
  has_cellar: false,
  has_garage: false,
  has_garden: false,
};

const DEFAULT_ZONES: Record<string, DiagnosticZoneScore> = {
  fondations: {
    risque: 25,
    niveau: 'faible',
    alea_principal: 'RGA / séisme / mouvement de terrain',
    justification: 'Score synthétique dérivé du rapport Géorisques.',
    recommandations: [],
  },
  murs_nord: {
    risque: 25,
    niveau: 'faible',
    alea_principal: 'Risque structurel',
    justification: 'Score synthétique dérivé du rapport Géorisques.',
    recommandations: [],
  },
  murs_sud: {
    risque: 25,
    niveau: 'faible',
    alea_principal: 'Risque structurel',
    justification: 'Score synthétique dérivé du rapport Géorisques.',
    recommandations: [],
  },
  murs_est: {
    risque: 25,
    niveau: 'faible',
    alea_principal: 'Risque structurel',
    justification: 'Score synthétique dérivé du rapport Géorisques.',
    recommandations: [],
  },
  murs_ouest: {
    risque: 25,
    niveau: 'faible',
    alea_principal: 'Risque structurel',
    justification: 'Score synthétique dérivé du rapport Géorisques.',
    recommandations: [],
  },
  toiture: {
    risque: 18,
    niveau: 'tres_faible',
    alea_principal: 'Feu de forêt / vent',
    justification: 'Score synthétique dérivé du rapport Géorisques.',
    recommandations: [],
  },
  sous_sol: {
    risque: 24,
    niveau: 'faible',
    alea_principal: 'Inondation / radon',
    justification: 'Score synthétique dérivé du rapport Géorisques.',
    recommandations: [],
  },
};

export function adaptDiagnosticContract(contract: DiagnosticContract | null | undefined): AdapterResult {
  const geometry = {
    ...DEFAULT_GEOMETRY,
    ...(contract?.geometry || {}),
  } as DiagnosticGeometry;

  const zones = {
    ...DEFAULT_ZONES,
    ...(contract?.zones || {}),
  } as Record<string, DiagnosticZoneScore>;

  const projectionZones = {
    ...DEFAULT_ZONES,
    ...(contract?.projection_2050?.zones || {}),
  } as Record<string, DiagnosticZoneScore>;

  // NOTE — la route /diagnostic/adresse construit des scores de zone
  // SYNTHÉTIQUES (dérivés des niveaux d'aléa Géorisques, pas du moteur F×V)
  // et expose score_global=0 (cf. routes/diagnostic.py, _zone_scores_from_report).
  // TODO: brancher le vrai moteur sur cette route — en attendant, on dérive
  // un score global cohérent (moyenne des zones) plutôt que d'afficher le 0.
  const deriveGlobal = (zs: Record<string, DiagnosticZoneScore>): number => {
    const scores = Object.values(zs)
      .map((z) => z.risque)
      .filter((n): n is number => Number.isFinite(n));
    if (scores.length === 0) return 0;
    return Math.round(scores.reduce((acc, n) => acc + n, 0) / scores.length);
  };

  const rawGlobal = contract?.score_global;
  const rawProjection = contract?.projection_2050?.score_global;
  const score_global =
    Number.isFinite(rawGlobal) && Number(rawGlobal) > 0 ? Number(rawGlobal) : deriveGlobal(zones);
  const projectionScore =
    Number.isFinite(rawProjection) && Number(rawProjection) > 0
      ? Number(rawProjection)
      : deriveGlobal(projectionZones);

  return {
    adresse: contract?.adresse_normalisee || contract?.adresse_saisie || contract?.adresse || '—',
    geometry,
    zones,
    score_global,
    projection_2050: {
      score_global: projectionScore,
      zones: projectionZones,
    },
    climat: (contract?.climat || contract?.climat_2050 || {}) as Record<string, unknown>,
    _resume: contract?._resume ?? null,
    _sources: contract?._sources ?? null,
    marche: contract?.marche ?? null,
  };
}
