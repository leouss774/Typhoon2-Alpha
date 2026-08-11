// =============================================================================
//   TYPHOON ��� /zone : diagnostic g+�o-risque par adresse (Stepper Material 3)
//   +�tapes :
//     1. Adresse      ��� hero centr+� fa+�on Gemini (champ de recherche au centre)
//     2. Cartographie ��� carte OpenLayers + panneau al+�as (data viz G+�orisques)
//     3. Analyse      ��� fiche b+�timent BDNB (Synth+�se / Construction / +�nergie�Ǫ)
//     4. Jumeau BIM   ��� viewer 3D thingraph en iframe (glTF g+�n+�r+� depuis l'emprise BDNB)
//     5. Recommandations ��� plan d'adaptation du bien
//     6. Artisans       ��� professionnels associ+�s aux travaux
//     7. Rapport IA     ��� rapport narratif Mistral + export PDF
//
//   Stepper lin+�aire : les +�tapes 2-4 sont bloqu+�es tant qu'aucune adresse
//   n'a +�t+� diagnostiqu+�e ��� l'+�tape Adresse passe en +�tat d'erreur (ic+�ne
//   erreur + message) si l'on tente de les atteindre sans rapport.
// =============================================================================

import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Menu } from '@material/web/menu/menu.js';
import type { MdSwitch } from '@material/web/switch/switch.js';
import { ZoneMap } from '../components/ZoneMap';
import { ZoneAnalyse } from '../components/ZoneAnalyse';
import { ZoneBIM } from '../components/ZoneBIM';
import { ZoneRecommendations } from '../components/ZoneRecommendations';
import { ZoneArtisans } from '../components/ZoneArtisans';
import { ACCENTS, useTyphoonTheme } from '../typhoon/useTyphoonTheme';
import { useAssistantContexte } from '../assistant/AssistantContext';
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
  type RisquesPrincipaux,
} from '../zone/config';
import type { RecommendationZone } from '../jumeau/recommendations';
import {
  addConversation,
  loadConversations,
  removeConversation,
  saveConversations,
  type Conversation,
} from '../zone/conversations';
import '../styles/zone.css';

const LEGEND_RANGES = ['<20', '20���39', '40���59', '60���79', '���80'];

/* Erreur structur+�e du rapport IA ��� contrat backend /diagnostic/adresse/rapport :
   { error: <code>, detail: <message utilisateur>, cause: <cause technique> } */
interface RapportError {
  code: string; // mistral_api_key_manquante | mistral_indisponible | reseau | http_*
  status?: number;
  message: string; // message lisible
  hint?: string; // conseil actionnable (facultatif)
  cause?: string; // d+�tail technique (affich+� dans <details>)
}

const STEPS = [
  { id: 'adresse', label: 'Adresse' },
  { id: 'carto', label: 'Cartographie' },
  { id: 'analyse', label: 'Analyse' },
  { id: 'bim', label: 'Jumeau BIM' },
  { id: 'recommandations', label: 'Recommandations' },
  { id: 'artisans', label: 'Artisans' },
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

  /* Le menu r+�glages se referme de lui-m+�me (clic ext+�rieur / +�chap) ��� on
     resynchronise l'+�tat React sur l'+�v+�nement `closed` du md-menu. */
  useEffect(() => {
    const menu = settingsMenuRef.current;
    if (!menu) return;
    const onClosed = () => setSettingsOpen(false);
    menu.addEventListener('closed', onClosed);
    return () => menu.removeEventListener('closed', onClosed);
  }, []);

  /* md-switch +�met `change` (custom element) ��� on +�coute via le ref. */
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
  const [detailedRecommendationZones, setDetailedRecommendationZones] = useState<Record<string, RecommendationZone>>({});
  const [detailedRecommendationsLoading, setDetailedRecommendationsLoading] = useState(false);
  const [detailedRecommendationsError, setDetailedRecommendationsError] = useState<string | null>(null);
  const [detailedRisquesPrincipaux, setDetailedRisquesPrincipaux] = useState<RisquesPrincipaux | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations());
  const [rapport, setRapport] = useState<RapportNarratif | null>(null);
  const [rapportLoading, setRapportLoading] = useState(false);
  const [rapportError, setRapportError] = useState<RapportError | null>(null);
  /* true quand l'+�tape Rapport IA a +�t+� atteinte pendant le chargement des
     recommandations : le rapport n'est g+�n+�r+� qu'une fois celles-ci pr+�tes. */
  const [rapportWaiting, setRapportWaiting] = useState(false);
  /* Export PDF du rapport IA (jsPDF c+�t+� client) ��� vrai bouton de t+�l+�chargement. */
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportPdfError, setExportPdfError] = useState<string | null>(null);
  /* Intention -� r+�g+�n+�ration forc+�e -+ m+�moris+�e quand la relance est diff+�r+�e
     par l'attente des recommandations (sinon force serait perdu). */
  const rapportForceRef = useRef(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [visibleLayerKeys, setVisibleLayerKeys] = useState<ReadonlySet<string>>(new Set());

  /* ������ Compagnon virtuel Typhoon : synchronise le contexte du diagnostic
     affich+� +� l'+�cran (adresse, bien, zones/recommandations) pour que le
     chat r+�ponde +� propos de CE bien. Contrat : backend/app/api/routes/chat.py. */
  const { setContexte } = useAssistantContexte();
  useEffect(() => {
    if (!report) {
      setContexte(null);
      return;
    }
    const batiment = report.bdnb?.batiment;
    setContexte({
      adresse: report.adresse_normalisee,
      bien: batiment
        ? {
            type: batiment.usage_principal_bdnb_open || batiment.usage_niveau_1_txt || null,
            annee_construction: batiment.annee_construction ?? null,
          }
        : undefined,
      zones: detailedRecommendationZones,
    });
  }, [report, detailedRecommendationZones, setContexte]);
  useEffect(() => () => setContexte(null), [setContexte]);

  /* Champ de la topbar (+�tapes 2-4) et champ du hero (+�tape 1) : deux
     instances distinctes de md-outlined-text-field, chacune avec son ref. */
  const inputRef = useRef<HTMLElement & { value: string }>(null);
  const heroInputRef = useRef<HTMLInputElement>(null);
  const lastQuery = useRef('');
  const banTimeout = useRef<number | null>(null);
  const userClosedSidebar = useRef(false);
  const recommendationsRequestId = useRef(0);

  async function loadDetailedRecommendations(address: string) {
    const requestId = ++recommendationsRequestId.current;
    setDetailedRecommendationsLoading(true);
    setDetailedRecommendationsError(null);
    setDetailedRecommendationZones({});
    setDetailedRisquesPrincipaux(null);
    try {
      const fastResponse = await fetch(`${API}/diagnostic/fast`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ adresse: address, copernicus: false }),
      });
      if (!fastResponse.ok) throw new Error(`Diagnostic d+�taill+� HTTP ${fastResponse.status}`);
      const fastContract = await fastResponse.json();
      if (!fastContract?._resume) throw new Error('Contexte de recommandations absent');

      const recommendationsResponse = await fetch(`${API}/diagnostic/recommandations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fastContract._resume),
      });
      if (!recommendationsResponse.ok) throw new Error(`Recommandations HTTP ${recommendationsResponse.status}`);
      const detailedContract = await recommendationsResponse.json();
      if (requestId !== recommendationsRequestId.current) return;
      setDetailedRecommendationZones(detailedContract?.zones || {});
      setDetailedRisquesPrincipaux(detailedContract?.risques_principaux || null);
    } catch (error) {
      if (requestId !== recommendationsRequestId.current) return;
      setDetailedRecommendationsError(error instanceof Error ? error.message : 'Recommandations d+�taill+�es indisponibles');
    } finally {
      if (requestId === recommendationsRequestId.current) setDetailedRecommendationsLoading(false);
    }
  }

  /* ������ BAN autocompl+�tion ������ */
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
    setStepError(false); // l'erreur -� adresse manquante -+ se dissipe d+�s la saisie
    setDiagError(null); // l'erreur d'API se dissipe aussi d+�s la saisie
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

  /* ������ Diagnostic ������ */
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
    recommendationsRequestId.current += 1;
    setDetailedRecommendationZones({});
    setDetailedRecommendationsLoading(false);
    setDetailedRecommendationsError(null);
    setDetailedRisquesPrincipaux(null);
    setRapport(null);
    setRapportError(null);
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
      void loadDetailedRecommendations(r.adresse_normalisee || value);
      /* Historique -� R+�cent -+ (localStorage) : adresse normalis+�e ou requ+�te brute. */
      setConversations((prev) => {
        const next = addConversation(prev, r.adresse_normalisee || value);
        saveConversations(next);
        return next;
      });
      setStepError(false); // l'adresse est valid+�e ��� +�tapes suivantes d+�bloqu+�es
      setStep(1); // ��� +�tape Cartographie
      if (!userClosedSidebar.current) setSidebarOpen(true);
      setVisibleLayerKeys(
        new Set((r.aleas || []).filter((a) => a.present === true).map((a) => a.code))
      );
    } catch {
      setDiagError('Erreur r+�seau ��� backend inaccessible ?');
    } finally {
      setLoading(false);
    }
  }

  /* ������ Rapport narratif IA (Mistral) ��� POST RisqueReport ��� RapportNarratif ������ */
  async function loadRapport(force = false) {
    if (!report || (rapport && !force) || rapportLoading) return;
    setRapportLoading(true);
    setRapportError(null);
    try {
      const resp = await fetch(`${API}/diagnostic/adresse/rapport`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(report),
      });
      if (!resp.ok) {
        // Contrat backend : detail = { error, detail, cause }. On g+�re aussi
        // le cas FastAPI o+� detail est une simple cha+�ne ({"detail": "..."}).
        const err = await resp.json().catch(() => null);
        const rawDetail = err?.detail;
        const d =
          rawDetail && typeof rawDetail === 'object'
            ? rawDetail
            : rawDetail && typeof rawDetail === 'string'
              ? { detail: rawDetail }
              : err ?? {};
        setRapportError({
          code: d.error || `http_${resp.status}`,
          status: resp.status,
          message:
            d.detail ||
            (resp.status === 503
              ? 'Le rapport IA n+�cessite une cl+� Mistral c+�t+� serveur.'
              : `Le service n'a pas pu g+�n+�rer le rapport (HTTP ${resp.status}).`),
          hint: hintForRapportError(d.error, resp.status),
          cause: d.cause || undefined,
        });
        return;
      }
      setRapport((await resp.json()) as RapportNarratif);
    } catch (err) {
      // fetch() a +�chou+� : backend injoignable, CORS, DNS�Ǫ
      setRapportError({
        code: 'reseau',
        message: 'Impossible de joindre le serveur pour g+�n+�rer le rapport IA.',
        hint: 'V+�rifiez que le backend Typhoon est d+�marr+� (port 8765) puis r+�essayez.',
        cause: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setRapportLoading(false);
    }
  }

  /* Rapport IA en attente : si l'+�tape 5 a +�t+� atteinte pendant le chargement
     des recommandations d+�taill+�es, on g+�n+�re le rapport d+�s qu'elles sont
     pr+�tes (m+�me en cas d'+�chec : le rapport reste g+�n+�rable). L'intention
     -� force -+ est conserv+�e pour la relance (R+�g+�n+�rer). */
  useEffect(() => {
    if (rapportWaiting && !detailedRecommendationsLoading && step === 5 && report) {
      const force = rapportForceRef.current;
      rapportForceRef.current = false;
      setRapportWaiting(false);
      void loadRapport(force);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rapportWaiting, detailedRecommendationsLoading, step, report]);

  /* Conseil actionnable selon le code d'erreur renvoy+� par le backend. */
  function hintForRapportError(code: string | undefined, status: number): string | undefined {
    if (code === 'mistral_api_key_manquante') {
      return "Ajoutez MISTRAL_API_KEY au fichier .env du backend puis red+�marrez l'API.";
    }
    if (code === 'mistral_indisponible' || status === 502) {
      return 'Le service Mistral est momentan+�ment indisponible ou a expir+� ��� r+�essayez dans quelques instants.';
    }
    if (status === 503) {
      return 'Le service de g+�n+�ration IA n\'est pas configur+� c+�t+� serveur.';
    }
    if (status >= 500) {
      return 'Le serveur a rencontr+� une erreur interne ��� r+�essayez, ou relancez le backend si cela persiste.';
    }
    return undefined;
  }

  /* ������ Navigation du stepper (lin+�aire : impossible de sauter l'adresse) ������ */
  function goToStep(i: number) {
    if (i > 0 && !report) {
      setStepError(true); // +�tape Adresse ��� +�tat d'erreur, navigation bloqu+�e
      setDiagError(null); // le message du stepper prime sur une erreur d'API ant+�rieure
      window.setTimeout(() => heroInputRef.current?.focus(), 80);
      return;
    }
    setStepError(false);
    setStep(i);
    /* Quitter l'+�tape Rapport IA avant la fin des recommandations : on retire
       l'+�tat -� en attente -+ (sera red+�clench+� si l'on revient +� l'+�tape 5). */
    if (i !== 5) setRapportWaiting(false);
    if (i === 0) window.setTimeout(() => heroInputRef.current?.focus(), 80);
    if (i === 6 && report) void loadRapport();
  }

  /* ������ Visibilit+� des couches ������ */
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
      userClosedSidebar.current = o; // fermeture manuelle ��� true -� r+�ouverture ��� false
      return !o;
    });
  }

  /* ������ Historique -� R+�cent -+ (sidenav) ������ */
  function handleOpenConversation(address: string) {
    setDrawerOpen(false);
    void runDiagnosis(address);
  }

  function handleDeleteConversation(id: string) {
    setConversations((prev) => {
      const next = removeConversation(prev, id);
      saveConversations(next);
      return next;
    });
  }

  function setAllVisible(visible: boolean) {
    if (!report) return;
    const codes = (report.aleas || []).map((a) => a.code);
    setVisibleLayerKeys(visible ? new Set(codes) : new Set());
  }

  /* ������ D+�riv+�s du rapport ������ */
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
  /* PDF officiel G+�orisques (ERRIAL) ��� lien secondaire conserv+�. */
  const pdfUrl = report
    ? `${API}/diagnostic/adresse/rapport-pdf?lat=${report.lat}&lon=${report.lon}`
    : '#';

  /* ������ Export PDF du rapport IA (client-side, jsPDF import+� +� la demande) ������ */
  async function handleExportPdf() {
    if (!report || !rapport || exportingPdf) return;
    setExportingPdf(true);
    setExportPdfError(null);
    try {
      const { exportRapportPdf } = await import('../zone/pdf-export');
      await exportRapportPdf(report, rapport);
    } catch (err) {
      console.error('Export PDF du rapport IA +�chou+� :', err);
      setExportPdfError(
        "L'export PDF a +�chou+� dans le navigateur. R+�essayez ��� si le probl+�me persiste, utilisez le lien -� PDF officiel G+�orisques -+."
      );
    } finally {
      setExportingPdf(false);
    }
  }

  const stripText = report
    ? `${report.adresse_normalisee} -� ${report.alea_count} al+�a(s) -� 0 simul+�s`
    : 'En attente d���une adresse';

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
      {/* ===== SIDENAV r+�tractable (navigation fa+�on Gemini) ===== */}
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
        conversations={conversations}
        activeAddress={report?.adresse_normalisee ?? null}
        onOpenConversation={handleOpenConversation}
        onDeleteConversation={handleDeleteConversation}
      />

      {/* ===== COLONNE PRINCIPALE ===== */}
      <div className="zone-main">
        {/* ===== STEPPER (indicateur d'+�tapes, lin+�aire) ===== */}
        <nav className="zone-stepper" aria-label="+�tapes du diagnostic">
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

        {/* ===== +�TAPE 1 ��� ADRESSE (hero fa+�on Gemini) ===== */}
      {step === 0 && (
        <section className="zone-hero">
          <div className="hero-brand">
            <h1>Diagnostic g+�o-risque</h1>
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
                  <span className="hero-thinking-txt">Diagnostic en cours�Ǫ</span>
                </div>
              ) : (
                (stepError || diagError) && (
                  <div className="hero-error" role="alert">
                    <md-icon>error</md-icon>
                    <span>
                      {diagError ||
                        "Saisissez d'abord une adresse pour acc+�der aux +�tapes suivantes."}
                    </span>
                  </div>
                )
              )}
            </div>
            {!loading && (
              <div className="hero-hints">
                <span>ex. 14 Avenue des Palmiers 06000 Nice</span>
                <span>Entr+�e ��� pour diagnostiquer</span>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ===== +�TAPES 2���5 : topbar + sc+�ne ===== */}
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
                  aria-label="Afficher / masquer le panneau des al+�as"
                  title="Panneau des al+�as"
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
            {/* Workspace ��� toujours mont+� pour pr+�server la carte OpenLayers
                (masqu+� via [hidden] hors de l'+�tape Cartographie) */}
            <div className="zone-workspace" hidden={step !== 1}>
              {/* SIDEBAR (couches + r+�sultats) */}
              <aside className="zone-sidebar">
                {report ? (
                  <section className="zone-results">
                    <div className="addr-heading">
                      <div className="norm">{report.adresse_normalisee}</div>
                      <div className="meta">
                        GPS {report.lat.toFixed(5)}-�N, {report.lon.toFixed(5)}-�E -� Code INSEE{' '}
                        {report.code_insee} -� G+�n+�r+� le {report.date_generation}
                      </div>
                    </div>

                    <details className="legend-section" open>
                      <summary className="section-heading legend-summary">
                        <span>Bandes D03 ��� Risque</span>
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
                    </details>      <div className="score-block">
        <div className="score-row">
          <span className="score-num" style={{ color: band?.color }}>
            {maxScore ?? '���'}
          </span>
          <div className="score-meta">
            <span className="score-label">Score de risque global /100</span>
            <span className={`d03-pill ${band ? band.cls : ''}`}>
              {band ? band.label : 'Ind+�termin+�'}
            </span>
          </div>
        </div>
      </div>

                    <div className="aleas-section">
                      <div className="section-heading">
                        <span>Al+�as recens+�s ��� G+�orisques</span>
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
                            Historique arr+�t+�s CatNat{' '}
                            <span className="catnat-count">({catnat.length} arr+�t+�s)</span>
                          </span>
                          <md-icon>expand_more</md-icon>
                        </summary>
                        <md-list className="catnat-list">
                          {catnat.slice(0, 15).map((ev, i) => (
                            <md-list-item key={i}>
                              <md-icon slot="start">history</md-icon>
                              <span slot="headline">
                                {ev.libelle_risque_jo || ev.libelle || '���'}
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
                              <span slot="headline">+ {catnat.length - 15} autre(s)�Ǫ</span>
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
                          {escHtml(report.erreurs_partielles.join(' -� '))}. Les al+�as concern+�s
                          affichent -� source indisponible -+.
                        </span>
                      </div>
                    )}

                    <div className="avertissement">
                      <md-icon>info</md-icon>
                      <span>
                        <strong>��� Ce rapport n'est pas l'ERRIAL officiel.</strong> Il agr+�ge les
                        donn+�es publiques G+�orisques (BRGM / MTE). Il ne remplace pas l'+�tat des
                        Risques r+�glementaire obligatoire +� la vente/location.
                      </span>
                    </div>
                  </section>
                ) : (
                  <div className="sidebar-empty">
                    <md-icon>gps_fixed</md-icon>
                    <p>Recherchez une adresse pour afficher le diagnostic g+�o-risque.</p>
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
                  <span>-� CARTO -� -� OpenStreetMap contributors -� -� BRGM G+�orisques</span>
                </div>
                {wmsActive && <div className="wms-badge">WMS BRGM actif</div>}
              </section>
            </div>

            {/* +�TAPE 3 ��� ANALYSE BDNB (fiche b+�timent) */}
            <section className="zone-analyse" hidden={step !== 2}>
              <ZoneAnalyse report={report} />
            </section>

            {/* +�TAPE 4 ��� JUMEAU BIM (viewer 3D thingraph/bim-viewer en iframe) */}
            <section className="zone-bim" hidden={step !== 3}>
              <ZoneBIM
                report={report}
                recommendationZones={detailedRecommendationZones}
                recommendationZonesLoading={detailedRecommendationsLoading}
                recommendationZonesError={detailedRecommendationsError}
                risquesPrincipaux={detailedRisquesPrincipaux}
                visibleLayerKeys={visibleLayerKeys}
                onToggleLayer={toggleLayer}
              />
            </section>

            {/* +�TAPE 5 ��� RECOMMANDATIONS */}
            <section className="zone-recommendations" hidden={step !== 4}>
              <ZoneRecommendations
                report={report}
                zones={detailedRecommendationZones}
                loading={detailedRecommendationsLoading}
                error={detailedRecommendationsError}
              />
            </section>

            {/* +�TAPE 6 ��� ARTISANS */}
            <section className="zone-artisans-step" hidden={step !== 5}>
              <ZoneArtisans
                report={report}
                zones={detailedRecommendationZones}
                loading={detailedRecommendationsLoading}
                error={detailedRecommendationsError}
              />
            </section>

            {/* +�TAPE 7 ��� RAPPORT IA */}
            <section className="zone-report" hidden={step !== 6}>
              {!report ? (
                <div className="report-empty">
                  <md-icon>description</md-icon>
                  <h2>Aucun diagnostic</h2>
                  <p>Diagnostiquez d'abord une adresse pour g+�n+�rer le rapport d'analyse IA.</p>
                  <md-filled-button onClick={() => goToStep(0)}>
                    <md-icon slot="icon">search</md-icon> Chercher une adresse
                  </md-filled-button>
                </div>
              ) : rapportLoading ? (
                <div className="report-empty">
                  <md-icon>psychology</md-icon>
                  <h2>G+�n+�ration du rapport IA�Ǫ</h2>
                  <p>Mistral analyse les donn+�es G+�orisques de {report.adresse_normalisee}.</p>
                  <md-linear-progress indeterminate></md-linear-progress>
                </div>
              ) : rapportWaiting && !rapport ? (
                <div className="report-empty">
                  <md-icon>hourglass_top</md-icon>
                  <h2>Analyse des recommandations en cours�Ǫ</h2>
                  <p>
                    Le rapport IA sera g+�n+�r+� d+�s la fin de l'analyse d+�taill+�e
                    du bien.
                  </p>
                  <md-linear-progress indeterminate></md-linear-progress>
                </div>
              ) : rapportError ? (
                <div className="report-error" role="alert">
                  <div className="report-error-icon">
                    <md-icon>
                      {rapportError.code === 'mistral_api_key_manquante'
                        ? 'vpn_key'
                        : rapportError.code === 'reseau'
                          ? 'wifi_off'
                          : 'cloud_off'}
                    </md-icon>
                  </div>
                  <h2>Rapport indisponible</h2>
                  <p className="report-error-msg">{rapportError.message}</p>
                  {rapportError.hint ? (
                    <p className="report-error-hint">
                      <md-icon>lightbulb</md-icon>
                      <span>{rapportError.hint}</span>
                    </p>
                  ) : null}
                  {rapportError.cause ? (
                    <details className="report-error-details">
                      <summary>
                        <md-icon>bug_report</md-icon> D+�tail technique
                      </summary>
                      <code>
                        [{rapportError.code}
                        {rapportError.status ? ` -� HTTP ${rapportError.status}` : ''}] {rapportError.cause}
                      </code>
                    </details>
                  ) : null}
                  <div className="report-error-actions">
                    <md-filled-button onClick={() => void loadRapport()}>
                      <md-icon slot="icon">refresh</md-icon> R+�essayer
                    </md-filled-button>
                    <md-text-button onClick={() => goToStep(0)}>
                      <md-icon slot="icon">search</md-icon> Nouvelle adresse
                    </md-text-button>
                  </div>
                </div>
              ) : rapport ? (
                <>
                  <header className="report-header">
                    <div className="report-title">
                      <h2>Rapport d'analyse IA</h2>
                      <p className="report-meta">
                        {report.adresse_normalisee} -� Code INSEE {report.code_insee} -�{' '}
                        {report.date_generation}
                      </p>
                    </div>
                    <div className="report-actions">
                      <md-text-button
                        className="report-regenerate"
                        aria-label="R+�g+�n+�rer le rapport IA (nouvel appel Mistral, sans cache)"
                        title="R+�g+�n+�rer avec le prompt actuel"
                        onClick={() => void loadRapport(true)}
                      >
                        <md-icon slot="icon">refresh</md-icon>
                        R+�g+�n+�rer
                      </md-text-button>
                      <md-elevated-button
                        className="pdf-btn report-export"
                        disabled={exportingPdf}
                        aria-busy={exportingPdf || undefined}
                        onClick={handleExportPdf}
                      >
                        <md-icon slot="icon">
                          {exportingPdf ? 'hourglass_top' : 'picture_as_pdf'}
                        </md-icon>
                        {exportingPdf ? 'G+�n+�ration du PDF�Ǫ' : 'Exporter en PDF'}
                      </md-elevated-button>
                      <md-text-button
                        className="report-official"
                        href={pdfUrl}
                        target="_blank"
                        rel="noopener"
                        title="PDF officiel G+�orisques (ERRIAL) pour ces coordonn+�es"
                      >
                        PDF officiel G+�orisques
                      </md-text-button>
                    </div>
                    {exportPdfError && (
                      <p className="report-export-error" role="alert">
                        <md-icon>error</md-icon>
                        <span>{exportPdfError}</span>
                      </p>
                    )}
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
                      <h3>Synth+�se finale</h3>
                      <p>{rapport.synthese_finale}</p>
                    </div>
                  </aside>

                  {rapport.obligations_reglementaires &&
                    rapport.obligations_reglementaires.length > 0 && (
                      <section className="report-obligations">
                        <h3>Obligations r+�glementaires</h3>
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
                        "Ce rapport est g+�n+�r+� automatiquement par IA +� partir des donn+�es publiques G+�orisques normalis+�es. Il ne remplace pas l'ERRIAL ni l'avis d'un expert."}
                    </span>
                  </p>
                </>
              ) : (
                <div className="report-empty">
                  <md-icon>description</md-icon>
                  <h2>Pr+�t +� g+�n+�rer</h2>
                  <p>
                    G+�n+�rez le rapport narratif IA +� partir du diagnostic{' '}
                    {report.adresse_normalisee}.
                  </p>
                  <md-filled-button onClick={() => void loadRapport()}>
                    <md-icon slot="icon">auto_awesome</md-icon> G+�n+�rer le rapport
                  </md-filled-button>
                </div>
              )}
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

/* ������ Champ d'adresse de l'+�tape 1 (hero) ��� input natif simple ������
   Un <input type="search"> standard styl+� en pilule : aucune d+�pendance au
   champ Material (md-outlined-text-field), donc aucune largeur intrins+�que
   qui pourrait d+�passer la page. Ref, +�couteurs et dropdown propres. */
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
  /* +�couteurs attach+�s au montage ; la valeur initiale restaure la derni+�re
     requ+�te saisie (lastQuery) lorsque le champ est (r+�)mont+�. */
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
          placeholder="Rechercher une adresse en France�Ǫ"
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

/* ������ Champ d'adresse r+�utilisable (topbar) ������
   Chaque instance poss+�de son propre md-outlined-text-field (ref distincte),
   ses +�couteurs (autocompl+�tion BAN, Entr+�e) et son dropdown de suggestions. */
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
  /* +�couteurs attach+�s au montage : la valeur initiale restaure la derni+�re
     requ+�te saisie (lastQuery) lorsque le champ est (r+�)mont+�. */
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
        placeholder="Rechercher une adresse en France�Ǫ"
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

/* ������ Suggestions BAN (dropdown) ������ */
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

/* ������ Carte d'al+�a ������ */
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
                {addrPresent ? 'CONCERN+�' : 'PAS DE RISQUE'}
              </span>
              <span className={`status-chip ${communePresent ? 'chip-mid' : 'chip-off'}`}>
                <md-icon>account_balance</md-icon>
                {communePresent ? 'EXISTANT' : 'NON CONCERN+�'}
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

/* ������ D+�tection mobile ��� 900px, m+�me breakpoint que @media (max-width:900px)
   dans zone.css (garder les deux synchronis+�s) ������ */
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

/* ������ Sidenav r+�tractable (navigation fa+�on Gemini) ������
   Desktop : rail pleine largeur ��� colonne d'ic+�nes (collapsed).
   Mobile  : drawer hors-+�cran ouvert via le hamburger du stepper + scrim. */
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
  conversations,
  activeAddress,
  onOpenConversation,
  onDeleteConversation,
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
  conversations: Conversation[];
  activeAddress: string | null;
  onOpenConversation: (address: string) => void;
  onDeleteConversation: (id: string) => void;
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
          /* Repli+� : l'ic+�ne d'expansion remplace le logo (clic ��� d+�plier) */
          <md-icon-button
            className="sidenav-expand"
            aria-label="D+�plier le menu"
            title="D+�plier le menu"
            onClick={onToggleCollapse}
          >
            <md-icon>chevron_right</md-icon>
          </md-icon-button>
        ) : (
          <>
            <Link
              to="/"
              className="sidenav-brand"
              aria-label="Typhoon ��� accueil"
              onClick={onCloseDrawer}
            >
              {/* Wordmark teint+� par l'accent : le SVG blanc sert de masque
                  alpha, la couleur est --accent (voir zone.css). Le lien a d+�j+�
                  aria-label ��� le span est d+�coratif. */}
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
        /* ������ Mode repli+� : colonne d'ic+�nes ������ */
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
        /* ������ Mode d+�pli+� : liste M3 + historique -� R+�cent -+ ������ */
        <div className="sidenav-body">
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

          <ConversationHistory
            conversations={conversations}
            activeAddress={activeAddress}
            onOpen={onOpenConversation}
            onDelete={onDeleteConversation}
          />
        </div>
      )}

      <footer className="sidenav-footer">
        <md-icon-button
          id="settings-anchor"
          className="sidenav-settings"
          aria-label="R+�glages"
          title="R+�glages"
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
              <span>R+�tablir le bleu d'origine</span>
            </button>
          </div>

          <md-menu-item type="button" onClick={() => navGo('/')}>
            <md-icon slot="start">home</md-icon>
            <span slot="headline">Retour +� l'accueil</span>
          </md-menu-item>
        </md-menu>
      </footer>
    </aside>
  );
}

/* ������ Historique -� R+�cent -+ de la sidenav (fa+�on Gemini) ������
   Section repliable : liste des adresses diagnostiqu+�es (localStorage),
   clic ��� relance le diagnostic, survol ��� bouton de suppression. */
function ConversationHistory({
  conversations,
  activeAddress,
  onOpen,
  onDelete,
}: {
  conversations: Conversation[];
  activeAddress: string | null;
  onOpen: (address: string) => void;
  onDelete: (id: string) => void;
}) {
  const [open, setOpen] = useState(true);

  if (conversations.length === 0) {
    return (
      <div className="sidenav-recent-empty">
        <md-icon>history</md-icon>
        <span>Pas encore de diagnostic</span>
      </div>
    );
  }

  return (
    <details
      className="sidenav-recent"
      open={open}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="sidenav-recent-header" aria-label="Historique des adresses diagnostiqu+�es">
        <span className="sidenav-recent-title">R+�cent</span>
        <md-icon>expand_more</md-icon>
      </summary>
      <div className="sidenav-recent-list">
        {conversations.map((c) => {
          const active = activeAddress !== null && c.address === activeAddress;
          return (
            <div
              className={`sidenav-recent-item${active ? ' active' : ''}`}
              key={c.id}
            >
              <button
                type="button"
                className="sidenav-recent-btn"
                title={c.address}
                onClick={() => onOpen(c.address)}
              >
                <md-icon>history</md-icon>
                <span className="sidenav-recent-label">{c.address}</span>
              </button>
              <md-icon-button
                className="sidenav-recent-del"
                aria-label={`Supprimer ${c.address} de l'historique`}
                title="Supprimer de l'historique"
                onClick={() => onDelete(c.id)}
              >
                <md-icon>close</md-icon>
              </md-icon-button>
            </div>
          );
        })}
      </div>
    </details>
  );
}
