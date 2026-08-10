// =============================================================================
//   TYPHOON — /zone : panneau « Comprendre risque »
//   Tableau de bord analytique agrégeant les scores de risque par zone du
//   bâtiment (fondations, murs, toiture, sous-sol…), calculés côté backend
//   à partir des données Géorisques (voir /diagnostic/recommandations).
// =============================================================================

import { useEffect, useMemo, useState } from 'react';
import {
  D03,
  bandForKey,
  type D03Band,
  type RisquesPrincipaux,
} from '../zone/config';
import { formatZoneLabel, type RecommendationZone } from '../jumeau/recommendations';

const NIVEAU_SCORE: Record<string, number> = {
  tres_faible: 10,
  faible: 30,
  modere: 50,
  eleve: 70,
  critique: 90,
};

function bandForScore(score: number): D03Band {
  return D03.find((b) => score <= b.max) || D03[D03.length - 1];
}

function zoneScore(zone: RecommendationZone): number | null {
  if (typeof zone.risque === 'number' && Number.isFinite(zone.risque)) {
    return Math.max(0, Math.min(100, zone.risque));
  }
  if (zone.niveau && NIVEAU_SCORE[zone.niveau] != null) return NIVEAU_SCORE[zone.niveau];
  return null;
}

/* Les 4 façades (murs_nord/sud/est/ouest) partagent le même modèle de risque
   côté backend (risk_model.py::_score_global) — on les fusionne en une seule
   entrée « Murs » plutôt que d'afficher 4 lignes quasi identiques. */
const MURS_GROUP_KEY = 'murs';
function groupKey(key: string): string {
  return key.startsWith('murs_') ? MURS_GROUP_KEY : key;
}

type ZoneEntry = { key: string; label: string; score: number; band: D03Band; aleaPrincipal?: string };

function polarPoint(cx: number, cy: number, r: number, angle: number): [number, number] {
  return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
}

function RadarChart({ entries }: { entries: ZoneEntry[] }) {
  const w = 300;
  const h = 240;
  const cx = w / 2;
  const cy = h / 2;
  const maxR = 58;
  const labelR = maxR + 34;
  const n = entries.length;

  const ringPolygon = (r: number) =>
    entries
      .map((_, i) => polarPoint(cx, cy, r, (2 * Math.PI * i) / n - Math.PI / 2).join(','))
      .join(' ');

  const dataPoints = entries.map((e, i) =>
    polarPoint(cx, cy, (e.score / 100) * maxR, (2 * Math.PI * i) / n - Math.PI / 2)
  );
  const dataPolygon = dataPoints.map((p) => p.join(',')).join(' ');

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="risk-radar-svg" role="img" aria-label="Radar des scores de risque par zone">
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <polygon key={f} points={ringPolygon(maxR * f)} className="risk-radar-ring" />
      ))}
      {entries.map((_, i) => {
        const [x, y] = polarPoint(cx, cy, maxR, (2 * Math.PI * i) / n - Math.PI / 2);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} className="risk-radar-axis" />;
      })}
      <polygon points={dataPolygon} className="risk-radar-area" />
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={2.5} className="risk-radar-dot" />
      ))}
      {entries.map((e, i) => {
        const [x, y] = polarPoint(cx, cy, labelR, (2 * Math.PI * i) / n - Math.PI / 2);
        const anchor = Math.abs(x - cx) < 4 ? 'middle' : x > cx ? 'start' : 'end';
        return (
          <text key={i} x={x} y={y} textAnchor={anchor} dominantBaseline="middle" className="risk-radar-label">
            {e.label}
          </text>
        );
      })}
    </svg>
  );
}

function ScoreDonut({ score, band }: { score: number; band: D03Band }) {
  const r = 62;
  const c = 2 * Math.PI * r;
  const dash = (score / 100) * c;
  return (
    <svg viewBox="0 0 160 160" className="risk-donut-svg" role="img" aria-label={`Score global de risque : ${score} sur 100`}>
      <circle cx="80" cy="80" r={r} className="risk-donut-track" />
      <circle
        cx="80"
        cy="80"
        r={r}
        className="risk-donut-value"
        style={{ stroke: band.color, strokeDasharray: `${dash} ${c - dash}` }}
        transform="rotate(-90 80 80)"
      />
      <text x="80" y="76" textAnchor="middle" className="risk-donut-score">{score}</text>
      <text x="80" y="96" textAnchor="middle" className="risk-donut-max">/ 100</text>
    </svg>
  );
}

export function ComprendreRisques({
  zones,
  loading,
  error,
  risquesPrincipaux,
}: {
  zones: Record<string, RecommendationZone>;
  loading?: boolean;
  error?: string | null;
  /* Top 3 des risques principaux (scores moteur + narration LLM croisant les
     données géo et bâtimentaires) — contrat app/agents/risques_principaux.py. */
  risquesPrincipaux?: RisquesPrincipaux | null;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [open]);

  const entries = useMemo<ZoneEntry[]>(() => {
    const groups = new Map<string, { scores: number[]; niveaux: string[]; aleaPrincipal?: string }>();
    Object.entries(zones || {}).forEach(([key, zone]) => {
      const score = zoneScore(zone);
      if (score == null) return;
      const gKey = groupKey(key);
      const group = groups.get(gKey) || { scores: [], niveaux: [] };
      group.scores.push(score);
      if (zone.niveau) group.niveaux.push(zone.niveau);
      if (!group.aleaPrincipal && zone.alea_principal) group.aleaPrincipal = zone.alea_principal;
      groups.set(gKey, group);
    });

    return [...groups.entries()]
      .map(([key, group]) => {
        const score = Math.round(group.scores.reduce((sum, s) => sum + s, 0) / group.scores.length);
        const worstNiveau = group.niveaux.reduce<string | undefined>(
          (worst, n) => (worst == null || (NIVEAU_SCORE[n] ?? 0) > (NIVEAU_SCORE[worst] ?? 0) ? n : worst),
          undefined,
        );
        const band = worstNiveau ? bandForKey(worstNiveau) || bandForScore(score) : bandForScore(score);
        const label = key === MURS_GROUP_KEY ? 'Murs' : formatZoneLabel(key);
        return { key, label, score, band, aleaPrincipal: group.aleaPrincipal } as ZoneEntry;
      })
      .sort((a, b) => b.score - a.score);
  }, [zones]);

  const globalScore = entries.length
    ? Math.round(entries.reduce((sum, e) => sum + e.score, 0) / entries.length)
    : null;
  const globalBand = globalScore != null ? bandForScore(globalScore) : null;

  return (
    <>
      <md-elevated-button
        className="bim-action"
        aria-label="Comprendre les risques du bien par zone"
        onClick={() => setOpen(true)}
      >
        <md-icon slot="icon">analytics</md-icon>
        Comprendre risque
      </md-elevated-button>

      {open && (
        <div
          className="risk-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setOpen(false);
          }}
        >
          <section className="risk-sheet" role="dialog" aria-modal="true" aria-labelledby="risk-sheet-title">
            <header className="risk-sheet-header">
              <div>
                <span className="risk-sheet-eyebrow">Tableau de bord analytique</span>
                <h2 id="risk-sheet-title">Comprendre les risques de votre bien</h2>
                <p>
                  Le score global agrège l'exposition de chaque zone du bien aux différents
                  aléas. Utilisez le radar pour visualiser en un coup d'œil l'équilibre — ou
                  le déséquilibre — des risques entre zones.
                </p>
              </div>
              <md-icon-button aria-label="Fermer" onClick={() => setOpen(false)}>
                <md-icon>close</md-icon>
              </md-icon-button>
            </header>

            {loading && entries.length === 0 && (
              <div className="risk-state">
                <span className="risk-status-dot" />
                Calcul des scores de risque par zone…
              </div>
            )}
            {!loading && error && entries.length === 0 && (
              <div className="risk-state risk-state-error">
                <md-icon>error</md-icon>
                {error}
              </div>
            )}
            {!loading && !error && entries.length === 0 && (
              <div className="risk-state">
                <md-icon>info</md-icon>
                Aucun score de risque disponible pour ce bien.
              </div>
            )}

            {entries.length > 0 && (
              <div className="risk-sheet-content">
                <div className="risk-cards">
                  <div className="risk-card risk-score-card">
                    <ScoreDonut score={globalScore!} band={globalBand!} />
                    <span className={`d03-pill ${globalBand!.cls}`}>{globalBand!.label}</span>
                    <p className="risk-score-caption">Score de résilience climatique global du bien</p>
                  </div>

                  <div className="risk-card risk-radar-card">
                    <h3>Équilibre des risques par aléa</h3>
                    <p className="risk-card-hint">
                      Diagramme en toile d'araignée — score de risque (0 = aucun risque, 100 =
                      risque critique) pour chaque aléa climatique et géologique identifié
                      (inondation, RGA, sismique…), agrégé sur l'ensemble des zones du bien.
                    </p>
                    {entries.length >= 3 ? (
                      <RadarChart entries={entries} />
                    ) : (
                      <p className="risk-card-hint">
                        Pas assez d'aléas distincts pour un radar — voir le détail ci-dessous.
                      </p>
                    )}
                  
                </div>
                </div>

                {/* ── Risques principaux + facteurs aggravants (bas du dashboard) ── */}
                {loading && !risquesPrincipaux && (
                  <div className="risk-principaux-loading" role="status" aria-live="polite">
                    <md-linear-progress indeterminate />
                    <span>
                      Croisement des données géographiques et bâtimentaires en
                      cours…
                    </span>
                  </div>
                )}

                {risquesPrincipaux && risquesPrincipaux.risques.length > 0 && (
                  <div className="risk-card risk-principaux-card">
                    <div className="risk-principaux-head">
                      <div>
                        <h3>Les risques principaux de votre bien</h3>
                        <p className="risk-card-hint">
                          Classement calculé en croisant l'aléa géographique avec la
                          vulnérabilité du bâtiment, puis interprété à la lumière de
                          toutes les données disponibles (Géorisques, BDNB, climat…).
                        </p>
                      </div>
                      {risquesPrincipaux.source?.includes('llm') && (
                        <span
                          className="risk-ai-badge"
                          title="Explications croisées générées par IA à partir des données Géorisques et BDNB"
                        >
                          <md-icon>auto_awesome</md-icon>
                          Analyse croisée IA
                        </span>
                      )}
                    </div>
                    <ol className="risk-principaux-list">
                      {risquesPrincipaux.risques.map((r) => {
                        const band = bandForKey(r.niveau) || bandForScore(r.score);
                        return (
                          <li key={r.code} className="risk-principal">
                            <div className="risk-principal-body">
                              <div className="risk-principal-head">
                                <span className="risk-principal-name">{r.libelle}</span>
                                <span
                                  className="risk-principal-score"
                                  style={{ color: band.color }}
                                >
                                  {r.score}
                                </span>
                                <span className={`d03-pill ${band.cls}`}>
                                  Risque {band.label.toLowerCase()}
                                </span>
                              </div>
                              {r.explication && (
                                <p className="risk-principal-explication">
                                  {r.explication}
                                </p>
                              )}
                              {r.facteurs_aggravants && r.facteurs_aggravants.length > 0 && (
                                <ul className="risk-aggravants">
                                  {r.facteurs_aggravants.map((f, j) => (
                                    <li key={j}>
                                      <md-icon>trending_up</md-icon>
                                      <span>{f}</span>
                                    </li>
                                  ))}
                                </ul>
                              )}
                              {r.zone_la_plus_exposee && (
                                <span className="risk-principal-zone">
                                  <md-icon>pin_drop</md-icon>
                                  Zone la plus exposée :{' '}
                                  {formatZoneLabel(r.zone_la_plus_exposee)}
                                </span>
                              )}
                            </div>
                          </li>
                        );
                      })}
                    </ol>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}