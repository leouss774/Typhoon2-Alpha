// =============================================================================
//   TYPHOON — /zone : diagnostic géo-risque par adresse (Stepper Material 3)
//   Étapes :
//     1. Adresse      — hero centré façon Gemini (champ de recherche au centre)
//     2. Cartographie — carte OpenLayers + panneau aléas (data viz Géorisques)
//     3. Analyse      — réservé (vide pour l'instant)
//     4. Rapport IA   — rapport narratif Mistral + export PDF
//
//   Stepper linéaire : les étapes 2-4 sont bloquées tant qu'aucune adresse
//   n'a été diagnostiquée — l'étape Adresse passe en état d'erreur (icône
//   erreur + message) si l'on tente de les atteindre sans rapport.
// =============================================================================

import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { ZoneMap } from '../components/ZoneMap';
import {
  API,
  D03,
  ALEA_ICONS,
  ALEA_ICON_FALLBACK,
  WMS_LAYER_MAP,
  bandForKey,
  escHtml,
  aleaScore,
  type AleaDetail,
  type RisqueReport,
  type RapportNarratif,
  type GeocodeSuggestion,
} from '../zone/config';
import '../styles/zone.css';

const LEGEND_RANGES = ['<20', '20–39', '40–59', '60–79', '≥80'];

const STEPS = [
  { id: 'adresse', label: 'Adresse' },
  { id: 'carto', label: 'Cartographie' },
  { id: 'analyse', label: 'Analyse' },
  { id: 'rapport', label: 'Rapport IA' },
] as const;

interface Status {
  text: string;
  kind: '' | 'loading' | 'error' | 'ok';
}

export function Zone() {
  const [step, setStep] = useState(0);
  const [stepError, setStepError] = useState(false);
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [status, setStatus] = useState<Status>({ text: '', kind: '' });
  const [progress, setProgress] = useState(0);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<RisqueReport | null>(null);
  const [rapport, setRapport] = useState<RapportNarratif | null>(null);
  const [rapportLoading, setRapportLoading] = useState(false);
  const [rapportError, setRapportError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [visibleLayerKeys, setVisibleLayerKeys] = useState<ReadonlySet<string>>(new Set());

  /* Champ de la topbar (étapes 2-4) et champ du hero (étape 1) : deux
     instances distinctes de md-outlined-text-field, chacune avec son ref. */
  const inputRef = useRef<HTMLElement & { value: string }>(null);
  const heroInputRef = useRef<HTMLInputElement>(null);
  const lastQuery = useRef('');
  const banTimeout = useRef<number | null>(null);
  const userClosedSidebar = useRef(false);

  /* ── BAN autocomplétion ── */
  function fetchSuggestions(q: string) {
    fetch(`${API}/api/geocode/search?q=${encodeURIComponent(q)}&limit=5`)
      .then((resp) => (resp.ok ? resp.json() : Promise.reject(new Error(`HTTP ${resp.status}`))))
      .then((data) => {
        setSuggestions(data.results || []);
        setSuggestionsOpen(true);
      })
      .catch(() => hideSuggestions());
  }

  function hideSuggestions() {
    setSuggestionsOpen(false);
  }

  function onQueryChange(value: string) {
    lastQuery.current = value;
    setStepError(false); // l'erreur « adresse manquante » se dissipe dès la saisie
    if (banTimeout.current) window.clearTimeout(banTimeout.current);
    if (value.trim().length < 3) {
      hideSuggestions();
      return;
    }
    banTimeout.current = window.setTimeout(() => fetchSuggestions(value.trim()), 220);
  }

  function pickSuggestion(s: GeocodeSuggestion) {
    lastQuery.current = s.label;
    hideSuggestions();
    void runDiagnosis(s.label);
  }

  /* ── Diagnostic ── */
  async function runDiagnosis(q: string) {
    const value = q.trim();
    if (!value) {
      setStatus({ text: 'Saisissez une adresse.', kind: 'error' });
      return;
    }
    hideSuggestions();
    setLoading(true);
    setReport(null);
    setRapport(null);
    setRapportError(null);
    setSidebarOpen(false);
    setStatus({ text: 'Géocodage IGN Géoplateforme…', kind: 'loading' });
    setProgress(15);

    try {
      const resp = await fetch(`${API}/diagnostic/adresse?q=${encodeURIComponent(value)}`);
      setProgress(75);

      if (!resp.ok) {
        let detail = `Erreur ${resp.status}`;
        try {
          const err = await resp.json();
          detail = err.detail?.detail || err.detail?.error || JSON.stringify(err.detail) || detail;
        } catch {
          /* corps non-JSON */
        }
        setStatus({ text: detail, kind: 'error' });
        setProgress(0);
        return;
      }

      const r = (await resp.json()) as RisqueReport;
      setReport(r);
      setStepError(false); // l'adresse est validée → étapes suivantes débloquées
      setStep(1); // → étape Cartographie
      if (!userClosedSidebar.current) setSidebarOpen(true);
      setVisibleLayerKeys(
        new Set((r.aleas || []).filter((a) => a.present === true).map((a) => a.code))
      );
      setStatus({
        text: `${r.alea_count} aléa(s) recensé(s) — rapport généré le ${r.date_generation}`,
        kind: 'ok',
      });
      setProgress(100);
      window.setTimeout(() => setProgress(0), 600);
    } catch {
      setStatus({ text: 'Erreur réseau — backend inaccessible ?', kind: 'error' });
      setProgress(0);
    } finally {
      setLoading(false);
    }
  }

  /* ── Rapport narratif IA (Mistral) — POST RisqueReport → RapportNarratif ── */
  async function loadRapport() {
    if (!report || rapport || rapportLoading) return;
    setRapportLoading(true);
    setRapportError(null);
    try {
      const resp = await fetch(`${API}/diagnostic/adresse/rapport`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(report),
      });
      if (!resp.ok) {
        let detail = `Erreur ${resp.status}`;
        try {
          const err = await resp.json();
          detail = err.detail?.detail || err.detail?.error || JSON.stringify(err.detail) || detail;
        } catch {
          /* corps non-JSON */
        }
        throw new Error(detail);
      }
      setRapport((await resp.json()) as RapportNarratif);
    } catch (err) {
      setRapportError(err instanceof Error ? err.message : String(err));
    } finally {
      setRapportLoading(false);
    }
  }

  /* ── Navigation du stepper (linéaire : impossible de sauter l'adresse) ── */
  function goToStep(i: number) {
    if (i > 0 && !report) {
      setStepError(true); // étape Adresse → état d'erreur, navigation bloquée
      window.setTimeout(() => heroInputRef.current?.focus(), 80);
      return;
    }
    setStepError(false);
    setStep(i);
    if (i === 0) window.setTimeout(() => heroInputRef.current?.focus(), 80);
    if (i === 3 && report) void loadRapport();
  }

  /* ── Visibilité des couches ── */
  function toggleLayer(code: string) {
    setVisibleLayerKeys((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function toggleSidebar() {
    setSidebarOpen((o) => {
      userClosedSidebar.current = o; // fermeture manuelle → true · réouverture → false
      return !o;
    });
  }

  function setAllVisible(visible: boolean) {
    if (!report) return;
    const codes = (report.aleas || []).filter((a) => a.present === true).map((a) => a.code);
    setVisibleLayerKeys(visible ? new Set(codes) : new Set());
  }

  /* ── Dérivés du rapport ── */
  const presentAleas = (report?.aleas || []).filter((a) => a.present === true);
  const maxScore = presentAleas.length ? Math.max(...presentAleas.map((a) => aleaScore(a))) : null;
  const band = maxScore != null ? D03.find((b) => (maxScore as number) < b.max) || D03[D03.length - 1] : null;

  const catnat = (report?.aleas || []).flatMap((a) =>
    (a.catnat_historique || []).map((ev) => ({
      ...ev,
      alea_libelle: a.libelle,
    }))
  );

  const wmsActive = !!report && report.aleas.some((a) => WMS_LAYER_MAP[a.code]);
  const pdfUrl = report
    ? `${API}/diagnostic/adresse/rapport-pdf?lat=${report.lat}&lon=${report.lon}`
    : '#';

  const stripText = report
    ? `${report.adresse_normalisee} · ${report.alea_count} aléa(s) · 0 simulés`
    : 'En attente d’une adresse';

  const allPresentVisible =
    report !== null &&
    presentAleas.length > 0 &&
    presentAleas.every((a) => visibleLayerKeys.has(a.code));

  return (
    <main className={`zone-app${sidebarOpen ? ' sidebar-open' : ''}`}>
      {/* ===== STEPPER (indicateur d'étapes, linéaire) ===== */}
      <nav className="zone-stepper" aria-label="Étapes du diagnostic">
        {STEPS.map((s, i) => {
          const active = i === step;
          const done = i < step;
          const isError = i === 0 && stepError;
          return (
            <div className="step-segment" key={s.id}>
              <button
                type="button"
                className={`step-item${active ? ' active' : ''}${done ? ' done' : ''}${
                  isError ? ' error' : ''
                }`}
                aria-current={active ? 'step' : undefined}
                aria-invalid={isError || undefined}
                onClick={() => goToStep(i)}
              >
                <span className="step-dot">
                  {isError ? (
                    <md-icon>error</md-icon>
                  ) : done ? (
                    <md-icon>check</md-icon>
                  ) : (
                    <span>{i + 1}</span>
                  )}
                </span>
                <span className="step-label">{s.label}</span>
              </button>
              {i < STEPS.length - 1 && (
                <span className={`step-connector${done ? ' done' : ''}`} aria-hidden="true" />
              )}
            </div>
          );
        })}
      </nav>

      {/* ===== ÉTAPE 1 — ADRESSE (hero façon Gemini) ===== */}
      {step === 0 && (
        <section className="zone-hero">
          <div className="hero-brand">
            <div className="hero-logo">
              <md-icon>shield</md-icon>
            </div>
            <h1>Diagnostic géo-risque</h1>
            <p>Typhoon · IGN Géoplateforme · Géorisques (BRGM / MTE) · Souverain FR/UE</p>
          </div>

          <div className="hero-search">
            <div className="input-wrap">
              <div className={`hero-field${stepError ? ' shake' : ''}`}>
                <HeroAddressField
                  fieldRef={heroInputRef}
                  initialValue={lastQuery.current}
                  suggestions={suggestions}
                  suggestionsOpen={suggestionsOpen}
                  onQueryChange={onQueryChange}
                  onHideSuggestions={hideSuggestions}
                  onPick={pickSuggestion}
                  onDiagnose={(v) => void runDiagnosis(v)}
                  stepError={stepError}
                />
              </div>
              {stepError && (
                <div className="hero-error" role="alert">
                  <md-icon>error</md-icon>
                  <span>Saisissez d'abord une adresse pour accéder aux étapes suivantes.</span>
                </div>
              )}
            </div>
            <div className="hero-hints">
              <span>ex. 14 Avenue des Palmiers 06000 Nice</span>
              <span>Entrée ↵ pour diagnostiquer</span>
            </div>
          </div>
        </section>
      )}

      {/* ===== ÉTAPES 2–4 : topbar + scène ===== */}
      {step >= 1 && (
        <>
          <header className="zone-topbar">
            <div className="topbar-main">
              <div className="topbar-brand">
                <Link to="/" className="brand-back" aria-label="Retour à l'accueil">
                  <md-icon>arrow_back</md-icon>
                </Link>
              </div>

              <div className="topbar-search">
                <div className="input-wrap">
                  <AddressField
                    id="addr-input"
                    fieldRef={inputRef}
                    initialValue={lastQuery.current}
                    suggestions={suggestions}
                    suggestionsOpen={suggestionsOpen}
                    onQueryChange={onQueryChange}
                    onHideSuggestions={hideSuggestions}
                    onPick={pickSuggestion}
                    onDiagnose={(v) => void runDiagnosis(v)}
                  >
                    <md-icon slot="leading-icon">search</md-icon>
                  </AddressField>
                </div>
              </div>
            </div>
          </header>

          <div className={`zone-stage${step === 1 ? ' workspace' : ' flat'}`}>
            {/* Workspace — toujours monté pour préserver la carte OpenLayers
                (masqué via [hidden] hors de l'étape Cartographie) */}
            <div className="zone-workspace" hidden={step !== 1}>
              {/* RAIL (toolbar latérale toujours visible) */}
              <nav className="zone-rail" aria-label="Panneau latéral">
                <md-icon-button
                  className="rail-toggle"
                  aria-label={
                    sidebarOpen ? 'Réduire le panneau latéral' : 'Déplier le panneau latéral'
                  }
                  aria-expanded={sidebarOpen}
                  onClick={toggleSidebar}
                >
                  <md-icon>{sidebarOpen ? 'menu_open' : 'menu'}</md-icon>
                </md-icon-button>
                <md-icon-button
                  className="rail-search"
                  aria-label="Rechercher une adresse"
                  onClick={() => inputRef.current?.focus()}
                >
                  <md-icon>search</md-icon>
                </md-icon-button>
              </nav>

              {/* SIDEBAR (couches + résultats) */}
              <aside className="zone-sidebar">
                {report ? (
                  <section className="zone-results">
                    <div className="addr-heading">
                      <div className="norm">{report.adresse_normalisee}</div>
                      <div className="meta">
                        GPS {report.lat.toFixed(5)}°N, {report.lon.toFixed(5)}°E · Code INSEE{' '}
                        {report.code_insee} · Généré le {report.date_generation}
                      </div>
                    </div>

                    <details className="legend-section" open>
                      <summary className="section-heading legend-summary">
                        <span>Bandes D03 — Risque</span>
                        <md-icon>expand_more</md-icon>
                      </summary>
                      <div className="legend-box">
                        {D03.map((b, i) => (
                          <div className="legend-row" key={b.key}>
                            <span className="legend-sw" style={{ background: b.color }} />
                            <span>{b.label}</span>
                            <span className="legend-range">{LEGEND_RANGES[i]}</span>
                          </div>
                        ))}
                      </div>
                    </details>

                    <div className="score-block">
                      <div className="score-row">
                        <span className="score-num" style={{ color: band?.color }}>
                          {maxScore ?? '—'}
                        </span>
                        <div className="score-meta">
                          <span className="score-label">Score de risque global /100</span>
                          <span className={`d03-pill ${band ? band.cls : ''}`}>
                            {band ? band.label : 'Indéterminé'}
                          </span>
                        </div>
                      </div>
                      <md-elevated-button
                        href={pdfUrl}
                        target="_blank"
                        rel="noopener"
                        className="pdf-btn"
                      >
                        <md-icon slot="icon">picture_as_pdf</md-icon>
                        Rapport PDF
                      </md-elevated-button>
                    </div>

                    <div className="aleas-section">
                      <div className="section-heading">
                        <span>Aléas recensés — Géorisques</span>
                        <md-text-button
                          className="toggle-all"
                          onClick={() => setAllVisible(!allPresentVisible)}
                        >
                          {allPresentVisible ? 'Tout masquer' : 'Tout afficher'}
                        </md-text-button>
                      </div>
                      <div className="alea-cards">
                        {(report.aleas || []).map((a) => (
                          <AleaCard
                            key={a.code}
                            alea={a}
                            visible={visibleLayerKeys.has(a.code)}
                            onToggle={() => toggleLayer(a.code)}
                          />
                        ))}
                      </div>
                    </div>

                    {catnat.length > 0 && (
                      <details className="catnat-section">
                        <summary className="section-heading catnat-summary">
                          <span>
                            Historique arrêtés CatNat{' '}
                            <span className="catnat-count">({catnat.length} arrêtés)</span>
                          </span>
                          <md-icon>expand_more</md-icon>
                        </summary>
                        <md-list className="catnat-list">
                          {catnat.slice(0, 15).map((ev, i) => (
                            <md-list-item key={i}>
                              <md-icon slot="start">history</md-icon>
                              <span slot="headline">
                                {ev.libelle_risque_jo || ev.libelle || '—'}
                              </span>
                              {ev.date_debut_evt ? (
                                <span slot="supporting-text">
                                  {ev.date_debut_evt.length >= 10
                                    ? ev.date_debut_evt.slice(0, 10)
                                    : ev.date_debut_evt}
                                </span>
                              ) : null}
                            </md-list-item>
                          ))}
                          {catnat.length > 15 && (
                            <md-list-item>
                              <span slot="headline">+ {catnat.length - 15} autre(s)…</span>
                            </md-list-item>
                          )}
                        </md-list>
                      </details>
                    )}

                    {report.erreurs_partielles?.length > 0 && (
                      <div className="partial-banner">
                        <md-icon>warning</md-icon>
                        <span>
                          <strong>Sources partiellement indisponibles :</strong>{' '}
                          {escHtml(report.erreurs_partielles.join(' · '))}. Les aléas concernés
                          affichent « source indisponible ».
                        </span>
                      </div>
                    )}

                    <div className="avertissement">
                      <md-icon>info</md-icon>
                      <span>
                        <strong>⚠ Ce rapport n'est pas l'ERRIAL officiel.</strong> Il agrège les
                        données publiques Géorisques (BRGM / MTE). Il ne remplace pas l'État des
                        Risques réglementaire obligatoire à la vente/location.
                      </span>
                    </div>
                  </section>
                ) : (
                  <div className="sidebar-empty">
                    <md-icon>gps_fixed</md-icon>
                    <p>Recherchez une adresse pour afficher le diagnostic géo-risque.</p>
                  </div>
                )}
              </aside>

              {/* CARTE */}
              <section className="zone-map-wrap">
                <ZoneMap report={report} visibleLayerKeys={visibleLayerKeys} />

                <div className="map-strip">
                  <span>
                    <span className="strip-dot" />
                    <span id="strip-text">{stripText}</span>
                  </span>
                  <span>© CARTO · © OpenStreetMap contributors · © BRGM Géorisques</span>
                </div>
                {wmsActive && <div className="wms-badge">WMS BRGM actif</div>}
              </section>
            </div>

            {/* ÉTAPE 3 — ANALYSE (réservé) */}
            <section className="zone-empty-step" hidden={step !== 2}>
              <md-icon>auto_awesome</md-icon>
              <h2>Analyse approfondie</h2>
              <p>
                Cette étape est en préparation — croisements de données, comparaison de scénarios
                et sources complémentaires (Copernicus, BDNB) y seront intégrés.
              </p>
            </section>

            {/* ÉTAPE 4 — RAPPORT IA (Mistral) */}
            <section className="zone-report" hidden={step !== 3}>
              {!report ? (
                <div className="report-empty">
                  <md-icon>description</md-icon>
                  <h2>Aucun diagnostic</h2>
                  <p>Diagnostiquez d'abord une adresse pour générer le rapport d'analyse IA.</p>
                  <md-filled-button onClick={() => goToStep(0)}>
                    <md-icon slot="icon">search</md-icon> Chercher une adresse
                  </md-filled-button>
                </div>
              ) : rapportLoading ? (
                <div className="report-empty">
                  <md-icon>psychology</md-icon>
                  <h2>Génération du rapport IA…</h2>
                  <p>Mistral analyse les données Géorisques de {report.adresse_normalisee}.</p>
                  <md-linear-progress indeterminate></md-linear-progress>
                </div>
              ) : rapportError ? (
                <div className="report-empty">
                  <md-icon>error</md-icon>
                  <h2>Rapport indisponible</h2>
                  <p>{rapportError}</p>
                  <md-filled-button onClick={() => void loadRapport()}>
                    <md-icon slot="icon">refresh</md-icon> Réessayer
                  </md-filled-button>
                </div>
              ) : rapport ? (
                <>
                  <header className="report-header">
                    <div className="report-title">
                      <h2>Rapport d'analyse IA</h2>
                      <p className="report-meta">
                        {report.adresse_normalisee} · Code INSEE {report.code_insee} ·{' '}
                        {report.date_generation}
                      </p>
                    </div>
                    <md-elevated-button
                      className="pdf-btn report-export"
                      href={pdfUrl}
                      target="_blank"
                      rel="noopener"
                    >
                      <md-icon slot="icon">picture_as_pdf</md-icon>
                      Exporter en PDF
                    </md-elevated-button>
                  </header>

                  <p className="report-intro">{rapport.introduction}</p>

                  <div className="report-sections">
                    {rapport.sections.map((s, i) => (
                      <article className="report-section" key={i}>
                        <h3>{s.titre}</h3>
                        <p>{s.contenu}</p>
                      </article>
                    ))}
                  </div>

                  <aside className="report-synthese">
                    <md-icon>summarize</md-icon>
                    <div>
                      <h3>Synthèse finale</h3>
                      <p>{rapport.synthese_finale}</p>
                    </div>
                  </aside>

                  {rapport.obligations_reglementaires &&
                    rapport.obligations_reglementaires.length > 0 && (
                      <section className="report-obligations">
                        <h3>Obligations réglementaires</h3>
                        <ul>
                          {rapport.obligations_reglementaires.map((o, i) => (
                            <li key={i}>{o}</li>
                          ))}
                        </ul>
                      </section>
                    )}

                  <p className="report-avertissement">
                    <md-icon>info</md-icon>
                    <span>
                      {rapport.avertissement_ia ||
                        "Ce rapport est généré automatiquement par IA à partir des données publiques Géorisques normalisées. Il ne remplace pas l'ERRIAL ni l'avis d'un expert."}
                    </span>
                  </p>
                </>
              ) : (
                <div className="report-empty">
                  <md-icon>description</md-icon>
                  <h2>Prêt à générer</h2>
                  <p>
                    Générez le rapport narratif IA à partir du diagnostic{' '}
                    {report.adresse_normalisee}.
                  </p>
                  <md-filled-button onClick={() => void loadRapport()}>
                    <md-icon slot="icon">auto_awesome</md-icon> Générer le rapport
                  </md-filled-button>
                </div>
              )}
            </section>
          </div>
        </>
      )}

      {/* ===== OVERLAY de statut (pendant le diagnostic) ===== */}
      {(loading || status.kind === 'error') && (
        <div
          className={`diagnosis-overlay${status.kind === 'error' ? ' overlay-error' : ''}`}
          role={status.kind === 'error' ? 'alert' : 'status'}
          aria-live="polite"
          onClick={
            status.kind === 'error' ? () => setStatus({ text: '', kind: '' }) : undefined
          }
        >
          <div className="overlay-card">
            <span className="overlay-msg">{status.text}</span>
            {loading ? (
              <md-linear-progress value={progress / 100}></md-linear-progress>
            ) : (
              <span className="overlay-hint">Cliquez pour fermer</span>
            )}
          </div>
        </div>
      )}
    </main>
  );
}

/* ── Champ d'adresse de l'étape 1 (hero) — input natif simple ──
   Un <input type="search"> standard stylé en pilule : aucune dépendance au
   champ Material (md-outlined-text-field), donc aucune largeur intrinsèque
   qui pourrait dépasser la page. Ref, écouteurs et dropdown propres. */
function HeroAddressField({
  fieldRef,
  initialValue,
  suggestions,
  suggestionsOpen,
  onQueryChange,
  onHideSuggestions,
  onPick,
  onDiagnose,
  stepError,
}: {
  fieldRef: RefObject<HTMLInputElement | null>;
  initialValue: string;
  suggestions: GeocodeSuggestion[];
  suggestionsOpen: boolean;
  onQueryChange: (value: string) => void;
  onHideSuggestions: () => void;
  onPick: (s: GeocodeSuggestion) => void;
  onDiagnose: (value: string) => void;
  stepError: boolean;
}) {
  /* Écouteurs attachés au montage ; la valeur initiale restaure la dernière
     requête saisie (lastQuery) lorsque le champ est (ré)monté. */
  useEffect(() => {
    const el = fieldRef.current;
    if (!el) return;
    el.value = initialValue;
    const onInput = () => onQueryChange(el.value);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        onHideSuggestions();
        onDiagnose(el.value);
      }
    };
    const onBlur = () => window.setTimeout(onHideSuggestions, 180);
    el.addEventListener('input', onInput);
    el.addEventListener('keydown', onKey);
    el.addEventListener('blur', onBlur);
    return () => {
      el.removeEventListener('input', onInput);
      el.removeEventListener('keydown', onKey);
      el.removeEventListener('blur', onBlur);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handlePick(s: GeocodeSuggestion) {
    if (fieldRef.current) fieldRef.current.value = s.label;
    onPick(s);
  }

  return (
    <>
      <div className={`hero-pill${stepError ? ' hero-pill-error' : ''}`}>
        <md-icon className="hero-pill-icon" aria-hidden="true">
          search
        </md-icon>
        <input
          ref={fieldRef}
          id="addr-input-hero"
          type="search"
          placeholder="Rechercher une adresse en France…"
          autoComplete="off"
          spellCheck={false}
          inputMode="search"
          className="hero-pill-input"
          aria-label="Rechercher une adresse"
        />
        <md-icon-button
          className="hero-send"
          aria-label="Diagnostiquer cette adresse"
          onClick={() => {
            const el = fieldRef.current;
            if (el) void onDiagnose(el.value);
          }}
        >
          <md-icon>arrow_forward</md-icon>
        </md-icon-button>
      </div>
      {suggestionsOpen && suggestions.length > 0 && (
        <Suggestions suggestions={suggestions} onPick={handlePick} />
      )}
    </>
  );
}

/* ── Champ d'adresse réutilisable (topbar) ──
   Chaque instance possède son propre md-outlined-text-field (ref distincte),
   ses écouteurs (autocomplétion BAN, Entrée) et son dropdown de suggestions. */
function AddressField({
  id,
  fieldRef,
  initialValue,
  suggestions,
  suggestionsOpen,
  onQueryChange,
  onHideSuggestions,
  onPick,
  onDiagnose,
  children,
}: {
  id: string;
  fieldRef: RefObject<HTMLElement & { value: string } | null>;
  initialValue: string;
  suggestions: GeocodeSuggestion[];
  suggestionsOpen: boolean;
  onQueryChange: (value: string) => void;
  onHideSuggestions: () => void;
  onPick: (s: GeocodeSuggestion) => void;
  onDiagnose: (value: string) => void;
  children?: ReactNode;
}) {
  /* Écouteurs attachés au montage : la valeur initiale restaure la dernière
     requête saisie (lastQuery) lorsque le champ est (ré)monté. */
  useEffect(() => {
    const el = fieldRef.current;
    if (!el) return;
    el.value = initialValue;
    const onInput = () => onQueryChange(el.value);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        onHideSuggestions();
        onDiagnose(el.value);
      }
    };
    const onBlur = () => window.setTimeout(onHideSuggestions, 180);
    el.addEventListener('input', onInput);
    el.addEventListener('keydown', onKey);
    el.addEventListener('blur', onBlur);
    return () => {
      el.removeEventListener('input', onInput);
      el.removeEventListener('keydown', onKey);
      el.removeEventListener('blur', onBlur);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handlePick(s: GeocodeSuggestion) {
    if (fieldRef.current) fieldRef.current.value = s.label;
    onPick(s);
  }

  return (
    <>
      <md-outlined-text-field
        ref={fieldRef}
        id={id}
        type="search"
        placeholder="Rechercher une adresse en France…"
        label="Rechercher une adresse"
        autoComplete="off"
        spellCheck={false}
        inputMode="search"
      >
        {children}
      </md-outlined-text-field>
      {suggestionsOpen && suggestions.length > 0 && (
        <Suggestions suggestions={suggestions} onPick={handlePick} />
      )}
    </>
  );
}

/* ── Suggestions BAN (dropdown) ── */
function Suggestions({
  suggestions,
  onPick,
}: {
  suggestions: GeocodeSuggestion[];
  onPick: (s: GeocodeSuggestion) => void;
}) {
  return (
    <div className="ban-suggestions">
      <md-list>
        {suggestions.map((s, i) => (
          <md-list-item
            key={i}
            onMouseDown={(e: { preventDefault: () => void }) => e.preventDefault()}
            onClick={() => onPick(s)}
          >
            <span slot="headline">{s.label}</span>
            {s.context ? <span slot="supporting-text">{s.context}</span> : null}
          </md-list-item>
        ))}
      </md-list>
    </div>
  );
}

/* ── Carte d'aléa ── */
function AleaCard({
  alea,
  visible,
  onToggle,
}: {
  alea: AleaDetail;
  visible: boolean;
  onToggle: () => void;
}) {
  const band = alea.niveau ? bandForKey(alea.niveau) : undefined;
  const icon = ALEA_ICONS[alea.code] || ALEA_ICON_FALLBACK;
  const isError = alea.present === null;
  const isAbsent = alea.present === false;

  const addrPresent = alea.present === true;
  const communePresent = alea.present_commune !== false;

  return (
    <div className={`alea-card${isAbsent ? ' absent' : ''}${isError ? ' error-partial' : ''}`}>
      <span className={`alea-icon ${band ? band.cls : ''}`}>
        <md-icon>{icon}</md-icon>
      </span>

      <div className="alea-left">
        <span className="alea-name">{alea.libelle}</span>
        <div className="alea-statuses">
          {isError ? (
            <span className="status-chip chip-off">
              <md-icon>cloud_off</md-icon> source indisponible
            </span>
          ) : (
            <>
              <span className={`status-chip ${addrPresent ? 'chip-on' : 'chip-off'}`}>
                <md-icon>location_on</md-icon>
                {addrPresent ? 'CONCERNÉ' : 'PAS DE RISQUE'}
              </span>
              <span className={`status-chip ${communePresent ? 'chip-mid' : 'chip-off'}`}>
                <md-icon>account_balance</md-icon>
                {communePresent ? 'EXISTANT' : 'NON CONCERNÉ'}
              </span>
            </>
          )}
        </div>
        {alea.zonage ? <span className="alea-zonage">{alea.zonage}</span> : null}
      </div>

      <div className="alea-right">
        <md-icon-button
          className="eye-btn"
          aria-label="Afficher/masquer la couche sur la carte"
          aria-pressed={visible}
          onClick={onToggle}
        >
          <md-icon>{visible ? 'visibility' : 'visibility_off'}</md-icon>
        </md-icon-button>
        {band && alea.present === true ? (
          <span className={`d03-pill ${band.cls}`}>{band.label}</span>
        ) : null}
        {alea.url_detail ? (
          <a className="alea-link" href={alea.url_detail} target="_blank" rel="noopener">
            <md-icon>open_in_new</md-icon>
          </a>
        ) : null}
      </div>
    </div>
  );
}
