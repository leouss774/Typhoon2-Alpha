// =============================================================================
//   TYPHOON — /usine : pipeline d'analyse de plan d'usine (Stepper Material 3)
//   Étapes :
//     1. Plan         — import d'un plan (image → Mistral Vision, JSON/GeoJSON)
//     2. Zones        — revue & édition des zones/équipements détectés (+ vue 2D)
//     3. Analyse      — risk engine par zone et équipement (R = √(F × V))
//     4. Jumeau BIM   — jumeau 3D three.js coloré par risque
//     5. Recommandations — plan d'adaptation (type de zone × niveau)
//     6. Rapport      — rapport narratif client-side + export PDF (jsPDF)
//
//   Stepper linéaire : les étapes 2-6 sont bloquées tant qu'aucun plan n'a
//   été importé (l'étape Plan passe en état d'erreur si l'on tente de les
//   atteindre). La navigation vers Analyse / BIM / Reco / Rapport relance
//   automatiquement l'analyse si elle n'a pas encore été calculée.
// =============================================================================

import { useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Menu } from '@material/web/menu/menu.js';
import type { MdSwitch } from '@material/web/switch/switch.js';
import { ACCENTS, useTyphoonTheme } from '../typhoon/useTyphoonTheme';
import { useAssistantContexte } from '../assistant/AssistantContext';
import { UsinePlanImport } from '../components/UsinePlanImport';
import { UsineAdresseField } from '../components/UsineAdresseField';
import { UsineZones } from '../components/UsineZones';
import { UsineAnalyse } from '../components/UsineAnalyse';
import { UsineBIM } from '../components/UsineBIM';
import { UsineRecommendations } from '../components/UsineRecommendations';
import { UsineRapport } from '../components/UsineRapport';
import { computeUsineRisk } from '../usine/api';
import type { AnalyseUsine, PlanUsine } from '../usine/types';
import '../styles/zone.css';
import '../styles/usine.css';

const STEPS = [
  { id: 'plan', label: 'Plan' },
  { id: 'zones', label: 'Zones & équipements' },
  { id: 'analyse', label: 'Analyse' },
  { id: 'bim', label: 'Jumeau BIM' },
  { id: 'recommandations', label: 'Recommandations' },
  { id: 'rapport', label: 'Rapport' },
] as const;

export function Usine() {
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

  /* Le menu réglages se referme de lui-même → resynchroniser React. */
  useEffect(() => {
    const menu = settingsMenuRef.current;
    if (!menu) return;
    const onClosed = () => setSettingsOpen(false);
    menu.addEventListener('closed', onClosed);
    return () => menu.removeEventListener('closed', onClosed);
  }, []);

  /* md-switch émet `change` (custom element) → écoute via le ref. */
  useEffect(() => {
    const sw = themeSwitchRef.current;
    if (!sw) return;
    const onChange = () => toggleTheme();
    sw.addEventListener('change', onChange);
    return () => sw.removeEventListener('change', onChange);
  }, [toggleTheme]);

  const [step, setStep] = useState(0);
  const [stepError, setStepError] = useState(false);
  const [plan, setPlan] = useState<PlanUsine | null>(null);
  const [planImage, setPlanImage] = useState<string | null>(null);
  const [adresse, setAdresse] = useState<string | null>(null);
  const [analyse, setAnalyse] = useState<AnalyseUsine | null>(null);
  const [analyseLoading, setAnalyseLoading] = useState(false);
  const [analyseError, setAnalyseError] = useState<string | null>(null);

  /* Compagnon virtuel Typhoon : contexte synchronisé sur l'usine affichée
     (score global + zones) pour que le chat réponde à propos de CE site. */
  const { setContexte } = useAssistantContexte();
  useEffect(() => {
    if (!analyse) {
      setContexte(null);
      return;
    }
    const zones: Record<string, unknown> = {};
    for (const z of analyse.zones) zones[z.id] = { risque: z.risque, niveau: z.niveau };
    setContexte({
      adresse: adresse || analyse.nom_usine,
      score_global: analyse.score_global,
      zones,
    });
  }, [analyse, adresse, setContexte]);
  useEffect(() => () => setContexte(null), [setContexte]);

  /* ── Étape 1 → 2 : plan importé ── */
  function handlePlanReady(nextPlan: PlanUsine, image: string | null) {
    setPlan(nextPlan);
    setPlanImage(image);
    setAnalyse(null);
    setAnalyseError(null);
    setStepError(false);
    setStep(1);
  }

  function handleUseDemo(demo: PlanUsine) {
    handlePlanReady(demo, null);
  }

  /* ── Étape 3 : risk engine ── */
  async function launchAnalyse() {
    if (!plan || analyseLoading) return;
    setAnalyseLoading(true);
    setAnalyseError(null);
    try {
      const result = await computeUsineRisk(plan, adresse || undefined);
      setAnalyse(result);
    } catch (err) {
      setAnalyseError(err instanceof Error ? err.message : String(err));
    } finally {
      setAnalyseLoading(false);
    }
  }

  /* ── Navigation du stepper (linéaire : impossible de sauter le plan) ── */
  function goToStep(i: number) {
    if (i > 0 && !plan) {
      setStepError(true);
      window.setTimeout(() => document.getElementById('usine-dropzone')?.focus(), 80);
      return;
    }
    setStepError(false);
    setStep(i);
    /* Analyse / BIM / Reco / Rapport sans analyse : la lancer automatiquement. */
    if (i >= 2 && plan && !analyse && !analyseLoading && !analyseError) {
      void launchAnalyse();
    }
  }

  function resetAll() {
    setPlan(null);
    setPlanImage(null);
    setAdresse(null);
    setAnalyse(null);
    setAnalyseError(null);
    setAnalyseLoading(false);
    setStepError(false);
    setDrawerOpen(false);
    setStep(0);
  }

  return (
    <main
      className={`zone-app usine-app${theme === 'light' ? ' theme-light' : ''}${
        navCollapsed && !isMobile ? ' nav-collapsed' : ''
      }${drawerOpen ? ' drawer-open' : ''}`}
      style={{ '--accent': accent } as CSSProperties}
    >
      {/* ===== SIDENAV rétractable (navigation façon Gemini) ===== */}
      <UsineSidenav
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
        onNewPlan={resetAll}
        planActive={!!plan}
      />

      {/* ===== COLONNE PRINCIPALE ===== */}
      <div className="zone-main">
        {/* ===== STEPPER (indicateur d'étapes, linéaire) ===== */}
        <nav className="zone-stepper" aria-label="Étapes de l'analyse du plan d'usine">
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

        {/* ===== ÉTAPE 1 — IMPORT DU PLAN (hero façon Gemini) ===== */}
        {step === 0 && (
          <section className="zone-hero">
            <div className="hero-brand">
              <h1 className="usine-hero-title">Analyse de plan d'usine</h1>
              <p className="usine-hero-sub">
                Importez un plan pour détecter les zones et équipements, puis mesurer le risque
                de chaque zone et de chaque équipement.
              </p>
            </div>
            {stepError && (
              <div className="hero-error" role="alert">
                <md-icon>error</md-icon>
                <span>Importez d'abord un plan pour accéder aux étapes suivantes.</span>
              </div>
            )}
            <UsinePlanImport initialImage={planImage} onReady={handlePlanReady} onUseDemo={handleUseDemo} />

            <div className="usine-adresse-block">
              <UsineAdresseField
                value={adresse}
                onChange={(next) => {
                  setAdresse(next);
                  /* L'adresse change le facteur F (Géorisques) → relancer. */
                  if (analyse) {
                    setAnalyse(null);
                    setAnalyseError(null);
                  }
                }}
              />
            </div>
          </section>
        )}

        {/* ===== ÉTAPES 2-6 : topbar + scène ===== */}
        {step >= 1 && (
          <>
            <header className="zone-topbar">
              <div className="topbar-main">
                <div className="topbar-search">
                  <md-icon className="usine-topbar-icon" aria-hidden="true">
                    factory
                  </md-icon>
                  <div className="usine-topbar-site">
                    <strong>{plan?.nom_usine || 'Site industriel'}</strong>
                    <span>
                      {plan ? `${plan.zones.length} zones · ${plan.equipements.length} équipements` : ''}
                      {adresse ? ` · ${adresse}` : ''}
                    </span>
                  </div>
                </div>
                <div className="topbar-actions">
                  <md-text-button
                    className="usine-topbar-reset"
                    aria-label="Importer un nouveau plan"
                    onClick={resetAll}
                  >
                    <md-icon slot="icon">upload_file</md-icon>
                    Nouveau plan
                  </md-text-button>
                </div>
              </div>
            </header>

            <div className="zone-stage flat">
              {/* ÉTAPE 2 — ZONES & ÉQUIPEMENTS */}
              <section className="usine-zones-step" hidden={step !== 1}>
                {plan && (
                  <UsineZones
                    plan={plan}
                    onChange={(next) => {
                      setPlan(next);
                      setAnalyse(null);
                      setAnalyseError(null);
                    }}
                  />
                )}
                <div className="usine-step-actions">
                  <md-filled-button
                    disabled={!plan || plan.zones.length === 0 || analyseLoading}
                    onClick={() => {
                      setStep(2);
                      void launchAnalyse();
                    }}
                  >
                    <md-icon slot="icon">{analyseLoading ? 'progress_activity' : 'play_arrow'}</md-icon>
                    {analyseLoading ? 'Analyse en cours…' : 'Lancer l\u0027analyse de risque'}
                  </md-filled-button>
                </div>
              </section>

              {/* ÉTAPE 3 — ANALYSE (risk engine) */}
              <section className="usine-analyse-step" hidden={step !== 2}>
                <UsineAnalyse
                  analyse={analyse}
                  loading={analyseLoading}
                  error={analyseError}
                  onRelance={() => void launchAnalyse()}
                  onGoBim={() => setStep(3)}
                  planImage={planImage}
                />
              </section>

              {/* ÉTAPE 4 — JUMEAU BIM (three.js / repli 2D) */}
              <section className="usine-bim-step" hidden={step !== 3}>
                <UsineBIM
                  zones={analyse?.zones || []}
                  equipements={analyse?.equipements || []}
                  nomUsine={analyse?.nom_usine || plan?.nom_usine}
                  scoreGlobal={analyse?.score_global ?? null}
                  planImage={planImage}
                />
              </section>

              {/* ÉTAPE 5 — RECOMMANDATIONS */}
              <section className="usine-reco-step" hidden={step !== 4}>
                <UsineRecommendations analyse={analyse} />
              </section>

              {/* ÉTAPE 6 — RAPPORT */}
              <section className="usine-report-step" hidden={step !== 5}>
                <UsineRapport analyse={analyse} />
              </section>
            </div>
          </>
        )}
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

/* ─────────── Sidenav rétractable (navigation façon Gemini) ─────────── */
function UsineSidenav({
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
  onNewPlan,
  planActive,
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
  onNewPlan: () => void;
  planActive: boolean;
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
        <nav className="sidenav-rail" aria-label="Raccourcis">
          <md-icon-button title="Nouveau plan" aria-label="Nouveau plan" onClick={onNewPlan}>
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
        <div className="sidenav-body">
          <md-list className="sidenav-nav">
            <md-list-item className="sidenav-new" type="button" onClick={onNewPlan}>
              <md-icon slot="start">add_circle</md-icon>
              <span slot="headline">Nouveau plan</span>
            </md-list-item>
            <md-list-item type="button" onClick={() => navGo('/')}>
              <md-icon slot="start">home</md-icon>
              <span slot="headline">Accueil</span>
            </md-list-item>
            <md-list-item type="button" onClick={() => navGo('/zone')}>
              <md-icon slot="start">location_searching</md-icon>
              <span slot="headline">Diagnostic /zone</span>
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

          {!planActive && (
            <div className="sidenav-recent-empty">
              <md-icon>factory</md-icon>
              <span>Aucun plan analysé pour le moment</span>
            </div>
          )}
        </div>
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

/* ─────────── Détection mobile (900px, même breakpoint que zone.css) ─────────── */
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
