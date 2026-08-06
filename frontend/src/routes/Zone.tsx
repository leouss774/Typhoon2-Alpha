// =============================================================================
//   TYPHOON — /zone : diagnostic géo-risque par adresse (Stepper Material 3)
//   Étapes :
//     1. Adresse      — hero centré façon Gemini (champ de recherche au centre)
//     2. Cartographie — carte OpenLayers + panneau aléas (data viz Géorisques)
//     3. Analyse      — risques industriels & technologiques
//     4. Rapport IA   — rapport narratif Mistral + module économie
//
//   Stepper linéaire : les étapes 2-4 sont bloquées tant qu'aucune adresse
//   n'a été diagnostiquée — l'étape Adresse passe en état d'erreur (icône
//   erreur + message) si l'on tente de les atteindre sans rapport.
// =============================================================================

import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Menu } from '@material/web/menu/menu.js';
import type { MdSwitch } from '@material/web/switch/switch.js';
import { ZoneMap } from '../components/ZoneMap';
import { ACCENTS, useTyphoonTheme } from '../typhoon/useTyphoonTheme';
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
import { runEconomiePipeline } from './economie/api';
import type { ResultatEconomie } from './economie/types';
import { PlanUsinePanel, TYPES_ZONE_LABELS, type PlanUsine } from './PlanUsine';
import '../styles/zone.css';

const LEGEND_RANGES = ['<20', '20–39', '40–59', '60–79', '≥80'];

const STEPS = [
  { id: 'adresse', label: 'Adresse' },
  { id: 'carto', label: 'Cartographie' },
  { id: 'analyse', label: 'Analyse' },
  { id: 'rapport', label: 'Rapport IA' },
] as const;

export function Zone() {
  const navigate = useNavigate();
  const { theme, accent, toggleTheme, pickAccent, resetAccent } = useTyphoonTheme();
  const isMobile = useIsMobile();
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsMenuRef = useRef<Menu | null>(null);
  const themeSwitchRef = useRef<MdSwitch | null>(null);
  const sidenavRef = useRef<HTMLElement | null>(null);

  /* Ouverture du drawer mobile : amener le focus dans la navigation. */
  useEffect(() => {
    if (!isMobile || !drawerOpen) return;
    const first = sidenavRef.current?.querySelector<HTMLElement>(
      'a, [tabindex]:not([tabindex="-1"])'
    );
    first?.focus();
  }, [isMobile, drawerOpen]);

  /* Le menu réglages se referme de lui-même (clic extérieur / Échap) → on
     resynchronise l'état React sur l'événement `closed` du md-menu. */
  useEffect(() => {
    const menu = settingsMenuRef.current;
    if (!menu) return;
    const onClosed = () => setSettingsOpen(false);
    menu.addEventListener('closed', onClosed);
    return () => menu.removeEventListener('closed', onClosed);
  }, []);

  /* md-switch émet `change` (custom element) — on écoute via le ref. */
  useEffect(() => {
    const sw = themeSwitchRef.current;
    if (!sw) return;
    const onChange = () => toggleTheme();
    sw.addEventListener('change', onChange);
    return () => sw.removeEventListener('change', onChange);
  }, [toggleTheme]);

  const [step, setStep] = useState(0);
  const [stepError, setStepError] = useState(false);
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [diagError, setDiagError] = useState<string | null>(null);
  const [report, setReport] = useState<RisqueReport | null>(null);
  const [rapport, setRapport] = useState<RapportNarratif | null>(null);
  const [rapportLoading, setRapportLoading] = useState(false);
  const [rapportError, setRapportError] = useState<string | null>(null);
  const [economie, setEconomie] = useState<ResultatEconomie | null>(null);
  const [economieLoading, setEconomieLoading] = useState(false);
  const [economieError, setEconomieError] = useState<string | null>(null);
  const [planUsineOpen, setPlanUsineOpen] = useState(false);
  const [planUsineResult, setPlanUsineResult] = useState<any>(null);
  const [planUsineLoading, setPlanUsineLoading] = useState(false);
  const [planUsineError, setPlanUsineError] = useState<string | null>(null);
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
    setDiagError(null); // l'erreur d'API se dissipe aussi dès la saisie
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
      setDiagError('Saisissez une adresse.');
      return;
    }
    hideSuggestions();
    setDiagError(null);
    setLoading(true);
    setReport(null);
    setRapport(null);
    setRapportError(null);
    setEconomie(null);
    setEconomieError(null);
    setSidebarOpen(false);

    try {
      const resp = await fetch(`${API}/diagnostic/adresse?q=${encodeURIComponent(value)}`);

      if (!resp.ok) {
        let detail = `Erreur ${resp.status}`;
        try {
          const err = await resp.json();
          detail = err.detail?.detail || err.detail?.error || JSON.stringify(err.detail) || detail;
        } catch {
          /* corps non-JSON */
        }
        setDiagError(detail);
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
    } catch {
      setDiagError('Erreur réseau — backend inaccessible ?');
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

  /* ── Module économie — utilise la MÊME adresse analysée (workflow fluide) ── */
  async function loadEconomie() {
    if (!lastQuery.current.trim() || economie || economieLoading) return;
    setEconomieLoading(true);
    setEconomieError(null);
    try {
      const res = await runEconomiePipeline(lastQuery.current);
      setEconomie(res);
    } catch (err) {
      setEconomieError(err instanceof Error ? err.message : String(err));
    } finally {
      setEconomieLoading(false);
    }
  }

  /* ── Niveau 2 — Plan d'usine (enrichit le score) ── */
  async function enrichirPlanUsine(plan: PlanUsine) {
    if (planUsineLoading) return;
    setPlanUsineLoading(true);
    setPlanUsineError(null);
    try {
      // Récupérer les risk_scores via le pipeline fast (même adresse)
      const fast = await fetch(`${API}/diagnostic/fast`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ adresse: lastQuery.current, copernicus: false }),
      });
      if (!fast.ok) {
        const err = await fast.json().catch(() => ({}));
        throw new Error(err.detail?.detail || `HTTP ${fast.status}`);
      }
      const fastData = await fast.json();
      const resume = fastData._resume;
      if (!resume) throw new Error('Contrat rapide sans _resume');

      const resp = await fetch(`${API}/diagnostic/plan-usine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          risk_scores: resume.risk_scores,
          plan,
          adresse: lastQuery.current,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail?.detail || `HTTP ${resp.status}`);
      }
      const resultat = await resp.json();
      setPlanUsineResult(resultat);
      setPlanUsineOpen(false);
    } catch (err) {
      setPlanUsineError(err instanceof Error ? err.message : String(err));
    } finally {
      setPlanUsineLoading(false);
    }
  }

  /* ── Navigation du stepper (linéaire : impossible de sauter l'adresse) ── */
  function goToStep(i: number) {
    if (i > 0 && !report) {
      setStepError(true); // étape Adresse → état d'erreur, navigation bloquée
      setDiagError(null); // le message du stepper prime sur une erreur d'API antérieure
      window.setTimeout(() => heroInputRef.current?.focus(), 80);
      return;
    }
    setStepError(false);
    setStep(i);
    if (i === 0) window.setTimeout(() => heroInputRef.current?.focus(), 80);
    if (i === 3 && report) {
      void loadRapport();
      void loadEconomie();
    }
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
    const codes = (report.aleas || []).map((a) => a.code);
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
    (report.aleas || []).length > 0 &&
    (report.aleas || []).every((a) => visibleLayerKeys.has(a.code));

  return (
    <main
      className={`zone-app${theme === 'light' ? ' theme-light' : ''}${
        sidebarOpen ? ' sidebar-open' : ''
      }${navCollapsed && !isMobile ? ' nav-collapsed' : ''}${drawerOpen ? ' drawer-open' : ''}`}
      style={{ '--accent': accent } as CSSProperties}
    >
      {/* ===== SIDENAV rétractable (navigation façon Gemini) ===== */}
      <ZoneSidenav
        sidenavRef={sidenavRef}
        collapsed={navCollapsed && !isMobile}
        mobile={isMobile}
        hidden={isMobile && !drawerOpen}
        theme={theme}
        accent={accent}
        settingsOpen={settingsOpen}
        settingsMenuRef={settingsMenuRef}
        themeSwitchRef={themeSwitchRef}
        onToggleCollapse={() =>
          isMobile ? setDrawerOpen(false) : setNavCollapsed((c) => !c)
        }
        onPickAccent={pickAccent}
        onResetAccent={resetAccent}
        onOpenSettings={() => setSettingsOpen((o) => !o)}
        onCloseDrawer={() => setDrawerOpen(false)}
        onNewDiagnostic={() => {
          setDrawerOpen(false);
          goToStep(0);
        }}
      />

      {/* ===== COLONNE PRINCIPALE ===== */}
      <div className="zone-main">
        {/* ===== STEPPER (indicateur d'étapes, linéaire) ===== */}
        <nav className="zone-stepper" aria-label="Étapes du diagnostic">
          <md-icon-button
            className="sidenav-hamburger"
            aria-label="Ouvrir le menu"
            onClick={() => setDrawerOpen(true)}
          >
            <md-icon>menu</md-icon>
          </md-icon-button>
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
            <h1>Diagnostic géo-risque</h1>
          </div>

          <div className="hero-search">
            <div className="input-wrap">
              <div className={`hero-field${stepError || diagError ? ' shake' : ''}`}>
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
                  loading={loading}
                  error={diagError}
                />
              </div>
              {loading ? (
                <div className="hero-thinking" role="status" aria-live="polite">
                  <span className="hero-thinking-dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span className="hero-thinking-txt">Diagnostic en cours…</span>
                </div>
              ) : (
                (stepError || diagError) && (
                  <div className="hero-error" role="alert">
                    <md-icon>error</md-icon>
                    <span>
                      {diagError ||
                        "Saisissez d'abord une adresse pour accéder aux étapes suivantes."}
                    </span>
                  </div>
                )
              )}
            </div>
            {!loading && (
              <div className="hero-hints">
                <span>ex. 14 Avenue des Palmiers 06000 Nice</span>
                <span>Entrée ↵ pour diagnostiquer</span>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ===== ÉTAPES 2–4 : topbar + scène ===== */}
      {step >= 1 && (
        <>
          <header className="zone-topbar">
            <div className="topbar-main">
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

              <div className="topbar-actions">
                <md-icon-button
                  toggle
                  selected={sidebarOpen}
                  className="panel-toggle"
                  aria-label="Afficher / masquer le panneau des aléas"
                  title="Panneau des aléas"
                  aria-pressed={sidebarOpen}
                  onClick={toggleSidebar}
                >
                  <md-icon>view_sidebar</md-icon>
                  <md-icon slot="selected">view_sidebar</md-icon>
                </md-icon-button>
              </div>
            </div>
          </header>

          <div className={`zone-stage${step === 1 ? ' workspace' : ' flat'}`}>
            {/* Workspace — toujours monté pour préserver la carte OpenLayers
                (masqué via [hidden] hors de l'étape Cartographie) */}
            <div className="zone-workspace" hidden={step !== 1}>
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
                    </div>

                    <div className="aleas-section">
                      <div className="section-heading">
                        <span>Aléas recensés — Géorisques</span>
                        <md-text-button
                          className="toggle-all"
                          aria-label={
                            allPresentVisible
                              ? 'Masquer toutes les couches sur la carte'
                              : 'Afficher toutes les couches sur la carte'
                          }
                          onClick={() => setAllVisible(!allPresentVisible)}
                        >
                          <md-icon slot="icon">
                            {allPresentVisible ? 'visibility' : 'visibility_off'}
                          </md-icon>
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

            {/* ÉTAPE 3 — ANALYSE (risques industriels & technologiques) */}
            <section className="zone-analysis" hidden={step !== 2}>
              {!report ? (
                <div className="report-empty">
                  <md-icon>search</md-icon>
                  <h2>Aucun diagnostic</h2>
                  <p>Diagnostiquez d'abord une adresse pour voir l'analyse approfondie.</p>
                </div>
              ) : (
                <>
                  <header className="analysis-header">
                    <div className="analysis-title">
                      <h2>Analyse des risques</h2>
                      <p className="report-meta">
                        {report.adresse_normalisee} · {report.alea_count} aléa(s) recensé(s)
                      </p>
                    </div>
                  </header>

                  {/* Score global */}
                  <div className="analysis-score-block">
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
                  </div>

                  {/* Synthèse des aléas */}
                  <div className="analysis-section">
                    <h3>Aléas recensés</h3>
                    <div className="analysis-grid">
                      {(report.aleas || []).map((a) => {
                        const aband = a.niveau ? bandForKey(a.niveau) : undefined;
                        const aicon = ALEA_ICONS[a.code] || ALEA_ICON_FALLBACK;
                        return (
                          <div
                            key={a.code}
                            className={`analysis-card${a.present === true ? ' present' : ''}${
                              a.present === null ? ' error-partial' : ''
                            }`}
                          >
                            <span className={`alea-icon ${aband ? aband.cls : ''}`}>
                              <md-icon>{aicon}</md-icon>
                            </span>
                            <div className="analysis-card-body">
                              <span className="analysis-card-name">{a.libelle}</span>
                              {a.present === true ? (
                                <span className={`d03-pill ${aband ? aband.cls : ''}`}>
                                  {aband ? aband.label : 'Présent'}
                                </span>
                              ) : a.present === null ? (
                                <span className="status-chip chip-off">
                                  <md-icon>cloud_off</md-icon> source indisponible
                                </span>
                              ) : (
                                <span className="status-chip chip-off">
                                  <md-icon>check_circle</md-icon> non concerné
                                </span>
                              )}
                              {a.zonage ? <p className="analysis-card-zone">{a.zonage}</p> : null}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Risques industriels & technologiques */}
                  <div className="analysis-section analysis-section-industry">
                    <h3>🏭 Risques industriels & technologiques</h3>
                    <div className="analysis-industry-banner">
                      <md-icon>factory</md-icon>
                      <span>
                        <strong>Sites industriels (ICPE), sols pollués et plans de prévention
                        des risques technologiques (PPRT)</strong> sont intégrés à l'analyse.
                        Ces données proviennent de Géorisques (BRGM / MTE).
                      </span>
                    </div>
                    <div className="analysis-industry-list">
                      {['icpe', 'ssp', 'pprt', 'canalisations'].map((code) => {
                        const alea = (report.aleas || []).find((x) => x.code === code);
                        if (!alea) return null;
                        const aband = alea.niveau ? bandForKey(alea.niveau) : undefined;
                        const aicon = ALEA_ICONS[code] || ALEA_ICON_FALLBACK;
                        return (
                          <div className="analysis-industry-row" key={code}>
                            <span className={`alea-icon ${aband ? aband.cls : ''}`}>
                              <md-icon>{aicon}</md-icon>
                            </span>
                            <div className="analysis-industry-info">
                              <span className="analysis-industry-name">{alea.libelle}</span>
                              {alea.zonage ? (
                                <span className="analysis-industry-zone">{alea.zonage}</span>
                              ) : null}
                            </div>
                            {alea.present === true ? (
                              <span className={`d03-pill ${aband ? aband.cls : ''}`}>
                                {aband ? aband.label : 'Présent'}
                              </span>
                            ) : alea.present === null ? (
                              <span className="status-chip chip-off">
                                <md-icon>cloud_off</md-icon>
                              </span>
                            ) : (
                              <span className="status-chip chip-off">
                                <md-icon>check_circle</md-icon> non concerné
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Plan du bâtiment (niveau 2) — disponible pour tous, adapté pour les usines */}
                  <div className="analysis-section analysis-section-usine">
                    <h3>
                      🏗️ Plan du bâtiment (niveau 2 — optionnel)
                      {report?.type_batiment?.type === 'industriel' && ' — Usine détectée'}
                    </h3>
                    <div className="analysis-usine-note">
                      <md-icon>info</md-icon>
                      <span>
                        Enrichissez le score de risque avec le plan réel du bâtiment : zones,
                        équipements critiques, matières dangereuses.
                        {report?.type_batiment?.type === 'industriel' && (
                          <span> Pour les <strong>usines</strong>, le score intègre également les{' '}
                            <strong>zones industrielles spécifiques</strong> (charpente, équipements
                            de production, stockage, cuves/réservoirs) et une{' '}
                            <strong>vulnérabilité adaptée</strong>.</span>
                        )}
                        <br />
                        Formats supportés : Images (JPG, PNG) · GeoJSON · JSON · CSV · DXF.
                      </span>
                    </div>

                      {/* Niveau 2 — Plan d'usine (optionnel, uniquement pour les usines) */}
                      {!planUsineOpen && (
                        <div className="plan-usine-banner">
                          <div className="plan-usine-banner-info">
                            <strong>
                              📐 Niveau 2 — Plan de l'usine (optionnel)
                            </strong>
                            <span>
                              Enrichissez le score avec le plan réel de l'usine : zones, équipements critiques, matières dangereuses.
                            </span>
                          </div>
                          <md-filled-button onClick={() => setPlanUsineOpen(true)}>
                            <md-icon slot="icon">map</md-icon>
                            Importer le plan
                          </md-filled-button>
                        </div>
                      )}

                      {planUsineOpen && (
                        <PlanUsinePanel
                          onEnrichir={(plan) => void enrichirPlanUsine(plan)}
                          onClose={() => setPlanUsineOpen(false)}
                        />
                      )}

                      {planUsineLoading && (
                        <div className="plan-usine-loading">
                          <md-linear-progress indeterminate></md-linear-progress>
                          <span>Enrichissement du score avec le plan…</span>
                        </div>
                      )}

                      {planUsineError && (
                        <div className="plan-usine-error">
                          <md-icon>error</md-icon>
                          <span>{planUsineError}</span>
                        </div>
                      )}

                      {planUsineResult?.plan_usine && (
                        <div className="plan-usine-result">
                          <h4>✅ Score enrichi avec le plan</h4>
                          <div className="plan-usine-result-grid">
                            <div className="plan-usine-result-kpi">
                              <span className="plan-usine-result-label">Score global plan</span>
                              <span className="plan-usine-result-value">
                                {planUsineResult.plan_usine.score_plan_global}/100
                              </span>
                            </div>
                            <div className="plan-usine-result-kpi">
                              <span className="plan-usine-result-label">Zones personnalisées</span>
                              <span className="plan-usine-result-value">
                                {planUsineResult.plan_usine.nb_zones}
                              </span>
                            </div>
                            <div className="plan-usine-result-kpi">
                              <span className="plan-usine-result-label">Équipements</span>
                              <span className="plan-usine-result-value">
                                {planUsineResult.plan_usine.nb_equipements}
                              </span>
                            </div>
                            <div className="plan-usine-result-kpi plan-usine-result-kpi-accent">
                              <span className="plan-usine-result-label">Confiance</span>
                              <span className="plan-usine-result-value">
                                {planUsineResult.plan_usine.confiance_plan.score}/100
                              </span>
                              <span className="plan-usine-result-sub">
                                {planUsineResult.plan_usine.confiance_plan.message}
                              </span>
                            </div>
                          </div>
                          <div className="plan-usine-result-zones">
                            <h5>Vulnérabilité par zone</h5>
                            {Object.keys(planUsineResult.plan_usine.zones_plan || {}).map((zoneId) => {
                              const zones = planUsineResult.plan_usine.zones_plan as Record<string, any>;
                              const zone = zones[zoneId];
                              const zband = zone.niveau ? bandForKey(zone.niveau) : undefined;
                              return (
                                <div className="plan-usine-result-zone" key={zoneId}>
                                  <div className="plan-usine-result-zone-top">
                                    <span className="plan-usine-result-zone-name">{zone.nom}</span>
                                    <span className="plan-usine-result-zone-type">
                                      {TYPES_ZONE_LABELS[zone.type] || zone.type}
                                    </span>
                                    {zband ? (
                                      <span className={`d03-pill ${zband.cls}`}>{zband.label}</span>
                                    ) : null}
                                  </div>
                                  <div className="plan-usine-result-zone-values">
                                    <span className="plan-usine-result-zone-value">
                                      Risque {zone.risque}/100
                                    </span>
                                    <span className="plan-usine-result-zone-sub">
                                      Vulnérabilité {zone.vulnerabilite}/100
                                    </span>
                                  </div>
                                  {(zone.description || zone.justification) && (
                                    <p className="plan-usine-result-zone-desc">
                                      {zone.description || zone.justification}
                                    </p>
                                  )}
                                  {zone.equipements?.length > 0 && (
                                    <div className="plan-usine-result-zone-eqs">
                                      <span className="plan-usine-result-zone-eqs-label">
                                        Équipements :
                                      </span>
                                      {zone.equipements.map((eq: any, i: number) => (
                                        <span
                                          className={`plan-usine-result-zone-eq${
                                            eq.matieres_dangereuses || eq.critique_production
                                              ? ' critical'
                                              : ''
                                          }`}
                                          key={i}
                                        >
                                          {eq.nom || eq.type || 'Équipement'}
                                          {eq.matieres_dangereuses && (
                                            <md-icon title="Matières dangereuses">warning</md-icon>
                                          )}
                                          {eq.critique_production && (
                                            <md-icon title="Critique production">bolt</md-icon>
                                          )}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>

                  {report.erreurs_partielles?.length > 0 && (
                    <div className="partial-banner">
                      <md-icon>warning</md-icon>
                      <span>
                        <strong>Sources partiellement indisponibles :</strong>{' '}
                        {escHtml(report.erreurs_partielles.join(' · '))}.
                      </span>
                    </div>
                  )}

                  <div className="avertissement">
                    <md-icon>info</md-icon>
                    <span>
                      <strong>⚠ Ce rapport ne remplace pas l'ERRIAL officiel.</strong> Il agrège
                      les données publiques Géorisques (BRGM / MTE) et intègre les risques
                      industriels et technologiques pour les sites industriels.
                    </span>
                  </div>
                </>
              )}
            </section>
          </div>
        </>
      )}

      {/* ÉTAPE 4 — RAPPORT IA (Mistral) + Module économie */}
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
              ) : (
                <>
                  {/* ── Rapport IA : état selon Mistral ── */}
                  {rapportLoading ? (
                    <div className="report-empty">
                      <md-icon>psychology</md-icon>
                      <h2>Génération du rapport IA…</h2>
                      <p>Mistral analyse les données Géorisques de {report.adresse_normalisee}.</p>
                      <md-linear-progress indeterminate></md-linear-progress>
                    </div>
                  ) : rapportError ? (
                    <div className="report-empty">
                      <md-icon>error</md-icon>
                      <h2>Rapport IA indisponible</h2>
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

                  {/* ── Module économie (TOUJOURS affiché, même si rapport IA échoue) ── */}
                  <section className="report-economie">
                    <header className="report-economie-header">
                      <h3>💶 Analyse économique des travaux</h3>
                      <p className="report-economie-meta">
                        Calculé pour {economie?.adresse || report.adresse_normalisee}
                      </p>
                    </header>

                    {economieLoading ? (
                      <div className="report-economie-loading">
                        <md-linear-progress indeterminate></md-linear-progress>
                        <span>Calcul du retour sur investissement…</span>
                      </div>
                    ) : economieError ? (
                      <div className="report-economie-error">
                        <md-icon>error</md-icon>
                        <span>{economieError}</span>
                      </div>
                    ) : economie?.contract ? (
                      (() => {
                        const c = economie.contract;
                        const fmtEur = (b: any) =>
                          !b || b.statut === 'null'
                            ? 'Non calculé'
                            : new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(
                                b.valeur ?? (b.min + b.max) / 2
                              );
                        const fmtAn = (b: any) =>
                          !b || b.statut === 'null'
                            ? 'Non calculé'
                            : `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 }).format(
                                b.valeur ?? (b.min + b.max) / 2
                              )} ans`;
                        return (
                          <div className="report-economie-grid">
                            <div className="report-economie-kpi">
                              <span className="report-economie-kpi-label">Coût net</span>
                              <span className="report-economie-kpi-value">
                                {fmtEur(c.niveau_b?.cout_travaux?.cout_net)}
                              </span>
                              <span className="report-economie-kpi-sub">après subventions</span>
                            </div>
                            <div className="report-economie-kpi">
                              <span className="report-economie-kpi-label">Bénéfice annuel</span>
                              <span className="report-economie-kpi-value">
                                {fmtEur(c.niveau_b?.benefice_assurance?.total)}
                              </span>
                              <span className="report-economie-kpi-sub">sinistres évités</span>
                            </div>
                            <div className="report-economie-kpi">
                              <span className="report-economie-kpi-label">Retour sur investissement</span>
                              <span className="report-economie-kpi-value">
                                {fmtAn(c.roi?.temps_de_retour)}
                              </span>
                              <span className="report-economie-kpi-sub">pour rentabiliser</span>
                            </div>
                            <div className="report-economie-kpi report-economie-kpi-accent">
                              <span className="report-economie-kpi-label">Confiance</span>
                              <span className="report-economie-kpi-value">
                                {c.confidence?.score ?? '—'}/100
                              </span>
                              <span className="report-economie-kpi-sub">
                                niveau {c.confidence?.niveau ?? '—'}
                              </span>
                            </div>
                          </div>
                        );
                      })()
                    ) : (
                      <button type="button" className="report-economie-cta" onClick={() => void loadEconomie()}>
                        <md-icon slot="icon">calcul</md-icon>
                        Calculer le retour sur investissement
                      </button>
                    )}
                  </section>
                </>
              )}
            </section>
      </div>

      {/* Scrim du drawer mobile */}
      <div
        className={`zone-scrim${drawerOpen ? ' visible' : ''}`}
        aria-hidden="true"
        onClick={() => setDrawerOpen(false)}
      />
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
  loading,
  error,
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
  loading: boolean;
  error: string | null;
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
      <div
        className={`hero-pill${stepError || error ? ' hero-pill-error' : ''}${
          loading ? ' hero-pill-loading' : ''
        }`}
      >
        <md-icon className="hero-pill-icon" aria-hidden="true">
          search
        </md-icon>
        <label className="hero-pill-label" htmlFor="addr-input-hero">
          Rechercher une adresse
        </label>
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
        {loading ? (
          <span className="hero-pill-spinner" aria-hidden="true" />
        ) : (
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
        )}
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
          aria-label={
            visible
              ? `Masquer la couche ${alea.libelle} sur la carte`
              : `Afficher la couche ${alea.libelle} sur la carte`
          }
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

/* ── Détection mobile — 900px, même breakpoint que @media (max-width:900px)
   dans zone.css (garder les deux synchronisés) ── */
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches
  );
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)');
    const onChange = () => setIsMobile(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isMobile;
}

/* ── Sidenav rétractable (navigation façon Gemini) ──
   Desktop : rail pleine largeur ↔ colonne d'icônes (collapsed).
   Mobile  : drawer hors-écran ouvert via le hamburger du stepper + scrim. */
function ZoneSidenav({
  sidenavRef,
  collapsed,
  mobile,
  hidden,
  theme,
  accent,
  settingsOpen,
  settingsMenuRef,
  themeSwitchRef,
  onToggleCollapse,
  onPickAccent,
  onResetAccent,
  onOpenSettings,
  onCloseDrawer,
  onNewDiagnostic,
}: {
  sidenavRef: RefObject<HTMLElement | null>;
  collapsed: boolean;
  mobile: boolean;
  hidden: boolean;
  theme: 'dark' | 'light';
  accent: string;
  settingsOpen: boolean;
  settingsMenuRef: RefObject<Menu | null>;
  themeSwitchRef: RefObject<MdSwitch | null>;
  onToggleCollapse: () => void;
  onPickAccent: (hex: string) => void;
  onResetAccent: () => void;
  onOpenSettings: () => void;
  onCloseDrawer: () => void;
  onNewDiagnostic: () => void;
}) {
  const navigate = useNavigate();

  const navGo = (path: string) => {
    onCloseDrawer();
    navigate(path);
  };

  return (
    <aside
      ref={sidenavRef}
      className="zone-sidenav"
      aria-label="Navigation principale"
      inert={hidden}
      aria-hidden={hidden}
    >
      <header className="sidenav-header">
        {collapsed ? (
          /* Replié : l'icône d'expansion remplace le logo (clic → déplier) */
          <md-icon-button
            className="sidenav-expand"
            aria-label="Déplier le menu"
            title="Déplier le menu"
            onClick={onToggleCollapse}
          >
            <md-icon>chevron_right</md-icon>
          </md-icon-button>
        ) : (
          <>
            <Link
              to="/"
              className="sidenav-brand"
              aria-label="Typhoon — accueil"
              onClick={onCloseDrawer}
            >
              {/* Wordmark teinté par l'accent : le SVG blanc sert de masque
                  alpha, la couleur est --accent (voir zone.css). Le lien a déjà
                  aria-label — le span est décoratif. */}
              <span className="sidenav-wordmark-img" aria-hidden="true" />
            </Link>
            <md-icon-button
              className="sidenav-collapse"
              aria-label={mobile ? 'Fermer le menu' : 'Replier le menu'}
              title={mobile ? 'Fermer le menu' : 'Replier le menu'}
              onClick={onToggleCollapse}
            >
              <md-icon>{mobile ? 'close' : 'menu_open'}</md-icon>
            </md-icon-button>
          </>
        )}
      </header>

      {collapsed ? (
        /* ── Mode replié : colonne d'icônes ── */
        <nav className="sidenav-rail" aria-label="Raccourcis">
          <md-icon-button title="Nouveau diagnostic" aria-label="Nouveau diagnostic" onClick={onNewDiagnostic}>
            <md-icon>add_circle</md-icon>
          </md-icon-button>
          <md-icon-button title="Accueil" aria-label="Accueil" onClick={() => navGo('/')}>
            <md-icon>home</md-icon>
          </md-icon-button>
          <md-icon-button title="FAQ" aria-label="FAQ" onClick={() => navGo('/faq')}>
            <md-icon>help</md-icon>
          </md-icon-button>
          <md-icon-button title="Contact" aria-label="Contact" onClick={() => navGo('/contact')}>
            <md-icon>mail</md-icon>
          </md-icon-button>
        </nav>
      ) : (
        /* ── Mode déplié : liste M3 ── */
        <md-list className="sidenav-nav">
          <md-list-item
            className="sidenav-new"
            type="button"
            onClick={onNewDiagnostic}
          >
            <md-icon slot="start">add_circle</md-icon>
            <span slot="headline">Nouveau diagnostic</span>
          </md-list-item>
          <md-list-item type="button" onClick={() => navGo('/')}>
            <md-icon slot="start">home</md-icon>
            <span slot="headline">Accueil</span>
          </md-list-item>
          <md-list-item type="button" onClick={() => navGo('/faq')}>
            <md-icon slot="start">help</md-icon>
            <span slot="headline">FAQ</span>
          </md-list-item>
          <md-list-item type="button" onClick={() => navGo('/contact')}>
            <md-icon slot="start">mail</md-icon>
            <span slot="headline">Contact</span>
          </md-list-item>
        </md-list>
      )}

      <footer className="sidenav-footer">
        <md-icon-button
          id="settings-anchor"
          className="sidenav-settings"
          aria-label="Réglages"
          title="Réglages"
          aria-expanded={settingsOpen}
          aria-haspopup="menu"
          onClick={onOpenSettings}
        >
          <md-icon>settings</md-icon>
        </md-icon-button>

        <md-menu
          ref={settingsMenuRef}
          anchor="settings-anchor"
          positioning="popover"
          open={settingsOpen}
          className="sidenav-menu"
        >
          <md-menu-item keepOpen>
            <span slot="headline">Mode sombre</span>
            <md-switch slot="end" ref={themeSwitchRef} selected={theme === 'dark'} icons>
              <md-icon slot="on-icon">dark_mode</md-icon>
              <md-icon slot="off-icon">light_mode</md-icon>
            </md-switch>
          </md-menu-item>

          <div className="sidenav-accent-block">
            <span className="sidenav-accent-title">Couleur d'accent</span>
            <div className="sidenav-accent-swatches">
              {ACCENTS.map((hex) => (
                <button
                  key={hex}
                  type="button"
                  className={`sidenav-accent-swatch${
                    accent.toLowerCase() === hex.toLowerCase() ? ' active' : ''
                  }`}
                  style={{ '--swatch': hex } as CSSProperties}
                  aria-label={`Accent ${hex}`}
                  title={hex}
                  onClick={() => onPickAccent(hex)}
                />
              ))}
            </div>
            <button type="button" className="sidenav-accent-reset" onClick={onResetAccent}>
              <md-icon>restart_alt</md-icon>
              <span>Rétablir le bleu d'origine</span>
            </button>
          </div>

          <md-menu-item type="button" onClick={() => navGo('/')}>
            <md-icon slot="start">home</md-icon>
            <span slot="headline">Retour à l'accueil</span>
          </md-menu-item>
        </md-menu>
      </footer>
    </aside>
  );
}