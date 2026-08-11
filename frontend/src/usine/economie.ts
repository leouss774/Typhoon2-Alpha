// =============================================================================
//   TYPHOON — /usine : synthèse économique du rapport (déterministe, client)
//   Construite uniquement à partir du risk engine (analyse) et du catalogue
//   de recommandations : valeur des actifs, enveloppe travaux, gain de
//   résilience estimé, sinistres annuels évités et temps de retour indicatif.
//   Aucun appel réseau — toutes les hypothèses sont documentées dans
//   `hypotheses` afin de ne jamais présenter un montant comme certain.
// =============================================================================

import { bandForScore } from './types';
import type { AnalyseUsine } from './types';
import { CATALOGUE, GLOBAL_ACTIONS, parseCostRange } from './recommandations';

export interface ZoneGainEconomie {
  id: string;
  nom: string;
  risqueAvant: number;
  risqueApres: number;
  gain: number;
}

export interface UsineEconomie {
  /* Actifs — valeur de remplacement des équipements renseignés */
  valeurActifsEur: number | null;
  nbEquipementsValeur: number;
  nbDangereux: number;
  nbCritiques: number;
  /* Enveloppe budgétaire des recommandations (min / max / moyenne) */
  enveloppeMin: number;
  enveloppeMax: number;
  /* Gain de résilience estimé (même catalogue que l'étape 5) */
  scoreAvant: number;
  scoreApresEstime: number;
  gainParZone: ZoneGainEconomie[];
  /* Bénéfice annuel estimé (sinistres évités) et temps de retour */
  perteAnnuelleEviteeEur: number | null;
  tempsRetourAns: number | null;
  hypotheses: string[];
}

/* Bandes D03 → niveaux du catalogue (identique à l'étape 5). */
const NIVEAU_CLE: Record<string, 'faible' | 'modere' | 'eleve'> = {
  tres_faible: 'faible',
  faible: 'faible',
  modere: 'modere',
  eleve: 'eleve',
  critique: 'eleve',
};

export function computeUsineEconomie(analyse: AnalyseUsine): UsineEconomie {
  const equipements = analyse.equipements || [];

  /* ── 1. Actifs exposés ── */
  let valeurActifsEur = 0;
  let nbEquipementsValeur = 0;
  let nbDangereux = 0;
  let nbCritiques = 0;
  for (const e of equipements) {
    if (typeof e.valeur_remplacement_eur === 'number' && e.valeur_remplacement_eur > 0) {
      valeurActifsEur += e.valeur_remplacement_eur;
      nbEquipementsValeur += 1;
    }
    if (e.matieres_dangereuses) nbDangereux += 1;
    if (e.critique_production) nbCritiques += 1;
  }

  /* ── 2. Enveloppe travaux + gain de résilience par zone ── */
  let enveloppeMin = 0;
  let enveloppeMax = 0;
  const gainParZone: ZoneGainEconomie[] = [];
  for (const zone of analyse.zones || []) {
    const lvl = NIVEAU_CLE[bandForScore(zone.risque).key] ?? 'modere';
    const items = CATALOGUE[zone.type]?.[lvl] || CATALOGUE[zone.type]?.['modere'] || [];
    let gain = 0;
    for (const r of items) {
      const [lo, hi] = parseCostRange(r.cout_estime);
      enveloppeMin += lo;
      enveloppeMax += hi;
      gain += r.gain_resilience;
    }
    const risqueAvant = zone.risque ?? 0;
    const risqueApres = Math.max(10, Math.round(risqueAvant - gain));
    gainParZone.push({
      id: zone.id,
      nom: zone.nom,
      risqueAvant,
      risqueApres,
      gain: Math.max(0, risqueAvant - risqueApres),
    });
  }
  for (const r of GLOBAL_ACTIONS) {
    const [lo, hi] = parseCostRange(r.cout_estime);
    enveloppeMin += lo;
    enveloppeMax += hi;
  }

  /* ── 3. Score avant → après (moyenne des risques de zones, comme le moteur) ── */
  const scoreAvant = analyse.score_global ?? 0;
  const scoreApresEstime =
    gainParZone.length > 0
      ? Math.max(10, Math.round(gainParZone.reduce((a, z) => a + z.risqueApres, 0) / gainParZone.length))
      : scoreAvant;
  const delta = Math.max(0, scoreAvant - scoreApresEstime);

  /* ── 4. Bénéfice annuel estimé (hypothèse documentée) ──
     Sinistres annuels évités ≈ actifs exposés × (Δscore/100) × P_annuelle,
     où P_annuelle = F/100 (aléa du site ; F neutre = 50 → 50 %/an). */
  const pAnnuelle = Math.min(1, Math.max(0, (analyse.aleas_site?.score ?? 50) / 100));
  const perteAnnuelleEviteeEur =
    valeurActifsEur > 0 && delta > 0
      ? Math.round(valeurActifsEur * (delta / 100) * pAnnuelle)
      : null;

  /* ── 5. Temps de retour indicatif = enveloppe moyenne / bénéfice annuel ── */
  const enveloppeMoyenne = (enveloppeMin + enveloppeMax) / 2;
  const tempsRetourAns =
    perteAnnuelleEviteeEur != null && perteAnnuelleEviteeEur > 0 && enveloppeMoyenne > 0
      ? Math.round((enveloppeMoyenne / perteAnnuelleEviteeEur) * 10) / 10
      : null;

  const aleaLabel = analyse.aleas_site?.libelle ? `« ${analyse.aleas_site.libelle} »` : 'neutre (F = 50)';
  const hypotheses = [
    `Actifs retenus : valeur de remplacement des ${nbEquipementsValeur} équipement(s) valorisé(s) sur ${equipements.length}.`,
    `Probabilité annuelle d'un événement dommageable : aléa du site F (${aleaLabel}), soit ${Math.round(pAnnuelle * 100)} %/an.`,
    `Sinistres annuels évités ≈ actifs × (Δscore/100) × P_annuelle, avec Δscore = ${scoreAvant} → ${scoreApresEstime} pts.`,
    `Enveloppe travaux : somme des recommandations du catalogue (${formatRange(enveloppeMin, enveloppeMax)}), hors études détaillées et frais de maîtrise d'œuvre.`,
    'Ordres de grandeur indicatifs — une étude d\u2019ingénierie et une consultation de fournisseurs restent nécessaires avant tout investissement.',
  ];

  return {
    valeurActifsEur: valeurActifsEur > 0 ? valeurActifsEur : null,
    nbEquipementsValeur,
    nbDangereux,
    nbCritiques,
    enveloppeMin,
    enveloppeMax,
    scoreAvant,
    scoreApresEstime,
    gainParZone,
    perteAnnuelleEviteeEur,
    tempsRetourAns,
    hypotheses,
  };
}

/** « 40 000 € » si min == max, sinon « 30 000 – 95 000 € ». */
export function formatRange(min: number, max: number): string {
  const fmt = (n: number) => Math.round(n).toLocaleString('fr-FR');
  if (min <= 0 && max <= 0) return 'non estimé';
  return min === max ? `${fmt(min)} €` : `${fmt(min)} – ${fmt(max)} €`;
}
