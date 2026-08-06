import { useEffect, useMemo, useState } from 'react';
import {
  aggregateRecommendations,
  formatCost,
  formatZoneLabel,
  sortRecommendations,
  type AggregatedRecommendation,
  type RecommendationsSnapshot,
  type RecommendationSort,
} from '../jumeau/recommendations';

const EMPTY_SNAPSHOT: RecommendationsSnapshot = { zones: {}, ready: false };

function displayType(value?: string): string {
  return value ? formatZoneLabel(value) : 'Autres travaux';
}

function sourceLabel(source: NonNullable<AggregatedRecommendation['sources']>[number]): string | null {
  const reference = source.source_id || source.fiche_id;
  const title = source.titre || source.organisme;
  if (reference && title) return `${reference} — ${title}`;
  return title || reference || null;
}

function RecommendationCard({ item }: { item: AggregatedRecommendation }) {
  const cost = formatCost(item);
  const rawCost = typeof item.cout_estime === 'object' ? item.cout_estime : null;
  const sources = (item.sources || []).map(sourceLabel).filter(Boolean) as string[];
  const measure = item.mesure || item.travaux || 'Travaux recommandés';

  return (
    <article className="reco-overview-card">
      <div className="reco-overview-card-head">
        <div>
          <h4>{measure}</h4>
          <div className="reco-overview-tags">
            <span className={`reco-overview-priority ${item.zoneLevel}`}>{formatZoneLabel(item.zoneLevel)}</span>
            {item.risque_concerne && <span>{item.risque_concerne}</span>}
          </div>
        </div>
        {cost && <strong className="reco-overview-cost">{cost}</strong>}
      </div>

      {item.explication && <p className="reco-overview-explanation">{item.explication}</p>}

      <dl className="reco-overview-details">
        {item.gain !== null && <><dt>Gain de résilience</dt><dd>+{item.gain}%</dd></>}
        {rawCost?.zone_geo && <><dt>Zone d’estimation</dt><dd>{rawCost.zone_geo}</dd></>}
        {rawCost?.date_estimation && <><dt>Date d’estimation</dt><dd>{rawCost.date_estimation}</dd></>}
        {rawCost?.hypotheses && <><dt>Hypothèses</dt><dd>{rawCost.hypotheses}</dd></>}
      </dl>

      {item.aide && (item.aide.dispositif || item.aide.conditions || item.aide.statut) && (
        <div className="reco-overview-aid">
          <md-icon aria-hidden="true">savings</md-icon>
          <div>
            <strong>{item.aide.dispositif || 'Aide potentielle'}</strong>
            {item.aide.conditions && <p>{item.aide.conditions}</p>}
            {item.aide.statut && <small>Statut : {formatZoneLabel(item.aide.statut)}</small>}
          </div>
        </div>
      )}

      {sources.length > 0 && (
        <div className="reco-overview-sources">
          <md-icon aria-hidden="true">library_books</md-icon>
          <span>Sources : {sources.join(' · ')}</span>
        </div>
      )}
    </article>
  );
}

export function RecommendationsOverview() {
  const [open, setOpen] = useState(false);
  const [sort, setSort] = useState<RecommendationSort>('criticite');
  const [snapshot, setSnapshot] = useState<RecommendationsSnapshot>(EMPTY_SNAPSHOT);

  useEffect(() => {
    const update = (event: Event) => {
      const detail = (event as CustomEvent<RecommendationsSnapshot>).detail;
      if (detail?.zones) setSnapshot(detail);
    };
    window.addEventListener('typhoon:recommendationsUpdated', update);
    return () => window.removeEventListener('typhoon:recommendationsUpdated', update);
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [open]);

  const recommendations = useMemo(
    () => sortRecommendations(aggregateRecommendations(snapshot.zones), sort),
    [snapshot.zones, sort],
  );

  const grouped = useMemo(() => {
    const zones = new Map<string, Map<string, AggregatedRecommendation[]>>();
    recommendations.forEach((item) => {
      if (!zones.has(item.zone)) zones.set(item.zone, new Map());
      const types = zones.get(item.zone)!;
      const type = displayType(item.type);
      if (!types.has(type)) types.set(type, []);
      types.get(type)!.push(item);
    });
    return zones;
  }, [recommendations]);

  return (
    <>
      <md-elevated-button className="reco-overview-trigger" onClick={() => setOpen(true)}>
        <md-icon slot="icon" aria-hidden="true">checklist</md-icon>
        Vue d’ensemble
        {recommendations.length > 0 && <span className="reco-overview-count">{recommendations.length}</span>}
      </md-elevated-button>

      {open && (
        <div className="reco-overview-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setOpen(false);
        }}>
          <section className="reco-overview-sheet" role="dialog" aria-modal="true" aria-labelledby="reco-overview-title">
            <header className="reco-overview-header">
              <div>
                <span className="reco-overview-eyebrow">Plan d’adaptation</span>
                <h2 id="reco-overview-title">Vue d’ensemble des recommandations</h2>
                <p>Actions consolidées pour toutes les zones du bâtiment.</p>
              </div>
              <md-icon-button aria-label="Fermer" onClick={() => setOpen(false)}>
                <md-icon>close</md-icon>
              </md-icon-button>
            </header>

            <div className="reco-overview-toolbar">
              <div className="reco-overview-summary">
                <strong>{recommendations.length}</strong>
                <span>recommandation{recommendations.length > 1 ? 's' : ''}</span>
                <i></i>
                <strong>{grouped.size}</strong>
                <span>zone{grouped.size > 1 ? 's' : ''}</span>
              </div>
              <label>
                Trier par
                <select value={sort} onChange={(event) => setSort(event.target.value as RecommendationSort)}>
                  <option value="criticite">Criticité</option>
                  <option value="cout_asc">Coût croissant</option>
                  <option value="cout_desc">Coût décroissant</option>
                  <option value="gain">Gain de résilience</option>
                </select>
              </label>
            </div>

            <div className="reco-overview-content">
              {!snapshot.ready && recommendations.length === 0 && (
                <div className="reco-overview-state">
                  <span className="reco-status-dot"></span>
                  Les recommandations sont en cours de génération…
                </div>
              )}
              {snapshot.ready && recommendations.length === 0 && (
                <div className="reco-overview-state">
                  <md-icon aria-hidden="true">verified</md-icon>
                  Aucune recommandation nécessaire pour ce bien.
                </div>
              )}
              {[...grouped.entries()].map(([zone, types]) => (
                <section className="reco-overview-zone" key={zone}>
                  <div className="reco-overview-zone-head">
                    <md-icon aria-hidden="true">domain</md-icon>
                    <h3>{formatZoneLabel(zone)}</h3>
                    <span>{[...types.values()].reduce((sum, items) => sum + items.length, 0)}</span>
                  </div>
                  {[...types.entries()].map(([type, items]) => (
                    <div className="reco-overview-type" key={type}>
                      <h4>{type}</h4>
                      <div className="reco-overview-grid">
                        {items.map((item) => <RecommendationCard item={item} key={item.id} />)}
                      </div>
                    </div>
                  ))}
                </section>
              ))}
            </div>
          </section>
        </div>
      )}
    </>
  );
}

