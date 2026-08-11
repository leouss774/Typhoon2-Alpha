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
import {
  CATALOGUE,
  GLOBAL_ACTIONS,
  parseCostRange,
  type Recommendation,
} from '../usine/recommandations';

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
  let lo = 0;
  let hi = 0;
  for (const { items } of byZone.values()) {
    for (const r of items) {
      const [a, b] = parseCostRange(r.cout_estime);
      lo += a;
      hi += b;
    }
  }
  for (const r of globaux) {
    const [a, b] = parseCostRange(r.cout_estime);
    lo += a;
    hi += b;
  }
  if (lo === 0 && hi === 0) return '—';
  const fmt = (n: number) => n.toLocaleString('fr-FR');
  return lo === hi ? `${fmt(lo)} €` : `${fmt(lo)} – ${fmt(hi)} €`;
}
