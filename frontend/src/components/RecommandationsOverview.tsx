// =============================================================================
//   TYPHOON — « Vue d'ensemble des recommandations »
//   Agrége toutes les recommandations du diagnostic (toutes zones confondues)
//   dans une vue unique, en réutilisant UNIQUEMENT les données déjà fusionnées
//   en mémoire par le moteur 3D (scene-engine.js, événement
//   'typhoon:recommandationsUpdated' / snapshot window.__typhoonDiagnostic).
//   AUCUNE requête réseau : c'est une couche d'agrégation en lecture seule.
//
//   Affichage par zone puis par type de travaux, avec pour chaque
//   recommandation : mesure, explication, risque concerné, priorité,
//   coût min/max + unité/devise/hypothèses, aide (dispositif/conditions/
//   statut) et sources. Tris : criticité, coût croissant/décroissant,
//   gain de résilience — les items sans valeur vont en fin de liste,
//   aucune valeur n'est jamais inventée.
//
//   Style : Material 3 sombre D03, mêmes tokens que le reste du /jumeau
//   (jumeau.css). Aucune réutilisation du HTML/CSS de develop.
// =============================================================================

import { useEffect, useMemo, useState } from 'react';

/* ───────────────────────── Types (contrat reco) ───────────────────────── */

interface CoutEstime {
  montant_min?: number | null;
  montant_max?: number | null;
  devise?: string | null;
  unite?: string | null;
  date_estimation?: string | null;
  zone_geo?: string | null;
  hypotheses?: string | null;
}

interface AideInfo {
  dispositif?: string | null;
  conditions?: string | null;
  statut?: string | null;
}

interface SourceRef {
  fiche_id?: string | null;
  source_id?: string | null;
  extrait_exact?: string | null;
}

interface RecoItem {
  mesure?: string | null;
  travaux?: string | null;
  explication?: string | null;
  risque_concerne?: string | null;
  type?: string | null;
  cout_estime?: CoutEstime | string | null;
  gain_resilience?: number | null;
  aide?: AideInfo | null;
  sources?: SourceRef[] | null;
}

interface ZoneData {
  risque?: number | null;
  niveau?: string | null;
  alea_principal?: string | null;
  justification?: string | null;
  recommandations?: RecoItem[] | null;
}

interface DiagnosticSnapshot {
  adresse?: string;
  score_global?: number | null;
  zones?: Record<string, ZoneData>;
  projection_2050?: Record<string, unknown> | null;
}

/* ───────────────────────── Helpers données ───────────────────────── */

type SortKey = 'criticite' | 'cout_asc' | 'cout_desc' | 'gain';

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'criticite', label: 'Criticité' },
  { key: 'cout_asc', label: 'Coût croissant' },
  { key: 'cout_desc', label: 'Coût décroissant' },
  { key: 'gain', label: 'Gain de résilience' },
];

/** Priorité dérivée du niveau de risque de la zone (donnée réelle,
 *  même règle que le panneau de zone du moteur). */
function prioriteFor(niveau?: string | null): { key: string; label: string } {
  if (niveau === 'critique' || niveau === 'eleve') return { key: 'haute', label: 'Haute' };
  if (niveau === 'faible') return { key: 'faible', label: 'Faible' };
  return { key: 'moyenne', label: 'Moyenne' };
}

/** Parse le coût dans les deux schémas (objet BDNB/agent ou chaîne démo).
 *  Retourne null quand aucune valeur exploitable — jamais de valeur inventée. */
function parseCost(
  c?: CoutEstime | string | null,
): { min: number | null; max: number | null; label: string | null } | null {
  if (c == null) return null;
  if (typeof c === 'object') {
    const min = c.montant_min ?? null;
    const max = c.montant_max ?? null;
    if (min == null && max == null) return null;
    const dev = c.devise || '€';
    const label =
      min != null && max != null && min !== max
        ? `${min} – ${max} ${dev}`
        : `environ ${min ?? max} ${dev}`;
    return { min, max, label };
  }
  if (typeof c === 'string') {
    const parts = c.replace(/€/g, '').trim().split('-').map((n) => parseInt(n, 10));
    if (parts.length === 2 && !Number.isNaN(parts[0]) && !Number.isNaN(parts[1])) {
      return { min: parts[0], max: parts[1], label: c };
    }
    if (parts.length === 1 && !Number.isNaN(parts[0])) {
      return { min: parts[0], max: parts[0], label: c };
    }
    return { min: null, max: null, label: c || null };
  }
  return null;
}

/** Gain réel seulement : les valeurs absentes restent null (pas de repli 10). */
function gainOf(r: RecoItem): number | null {
  return typeof r.gain_resilience === 'number' && Number.isFinite(r.gain_resilience)
    ? r.gain_resilience
    : null;
}

/** Flatte les zones vers une liste d'items avec contexte de zone. */
function aggregate(snapshot: DiagnosticSnapshot | null): RecoItemView[] {
  if (!snapshot?.zones) return [];
  const out: RecoItemView[] = [];
  Object.entries(snapshot.zones).forEach(([zoneName, zone]) => {
    (zone?.recommandations || []).forEach((reco) => {
      out.push({
        zone: zoneName,
        risqueZone: zone?.risque ?? null,
        niveauZone: zone?.niveau ?? null,
        aleaZone: zone?.alea_principal ?? null,
        reco,
      });
    });
  });
  return out;
}

interface RecoItemView {
  zone: string;
  risqueZone: number | null;
  niveauZone: string | null;
  aleaZone: string | null;
  reco: RecoItem;
}

/** Valeur de tri réelle pour un item — null quand elle est absente
 *  (jamais de valeur inventée). Coût décroissant : on classe par montant
 *  max si disponible, sinon min. */
function valueFor(it: RecoItemView, key: SortKey): number | null {
  if (key === 'criticite') return it.risqueZone;
  const c = parseCost(it.reco.cout_estime);
  if (key === 'cout_asc') return c?.min ?? null;
  if (key === 'cout_desc') return c?.max ?? c?.min ?? null;
  return gainOf(it.reco);
}

/** Tri : les items SANS la valeur de tri vont TOUJOURS en fin de liste
 *  (comparateur explicite, pas de sentinelle inversée). */
function sortItems(items: RecoItemView[], key: SortKey): RecoItemView[] {
  const desc = key !== 'cout_asc';
  return [...items].sort((a, b) => {
    const va = valueFor(a, key);
    const vb = valueFor(b, key);
    const na = va == null;
    const nb = vb == null;
    if (na && nb) return 0;
    if (na) return 1; // manquant → fin
    if (nb) return -1;
    return desc ? vb - va : va - vb;
  });
}

/* ───────────────────────── Composant ───────────────────────── */

export function RecommandationsOverview({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [snapshot, setSnapshot] = useState<DiagnosticSnapshot | null>(() => {
    const s = (window as unknown as { __typhoonDiagnostic?: DiagnosticSnapshot }).__typhoonDiagnostic;
    return s || null;
  });
  const [sort, setSort] = useState<SortKey>('criticite');

  /* Abonnement aux mises à jour du moteur (chargement + fusion recos).
     Le snapshot de window couvre le cas où l'événement est déjà passé. */
  useEffect(() => {
    if (!open) return;
    const onUpdate = (e: Event) => {
      const detail = (e as CustomEvent<DiagnosticSnapshot>).detail;
      if (detail) setSnapshot(detail);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('typhoon:recommandationsUpdated', onUpdate);
    window.addEventListener('keydown', onKey);
    // Rattrapage si le moteur a émis avant le montage
    const s = (window as unknown as { __typhoonDiagnostic?: DiagnosticSnapshot }).__typhoonDiagnostic;
    if (s) setSnapshot(s);
    return () => {
      window.removeEventListener('typhoon:recommandationsUpdated', onUpdate);
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  const items = useMemo(() => sortItems(aggregate(snapshot), sort), [snapshot, sort]);

  /* Regroupement par zone, puis par type de travaux dans la zone.
     Les zones complètes (toutes leurs recommandations ont la valeur de
     tri) passent avant les zones qui en manquent au moins une ; la zone
     incomplète garde son item sans valeur en fin de zone — jamais de
     valeur inventée. */
  const byZone = useMemo(() => {
    const zones = new Map<string, RecoItemView[]>();
    items.forEach((it) => {
      if (!zones.has(it.zone)) zones.set(it.zone, []);
      zones.get(it.zone)!.push(it);
    });
    const zoneRank = (zs: RecoItemView[]): { missing: boolean; best: number | null } => {
      const vals = zs
        .map((it) => valueFor(it, sort))
        .filter((v): v is number => v != null);
      return {
        missing: vals.length !== zs.length,
        best: vals.length ? (sort === 'cout_asc' ? Math.min(...vals) : Math.max(...vals)) : null,
      };
    };
    const desc = sort !== 'cout_asc';
    return Array.from(zones.entries()).sort((a, b) => {
      const ra = zoneRank(a[1]);
      const rb = zoneRank(b[1]);
      if (ra.missing !== rb.missing) return ra.missing ? 1 : -1;
      if (ra.best == null && rb.best == null) return 0;
      if (ra.best == null) return 1;
      if (rb.best == null) return -1;
      return desc ? rb.best - ra.best : ra.best - rb.best;
    });
  }, [items, sort]);

  if (!open) return null;

  return (
    <div className="reco-overview" role="dialog" aria-modal="true" aria-label="Vue d'ensemble des recommandations">
      <div className="reco-overview-backdrop" onClick={onClose} aria-hidden="true" />

      <aside className="reco-overview-panel">
        <header className="reco-overview-header">
          <div className="reco-overview-title">
            <md-icon aria-hidden="true">format_list_bulleted</md-icon>
            <div>
              <h2>Vue d'ensemble des recommandations</h2>
              <p className="reco-overview-meta">
                {snapshot?.adresse || 'Diagnostic'} · {items.length} recommandation(s) ·{' '}
                {byZone.length} zone(s)
              </p>
            </div>
          </div>
          <div className="reco-overview-actions">
            <label className="reco-overview-sort">
              <md-icon aria-hidden="true">swap_vert</md-icon>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
                aria-label="Trier les recommandations"
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <md-icon-button aria-label="Fermer" onClick={onClose}>
              <md-icon>close</md-icon>
            </md-icon-button>
          </div>
        </header>

        <div className="reco-overview-body">
          {items.length === 0 ? (
            <div className="reco-overview-empty">
              <md-icon>inbox</md-icon>
              <p>Aucune recommandation pour l'instant.</p>
              <span>Les recommandations apparaîtront une fois le diagnostic généré.</span>
            </div>
          ) : (
            byZone.map(([zoneName, zoneItems]) => (
              <section className="reco-zone" key={zoneName}>
                <header className="reco-zone-head">
                  <span className="reco-zone-name">
                    {zoneName.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                  </span>
                  <span className="reco-zone-count">{zoneItems.length}</span>
                  {zoneItems[0]?.aleaZone && (
                    <span className="reco-zone-alea">{zoneItems[0].aleaZone}</span>
                  )}
                </header>

                {/* Regroupement par type dans la zone */}
                {groupByType(zoneItems).map(([typeLabel, groupItems]) => (
                  <div className="reco-type-group" key={typeLabel}>
                    {groupItems.length > 0 && (
                      <div className="reco-type-label">
                        {typeLabel} ({groupItems.length})
                      </div>
                    )}
                    {groupItems.map((it, i) => (
                      <RecoCard key={`${zoneName}-${typeLabel}-${i}`} view={it} />
                    ))}
                  </div>
                ))}
              </section>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}

function groupByType(items: RecoItemView[]): [string, RecoItemView[]][] {
  const groups = new Map<string, RecoItemView[]>();
  items.forEach((it) => {
    const raw = it.reco.type;
    const key = raw ? raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : 'Autres travaux';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(it);
  });
  return Array.from(groups.entries());
}

/* ───────────────────────── Carte recommandation ───────────────────────── */

function RecoCard({ view }: { view: RecoItemView }) {
  const r = view.reco;
  const mesure = r.mesure || r.travaux || 'Travaux recommandés';
  const cout = parseCost(r.cout_estime);
  const gain = gainOf(r);
  const priorite = prioriteFor(view.niveauZone);
  const risque = r.risque_concerne || view.aleaZone || null;

  return (
    <article className="reco-card">
      <header className="reco-card-header">
        <span className="reco-chevron" aria-hidden="true" />
        <div className="reco-title-wrap">
          <span className="reco-title">{mesure}</span>
          {cout?.label && <span className="reco-sub">{cout.label}</span>}
        </div>
        <span className={`reco-priority-badge ${priorite.key}`}>{priorite.label}</span>
      </header>

      <div className="reco-card-body">
        {risque && <div className="reco-risque-tag">{risque}</div>}
        {r.explication && <div className="reco-explication">{r.explication}</div>}
        {r.type && (
          <div className="reco-meta">
            <strong>Type :</strong> {r.type.replace(/_/g, ' ')}
          </div>
        )}
        {cout?.label && (
          <div className="reco-meta">
            <strong>Coût estimé :</strong> {cout.label}
            {coutCtx(r.cout_estime)}
          </div>
        )}
        {gain != null && (
          <div className="reco-meta">
            <strong>Gain de résilience :</strong> +{gain}
          </div>
        )}
        {r.aide && (r.aide.dispositif || r.aide.conditions) && (
          <div className="reco-aide">
            <b>{r.aide.dispositif || 'Aide potentielle'}</b>
            {r.aide.conditions && <div className="reco-aide-cond">{r.aide.conditions}</div>}
            {r.aide.statut && (
              <div className="reco-aide-statut">Statut : {r.aide.statut.replace(/_/g, ' ')}</div>
            )}
          </div>
        )}
        {Array.isArray(r.sources) && r.sources.length > 0 && (
          <div className="reco-sources">
            Sources :{' '}
            {r.sources
              .map((s) => s.source_id || s.fiche_id)
              .filter(Boolean)
              .join(', ')}
          </div>
        )}
      </div>
    </article>
  );
}

/** Contexte du coût (unité, zone géo, date, hypothèses) — rien d'inventé. */
function coutCtx(c?: CoutEstime | string | null): string {
  if (typeof c !== 'object' || !c) return '';
  const parts: string[] = [];
  if (c.unite) parts.push(c.unite);
  if (c.zone_geo) parts.push(c.zone_geo);
  if (c.date_estimation) parts.push(`estimation ${c.date_estimation}`);
  const extra = parts.join(' · ');
  const hypo = c.hypotheses ? ` — ${c.hypotheses}` : '';
  return extra || hypo ? ` (${extra}${hypo})` : '';
}
