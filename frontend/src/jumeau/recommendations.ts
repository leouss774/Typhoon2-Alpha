export type RecommendationSource = {
  source_id?: string;
  fiche_id?: string;
  organisme?: string;
  titre?: string;
};

export type RecommendationCost = {
  montant_min?: number | null;
  montant_max?: number | null;
  devise?: string | null;
  unite?: string | null;
  date_estimation?: string | null;
  zone_geo?: string | null;
  hypotheses?: string | null;
};

export type RecommendationAid = {
  dispositif?: string | null;
  conditions?: string | null;
  statut?: string | null;
};

export type ZoneRecommendation = {
  mesure?: string;
  travaux?: string;
  explication?: string;
  risque_concerne?: string;
  type?: string;
  priorite?: string;
  cout_estime?: RecommendationCost | string | null;
  gain_resilience?: number | null;
  aide?: RecommendationAid | null;
  sources?: RecommendationSource[];
};

export type RecommendationZone = {
  niveau?: string;
  risque?: number;
  alea_principal?: string;
  recommandations?: ZoneRecommendation[];
};

export type RecommendationsSnapshot = {
  zones: Record<string, RecommendationZone>;
  ready: boolean;
};

export type RecommendationSort = 'criticite' | 'cout_asc' | 'cout_desc' | 'gain';

export type AggregatedRecommendation = ZoneRecommendation & {
  id: string;
  zone: string;
  zoneLevel: string;
  zoneRisk: number | null;
  costMin: number | null;
  costMax: number | null;
  gain: number | null;
};

const LEVEL_RANK: Record<string, number> = {
  critique: 4,
  eleve: 3,
  modere: 2,
  faible: 1,
};

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function recommendationCost(cost: ZoneRecommendation['cout_estime']): {
  min: number | null;
  max: number | null;
} {
  if (!cost || typeof cost !== 'object') return { min: null, max: null };
  const min = finiteNumber(cost.montant_min);
  const max = finiteNumber(cost.montant_max);
  return { min: min ?? max, max: max ?? min };
}

export function aggregateRecommendations(
  zones: Record<string, RecommendationZone>,
): AggregatedRecommendation[] {
  const result: AggregatedRecommendation[] = [];
  Object.entries(zones || {}).forEach(([zone, zoneData]) => {
    (zoneData.recommandations || []).forEach((recommendation, index) => {
      const cost = recommendationCost(recommendation.cout_estime);
      result.push({
        ...recommendation,
        id: `${zone}:${index}`,
        zone,
        zoneLevel: zoneData.niveau || 'inconnu',
        zoneRisk: finiteNumber(zoneData.risque),
        costMin: cost.min,
        costMax: cost.max,
        gain: finiteNumber(recommendation.gain_resilience),
      });
    });
  });
  return result;
}

function compareNullable(
  left: number | null,
  right: number | null,
  direction: 'asc' | 'desc',
): number {
  // Missing values always remain at the end, in both directions.
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  return direction === 'asc' ? left - right : right - left;
}

export function sortRecommendations(
  recommendations: AggregatedRecommendation[],
  sort: RecommendationSort,
): AggregatedRecommendation[] {
  return [...recommendations].sort((left, right) => {
    let result = 0;
    if (sort === 'cout_asc') result = compareNullable(left.costMin, right.costMin, 'asc');
    else if (sort === 'cout_desc') result = compareNullable(left.costMax, right.costMax, 'desc');
    else if (sort === 'gain') result = compareNullable(left.gain, right.gain, 'desc');
    else {
      result = (LEVEL_RANK[right.zoneLevel] || 0) - (LEVEL_RANK[left.zoneLevel] || 0);
      if (result === 0) result = compareNullable(left.zoneRisk, right.zoneRisk, 'desc');
    }
    return result || left.id.localeCompare(right.id, 'fr');
  });
}

export function formatZoneLabel(zone: string): string {
  return zone
    .replace(/_/g, ' ')
    .replace(/\b\p{L}/gu, (letter) => letter.toUpperCase());
}

export function formatCost(recommendation: AggregatedRecommendation): string | null {
  if (recommendation.costMin === null && recommendation.costMax === null) return null;
  const raw = recommendation.cout_estime;
  const currency = typeof raw === 'object' && raw?.devise ? raw.devise : '€';
  const unit = typeof raw === 'object' && raw?.unite ? ` ${raw.unite}` : '';
  const formatter = new Intl.NumberFormat('fr-FR');
  const amount = recommendation.costMin !== recommendation.costMax
    ? `${formatter.format(recommendation.costMin!)} – ${formatter.format(recommendation.costMax!)}`
    : formatter.format(recommendation.costMin ?? recommendation.costMax!);
  return `${amount} ${currency}${unit}`;
}
