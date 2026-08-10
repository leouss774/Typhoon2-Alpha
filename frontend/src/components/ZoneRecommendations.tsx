import { useMemo, useState } from 'react';
import { ALEA_ICON_FALLBACK, ALEA_ICONS, aleaScore, bandForKey, type RisqueReport } from '../zone/config';
import { aggregateRecommendations, formatCost, formatZoneLabel, type RecommendationZone } from '../jumeau/recommendations';

type Props = {
  report: RisqueReport | null;
  zones: Record<string, RecommendationZone>;
  loading: boolean;
  error: string | null;
};

function recommendationLevel(score: number | null): { label: string; className: string } {
  if (score === null) return { label: 'Score indisponible', className: 'unknown' };
  if (score >= 80) return { label: 'Recommandation critique', className: 'critical' };
  if (score >= 60) return { label: 'Recommandation prioritaire', className: 'priority' };
  if (score >= 40) return { label: 'Recommandation modérée', className: 'moderate' };
  return { label: 'Prévention facultative', className: 'optional' };
}

export function ZoneRecommendations({ report, zones, loading, error }: Props) {
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const recommendations = useMemo(() => aggregateRecommendations(zones), [zones]);
  const grouped = useMemo(() => {
    const result = new Map<string, typeof recommendations>();
    Object.keys(zones).forEach((zone) => result.set(zone, []));
    recommendations.forEach((item) => result.set(item.zone, [...(result.get(item.zone) || []), item]));
    return result;
  }, [recommendations, zones]);
  const activeZone = selectedZone && grouped.has(selectedZone)
    ? selectedZone
    : grouped.keys().next().value as string | undefined;

  if (!report) return <div className="zone-reco-empty"><md-icon>recommend</md-icon><h2>Aucun diagnostic</h2><p>Diagnostiquez une adresse pour afficher ses recommandations.</p></div>;
  const risks = (report.aleas || []).filter((alea) => alea.present === true).sort((a, b) => aleaScore(b) - aleaScore(a));

  return <div className="zone-recommendations-view">
    <header className="zone-reco-header"><div><span className="zone-reco-eyebrow">Plan d’adaptation du bien</span><h2>Recommandations détaillées</h2><p>{report.adresse_normalisee}</p></div><div className="zone-reco-count"><strong>{recommendations.length}</strong><span>mesures documentées</span></div></header>

    <section className="zone-reco-risks">
      <div className="zone-reco-section-title"><div><span>01</span><h3>Risques retenus pour cette adresse</h3></div><small>Classement par criticité calculée</small></div>
      <div className="zone-reco-risk-grid">{risks.map((risk) => { const score = aleaScore(risk); const band = bandForKey(risk.niveau); return <article className="zone-reco-risk" key={risk.code}><md-icon>{ALEA_ICONS[risk.code] || ALEA_ICON_FALLBACK}</md-icon><div><strong>{risk.libelle}</strong><span>{risk.zonage || band?.label || 'Risque présent'}</span></div><div className={`zone-reco-score ${band?.cls || ''}`}><strong>{score}</strong><small>/100</small></div></article>; })}</div>
    </section>

    <section className="zone-reco-actions">
      <div className="zone-reco-section-title"><div><span>02</span><h3>Mesures adaptées aux zones du bâtiment</h3></div></div>

      {loading && <div className="zone-reco-loading"><md-circular-progress indeterminate></md-circular-progress><div><strong>Analyse détaillée du bien en cours…</strong><p>Le moteur consulte les caractéristiques BDNB, les scores par zone et le référentiel documentaire.</p></div></div>}
      {!loading && grouped.size > 0 && <>
        <nav className="zone-reco-chips" aria-label="Zones du bâtiment">
          {[...grouped.entries()].map(([zone, items]) => <button type="button" className={`zone-reco-chip${activeZone === zone ? ' active' : ''}${items.length === 0 ? ' empty' : ''}`} aria-pressed={activeZone === zone} onClick={() => setSelectedZone(zone)} key={zone}><md-icon>domain</md-icon><span>{formatZoneLabel(zone)}</span><small>{items.length}</small></button>)}
        </nav>
        {activeZone && <section className="zone-reco-group" key={activeZone}>{(grouped.get(activeZone) || []).length > 0 ? <div className="zone-reco-action-list">{(grouped.get(activeZone) || []).map((item) => {
        const rawCost = typeof item.cout_estime === 'object' ? item.cout_estime : null;
        const sources = (item.sources || []).map((source) => source.titre || source.organisme || source.source_id || source.fiche_id).filter(Boolean);
        const level = recommendationLevel(item.zoneRisk);
        return <article className="zone-reco-action-card rich" key={item.id}><div className="zone-reco-card-head"><div><span className={`zone-reco-priority ${level.className}`}>{level.label}{item.zoneRisk !== null ? ` · score ${item.zoneRisk}/100` : ''}</span><h4>{item.mesure || item.travaux || 'Mesure recommandée'}</h4></div>{formatCost(item) && <strong className="zone-reco-card-cost">{formatCost(item)}</strong>}</div>{item.explication && <p className="zone-reco-card-explanation">{item.explication}</p>}<div className="zone-reco-card-tags">{item.risque_concerne && <span><md-icon>warning</md-icon>{formatZoneLabel(item.risque_concerne)}</span>}{item.type && <span>{formatZoneLabel(item.type)}</span>}{item.gain !== null && <span>Gain +{item.gain}%</span>}</div>{rawCost?.hypotheses && <p className="zone-reco-meta"><strong>Hypothèses :</strong> {rawCost.hypotheses}</p>}{item.aide && (item.aide.dispositif || item.aide.conditions || item.aide.statut) && <div className="zone-reco-aid"><md-icon>savings</md-icon><span><strong>{item.aide.dispositif || 'Aide potentielle'}</strong>{item.aide.conditions && <> — {item.aide.conditions}</>}{item.aide.statut && <small>Statut : {formatZoneLabel(item.aide.statut)}</small>}</span></div>}{sources.length > 0 && <div className="zone-reco-sources"><md-icon>library_books</md-icon><span>Sources : {sources.join(' · ')}</span></div>}</article>;
      })}</div> : <div className="zone-reco-zone-empty"><md-icon>verified</md-icon><div><strong>0 recommandation</strong><p>{(zones[activeZone]?.risque ?? 0) < 20 ? `Risque absent ou score ${zones[activeZone]?.risque ?? 0}/100 inférieur à 20 → aucune recommandation.` : `Aucune recommandation documentée disponible pour le risque calculé dans cette zone (score ${zones[activeZone]?.risque ?? 'indisponible'}/100).`}</p></div></div>}</section>}
      </>}

      {!loading && recommendations.length === 0 && <div className="zone-reco-notice"><md-icon>{error ? 'cloud_off' : 'verified'}</md-icon><div><strong>Risque absent ou score &lt; 20 → aucune recommandation</strong>{error && <p>Le moteur détaillé est actuellement indisponible : {error}</p>}</div></div>}
    </section>

  </div>;
}
