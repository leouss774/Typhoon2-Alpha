// =============================================================================
//   TYPHOON — /usine : étape 5 « Recommandations » — plan d'adaptation
//   Recommandations par zone générées à partir du risk engine (type de zone
//   × niveau de risque × équipements critiques / dangereux).
// =============================================================================

import { useMemo } from 'react';
import {
  bandForScore,
  TYPE_EQUIP_LABELS,
  TYPE_ZONE_LABELS,
  type AnalyseUsine,
  type ZonePlan,
} from '../usine/types';

type Recommendation = {
  travaux: string;
  cout_estime: string;
  gain_resilience: number;
  priorite: 'urgent' | 'recommande' | 'anticipation';
};

const CATALOGUE: Record<string, Record<string, Recommendation[]>> = {
  production: {
    eleve: [
      { travaux: 'Confinement et sécurisation des lignes critiques (bornes de coupure, réarmement automatique)', cout_estime: '25 000 – 60 000 €', gain_resilience: 28, priorite: 'urgent' },
      { travaux: 'Redondance des équipements vitaux (groupe froid, compresseur) et contrats de maintenance préventive', cout_estime: '40 000 – 120 000 €', gain_resilience: 24, priorite: 'recommande' },
      { travaux: 'Système de surveillance et d\'alerte (capteurs température, vibrations, fuite)', cout_estime: '8 000 – 20 000 €', gain_resilience: 18, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Révision et fiabilisation des automates et commandes électriques', cout_estime: '12 000 – 35 000 €', gain_resilience: 16, priorite: 'recommande' },
      { travaux: 'Plan de continuité d\'activité (PCA) avec procédures de repli des lignes critiques', cout_estime: '3 000 – 10 000 €', gain_resilience: 12, priorite: 'anticipation' },
    ],
    faible: [
      { travaux: 'Suivi annuel des équipements et mise à jour des consignes', cout_estime: '2 000 – 6 000 €', gain_resilience: 6, priorite: 'anticipation' },
    ],
  },
  stockage: {
    eleve: [
      { travaux: 'Renforcement du rackage et des allées de manutention (protège-poteaux, fixations antisismiques)', cout_estime: '15 000 – 45 000 €', gain_resilience: 22, priorite: 'urgent' },
      { travaux: 'Murs et portes coupe-feu entre zones de stockage et ateliers', cout_estime: '20 000 – 70 000 €', gain_resilience: 20, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Surélévation des stocks hors sol et séparation des matières incompatibles', cout_estime: '5 000 – 18 000 €', gain_resilience: 14, priorite: 'recommande' },
    ],
    faible: [
      { travaux: 'Inventaire et optimisation des flux de stockage', cout_estime: '1 000 – 4 000 €', gain_resilience: 5, priorite: 'anticipation' },
    ],
  },
  cuves: {
    eleve: [
      { travaux: 'Mise en place de cuvettes de rétention et de vannes de sécurité automatiques', cout_estime: '30 000 – 90 000 €', gain_resilience: 30, priorite: 'urgent' },
      { travaux: 'Capteurs de niveau, pression et détection de fuite avec télésurveillance', cout_estime: '10 000 – 25 000 €', gain_resilience: 22, priorite: 'urgent' },
      { travaux: 'Ancrage et renforcement des supports de cuves et réservoirs', cout_estime: '12 000 – 40 000 €', gain_resilience: 16, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Plan d\'intervention d\'urgence avec exercices réguliers', cout_estime: '2 000 – 8 000 €', gain_resilience: 12, priorite: 'recommande' },
    ],
    faible: [
      { travaux: 'Inspection et maintenance périodique des cuves', cout_estime: '1 500 – 5 000 €', gain_resilience: 6, priorite: 'anticipation' },
    ],
  },
  bureaux: {
    eleve: [
      { travaux: 'Protection des serveurs et données (onduleurs, sauvegardes hors site)', cout_estime: '6 000 – 20 000 €', gain_resilience: 18, priorite: 'urgent' },
      { travaux: 'Étanchéité de la toiture et protection contre les infiltrations', cout_estime: '8 000 – 30 000 €', gain_resilience: 12, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Éclairage de secours et locaux de repli', cout_estime: '2 000 – 6 000 €', gain_resilience: 8, priorite: 'recommande' },
    ],
    faible: [
      { travaux: 'Mise à jour du plan de sécurité', cout_estime: '500 – 2 000 €', gain_resilience: 4, priorite: 'anticipation' },
    ],
  },
  expedition: {
    eleve: [
      { travaux: 'Surélévation des quais et protection des convoyeurs contre les intempéries', cout_estime: '18 000 – 50 000 €', gain_resilience: 20, priorite: 'urgent' },
      { travaux: 'Système de gestion des expéditions déporté (repli informatique)', cout_estime: '5 000 – 15 000 €', gain_resilience: 12, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Procédures de manutention renforcées et formation', cout_estime: '2 000 – 6 000 €', gain_resilience: 8, priorite: 'recommande' },
    ],
    faible: [
      { travaux: 'Organisation des flux d\'expédition', cout_estime: '1 000 – 3 000 €', gain_resilience: 4, priorite: 'anticipation' },
    ],
  },
};

const GLOBAL_ACTIONS: Recommendation[] = [
  { travaux: 'Diagnostic détaillé du site par un bureau d\'ingénierie (structure, process, sécurité incendie)', cout_estime: '5 000 – 15 000 €', gain_resilience: 20, priorite: 'recommande' },
  { travaux: 'Mise à niveau de la conformité ICPE / réglementation environnementale', cout_estime: '10 000 – 40 000 €', gain_resilience: 15, priorite: 'recommande' },
  { travaux: 'Souscription d\'une couverture d\'assurance adaptée aux risques identifiés', cout_estime: 'variable', gain_resilience: 10, priorite: 'anticipation' },
];

type Props = {
  analyse: AnalyseUsine | null;
};

export function UsineRecommendations({ analyse }: Props) {
  const recos = useMemo(() => {
    if (!analyse) return { byZone: new Map<string, { zone: ZonePlan; items: Recommendation[] }>(), globaux: GLOBAL_ACTIONS };
    const byZone = new Map<string, { zone: ZonePlan; items: Recommendation[] }>();
    const niveauKey = (zone: ZonePlan) => {
      const band = bandForScore(zone.risque);
      return band.key === 'tres_faible' || band.key === 'faible'
        ? 'faible'
        : band.key === 'modere'
          ? 'modere'
          : 'eleve';
    };
    for (const zone of analyse.zones) {
      const lvl = niveauKey(zone);
      const catalogue = CATALOGUE[zone.type]?.[lvl] || CATALOGUE[zone.type]?.['modere'] || [];
      byZone.set(zone.id, { zone, items: catalogue });
    }
    return { byZone, globaux: GLOBAL_ACTIONS };
  }, [analyse]);

  if (!analyse) {
    return (
      <div className="analyse-empty">
        <md-icon>fact_check</md-icon>
        <h2>Recommandations indisponibles</h2>
        <p>Lancez d'abord l'analyse de risque pour générer le plan d'adaptation de l'usine.</p>
      </div>
    );
  }

  const criticalCount = analyse.zones.filter((z) => (z.risque ?? 0) >= 60).length;
  const totalCost = sumCosts(recos.byZone, recos.globaux);

  return (
    <div className="usine-recos">
      <header className="usine-recos-header">
        <div className="usine-recos-title">
          <h2>Plan d'adaptation de l'usine</h2>
          <p className="usine-recos-meta">
            {analyse.nb_zones} zones analysées · {criticalCount} zone(s) à risque élevé ou critique
          </p>
        </div>
        <span className="usine-recos-budget">
          <md-icon>savings</md-icon>
          <span>
            Enveloppe estimée : <strong>{totalCost}</strong>
          </span>
        </span>
      </header>

      {criticalCount > 0 && (
        <div className="usine-recos-alert">
          <md-icon>warning</md-icon>
          <span>
            <strong>Priorité haute :</strong> {criticalCount} zone(s) présentent un risque
            {criticalCount > 1 ? ' élevé ou critique' : ' élevé ou critique'} — les mesures « urgentes »
            doivent être engagées dans les 12 prochains mois.
          </span>
        </div>
      )}

      {Array.from(recos.byZone.values()).map(({ zone, items }) => (
        <ZoneReco key={zone.id} zone={zone} items={items} analyse={analyse} />
      ))}

      <section className="usine-reco-section">
        <h3>
          <md-icon>apartment</md-icon> Actions globales du site
        </h3>
        <div className="usine-reco-list">
          {recos.globaux.map((r, i) => (
            <RecoItem key={i} reco={r} />
          ))}
        </div>
      </section>

      <p className="usine-analyse-note" role="note">
        <md-icon>info</md-icon>
        <span>
          Montants indicatifs en euros (hors études détaillées). Les gains de résilience sont des
          ordres de grandeur issus du risk engine — une étude d'ingénierie reste nécessaire pour
          tout investissement.
        </span>
      </p>
    </div>
  );
}

function ZoneReco({ zone, items, analyse }: { zone: ZonePlan; items: Recommendation[]; analyse: AnalyseUsine }) {
  const band = bandForScore(zone.risque);
  const eqs = (zone.equipements || [])
    .map((id) => analyse.equipements.find((e) => e.id === id))
    .filter(Boolean);

  return (
    <section className="usine-reco-section">
      <h3>
        <span className="usine-reco-zone-dot" style={{ background: band.color }} />
        {zone.nom}
        <span className="usine-reco-zone-sub">
          {TYPE_ZONE_LABELS[zone.type] || zone.type} · risque {zone.risque ?? '—'}/100 ({band.label})
        </span>
      </h3>
      <div className="usine-reco-list">
        {items.length === 0 ? (
          <p className="usine-reco-empty">Aucune recommandation prioritaire — zone bien maîtrisée.</p>
        ) : (
          items.map((r, i) => <RecoItem key={i} reco={r} />)
        )}
      </div>
      {eqs.length > 0 && (
        <div className="usine-reco-eqs">
          <span className="usine-reco-eqs-label">
            <md-icon>precision_manufacturing</md-icon> Équipements concernés :
          </span>
          {eqs.map((e: any) => (
            <span key={e.id} className="usine-reco-eq-chip">
              {e.nom} <small>({TYPE_EQUIP_LABELS[e.type] || e.type})</small>
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function RecoItem({ reco }: { reco: Recommendation }) {
  const cls = reco.priorite;
  const label =
    cls === 'urgent' ? 'Urgent' : cls === 'recommande' ? 'Recommandé' : 'Anticipation';
  return (
    <div className={`usine-reco-item p-${cls}`}>
      <span className="usine-reco-item-tag">{label}</span>
      <div className="usine-reco-item-main">
        <strong>{reco.travaux}</strong>
        <div className="usine-reco-item-meta">
          <span>
            <md-icon>payments</md-icon> {reco.cout_estime}
          </span>
          <span>
            <md-icon>trending_up</md-icon> +{reco.gain_resilience} pts de résilience
          </span>
        </div>
      </div>
    </div>
  );
}

/* ─────────── Helpers ─────────── */

function sumCosts(
  byZone: Map<string, { zone: ZonePlan; items: Recommendation[] }>,
  globaux: Recommendation[]
): string {
  const parse = (s: string): [number, number] => {
    const nums = s.match(/[\d\s]+/g);
    if (!nums) return [0, 0];
    const vals = nums.map((n) => Number(n.replace(/\s/g, '')) || 0);
    return vals.length === 1 ? [vals[0], vals[0]] : [vals[0], vals[1] || vals[0]];
  };
  let lo = 0;
  let hi = 0;
  for (const { items } of byZone.values()) {
    for (const r of items) {
      const [a, b] = parse(r.cout_estime);
      lo += a;
      hi += b;
    }
  }
  for (const r of globaux) {
    const [a, b] = parse(r.cout_estime);
    lo += a;
    hi += b;
  }
  if (lo === 0 && hi === 0) return '—';
  const fmt = (n: number) => n.toLocaleString('fr-FR');
  return lo === hi ? `${fmt(lo)} €` : `${fmt(lo)} – ${fmt(hi)} €`;
}
