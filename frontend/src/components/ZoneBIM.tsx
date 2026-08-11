// =============================================================================
//   TYPHOON — /zone : étape 4 « Jumeau BIM » — visualisation 3D du bâtiment
//   Ouvre le viewer thingraph/bim-viewer (clone local, build statique servi
//   par Vite sous /bim-viewer/) dans une iframe, pointé sur le .glb généré
//   par le backend (GET /diagnostic/adresse/gltf — emprise BDNB extrudée).
//
//   Flux : report.adresse_saisie → modelUrl (backend 8765)
//          → iframe /bim-viewer/projects/remote?model=<url encodée>
//   Le viewer charge le projet synthétique « remote » via le query param
//   `model` (patch local du clone) — aucune dépendance à son API service.
//
//   Simulations : après chargement, on envoie au viewer le rapport
//   (aleas[*].niveau D03 + données BDNB) par postMessage `typhoon:sim` —
//   l'intensité des simulations (inondation / feu / séisme) suit donc les
//   niveaux réels calculés par le backend, sans inventer de donnée.
// =============================================================================

import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { RisqueReport, RisquesPrincipaux } from '../zone/config';
import { API, ALEA_ICONS, ALEA_ICON_FALLBACK, WMS_LAYER_MAP, WFS_LAYER_MAP } from '../zone/config';
import { ComprendreRisques } from './ComprendreRisques';
import type { RecommendationZone } from '../jumeau/recommendations';
import type { AdapterResult } from '../zone/diagnosticAdapter';
import {
  SIMULABLE_ALEAS,
  runSimulationToEnd,
  type SimulationStatus,
} from '../zone3d/simulation';
import type { CesiumSimulation } from '../zone3d/CesiumViewer';

/* Chargé à la demande (React.lazy) : le bundle Cesium (~10 Mo) n'est
   téléchargé qu'au premier clic sur l'onglet « Vue terrain 3D », et
   three+cannon-es seulement à l'ouverture de la « Simulation catastrophe ». */
const CesiumViewer = lazy(() => import('../zone3d/CesiumViewer'));
const DisasterView = lazy(() => import('../zone3d/DisasterView'));

const SIM_MESSAGE_TYPE = 'typhoon:sim';

export function ZoneBIM({
  report,
  adaptedDiagnostic = null,
  recommendationZones = {},
  recommendationZonesLoading = false,
  recommendationZonesError = null,
  risquesPrincipaux = null,
  visibleLayerKeys,
  onToggleLayer,
}: {
  report: RisqueReport | null;
  /* Contrat adapté (geometry + zones) du diagnostic — consommé par le
     composant disaster-view (Three.js/cannon-es, troisième toggle de cette
     étape) : geometry → construction du bâtiment, zones → vue risque. */
  adaptedDiagnostic?: AdapterResult | null;
  recommendationZones?: Record<string, RecommendationZone>;
  recommendationZonesLoading?: boolean;
  recommendationZonesError?: string | null;
  risquesPrincipaux?: RisquesPrincipaux | null;
  visibleLayerKeys: ReadonlySet<string>;
  onToggleLayer: (code: string) => void;
}) {
  const [view, setView] = useState<'bim' | 'terrain' | 'disaster'>('bim');
  const [loaded, setLoaded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  /* Simulation CZML (Sprint 2) : alea lancé, statut du job, URL du CZML prêt. */
  const [sim, setSim] = useState<{
    code: string;
    status: SimulationStatus;
    czmlUrl?: string;
    error?: string;
    label?: string;
  } | null>(null);
  const simAbortRef = useRef<AbortController | null>(null);

  /* Outil interactif « placer une source » : l'utilisateur clique un point
     du globe (Vue terrain) et l'inondation part de ce point (priority flood
     sur le relief RGE ALTI), pilotée par un curseur d'intensité. */
  const [sourceMode, setSourceMode] = useState(false);
  const [source, setSource] = useState<{ lat: number; lon: number } | null>(null);
  const [intensite, setIntensite] = useState(0.7);
  const intensiteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* Nouveau diagnostic ou rechargement manuel → on réaffiche le voile de
     chargement le temps que l'iframe remonte, et on coupe toute simulation
     en cours (les coordonnées du rapport changent). */
  /* Annule tout timer d'intensité en attente (sinon un relaunch débouncé
     tirerait avec l'ancienne source après nettoyage/remplacement). */
  const clearIntensiteTimer = () => {
    if (intensiteTimerRef.current) {
      clearTimeout(intensiteTimerRef.current);
      intensiteTimerRef.current = null;
    }
  };

  useEffect(() => {
    setLoaded(false);
    setSim(null);
    simAbortRef.current?.abort();
    setSource(null);
    setSourceMode(false);
    clearIntensiteTimer();
    return clearIntensiteTimer;
  }, [report?.adresse_saisie, attempt]);

  /* Envoie le rapport au viewer dès que l'iframe est prête (et à chaque
     rechargement) : les simulations dérivent leurs niveaux de `aleas`. */
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!loaded || !report || !iframe || !iframe.contentWindow) return;
    iframe.contentWindow.postMessage(
      {
        type: SIM_MESSAGE_TYPE,
        payload: {
          source: 'rapport',
          aleas: report.aleas,
          batiment: report.bdnb?.batiment ?? null,
        },
      },
      '*'
    );
  }, [loaded, report, attempt]);

  if (!report) {
    return (
      <div className="analyse-empty">
        <md-icon>view_in_ar</md-icon>
        <h2>Jumeau 3D indisponible</h2>
        <p>Diagnostiquez d'abord une adresse pour générer le modèle 3D du bâtiment.</p>
      </div>
    );
  }

  const batiment = report.bdnb?.batiment || null;
  // `_r` : cache-buster — l'endpoint répond Cache-Control max-age=3600, sans
  // lui le bouton « Recharger » resservirait le .glb du cache navigateur.
  const modelUrl = `${API}/diagnostic/adresse/gltf?q=${encodeURIComponent(
    report.adresse_saisie
  )}&_r=${attempt}`;
  const iframeSrc = `/bim-viewer/projects/remote?model=${encodeURIComponent(modelUrl)}`;
  const iframeKey = `${attempt}-${report.adresse_saisie}`;

  /* Aléas disposant d'une couche WMS/WFS → toggles de la « Vue terrain 3D ». */
  const terrainAleas = (report.aleas || []).filter(
    (a) => WMS_LAYER_MAP[a.code] || WFS_LAYER_MAP[a.code]
  );

  /* Aléas simulables présents dans le rapport (à l'adresse OU à la commune,
     ex. inondation zonée TRI → present_commune) → boutons de la barre de sim. */
  const simulableAleas = (report.aleas || []).filter(
    (a) => SIMULABLE_ALEAS[a.code] && (a.present === true || a.present_commune === true)
  );

  const launchSimulation = async (
    code: string,
    overrides?: { sourceLat: number; sourceLon: number; intensite: number }
  ) => {
    simAbortRef.current?.abort();
    const ac = new AbortController();
    simAbortRef.current = ac;
    const isSource = Boolean(overrides);
    setSim({ code, status: 'queued', label: isSource ? 'Source manuelle' : undefined });

    try {
      const alea = (report.aleas || []).find((a) => a.code === code);
      const status = await runSimulationToEnd(
        code,
        {
          lat: overrides?.sourceLat ?? report.lat,
          lon: overrides?.sourceLon ?? report.lon,
          codeInsee: report.code_insee,
          niveau: alea?.niveau ?? null,
          sourceLat: overrides?.sourceLat,
          sourceLon: overrides?.sourceLon,
          intensite: overrides?.intensite,
        },
        ac.signal,
        (s) => setSim((prev) => (prev && prev.code === code ? { ...prev, status: s } : prev))
      );
      if (status.status === 'ready' && status.czml_url) {
        setSim({ code, status: 'ready', czmlUrl: `${API}${status.czml_url}`, label: isSource ? 'Source manuelle' : undefined });
      } else if (status.status === 'error') {
        setSim({ code, status: 'error', error: status.error || 'Simulation en échec.' });
      }
    } catch (err) {
      if (ac.signal.aborted) return; // remplacée / onglet quitté — silencieux
      setSim({ code, status: 'error', error: String(err) });
    }
  };

  const stopSimulation = () => {
    simAbortRef.current?.abort();
    setSim(null);
  };

  /* Point cliqué sur le globe → marqueur + lancement immédiat de
     l'inondation depuis ce point, à l'intensité courante. */
  const onSourcePicked = (srcLat: number, srcLon: number) => {
    const picked = { lat: srcLat, lon: srcLon };
    setSource(picked);
    setSourceMode(false);
    clearIntensiteTimer(); // un relaunch débouncé en attente tirerait l'ancien point
    void launchSimulation('inondation', {
      sourceLat: srcLat,
      sourceLon: srcLon,
      intensite,
    });
  };

  /* Curseur d'intensité : ré-lance la simulation depuis la même source,
     débouncé (l'utilisateur voit la crue réagir). */
  const onIntensiteChange = (value: number) => {
    setIntensite(value);
    if (!source) return;
    clearIntensiteTimer();
    intensiteTimerRef.current = setTimeout(() => {
      void launchSimulation('inondation', {
        sourceLat: source.lat,
        sourceLon: source.lon,
        intensite: value,
      });
    }, 450);
  };

  const clearSource = () => {
    setSource(null);
    setSourceMode(false);
    clearIntensiteTimer();
    stopSimulation();
  };

  /* CZML prêt → à passer au globe. Objet stable (pas de nouvelle référence à
     chaque render) : l'effet de CesiumViewer dépend des primitives code/url,
     donc une référence neuve ne relancerait pas le chargement — on garde
     quand même un objet constant pour éviter toute surprise. */
  const simForGlobe: CesiumSimulation | null =
    sim?.status === 'ready' && sim.czmlUrl ? { code: sim.code, czmlUrl: sim.czmlUrl } : null;

  return (
    <div className="bim-wrap">
      <header className="bim-header">
        <div className="bim-title">
          <h2>Jumeau numérique 3D</h2>
          <p className="bim-meta">
            {report.adresse_normalisee} · modèle glTF généré depuis l'emprise
            BDNB (footprint → extrusion)
          </p>
        </div>
        <div className="bim-actions">
          <ComprendreRisques
            zones={recommendationZones}
            loading={recommendationZonesLoading}
            error={recommendationZonesError}
            risquesPrincipaux={risquesPrincipaux}
          />
          <md-filled-button
            className="bim-action"
            aria-label="Recharger le modèle 3D"
            onClick={() => setAttempt((a) => a + 1)}
          >
            <md-icon slot="icon">refresh</md-icon>
            Recharger
          </md-filled-button>
          <md-elevated-button
            className="bim-action"
            aria-label="Ouvrir le modèle 3D en plein écran"
            href={iframeSrc}
            target="_blank"
            rel="noopener"
          >
            <md-icon slot="icon">open_in_new</md-icon>
            Plein écran
          </md-elevated-button>
        </div>
      </header>

      {batiment && (
        <div className="bim-chips">
          <Chip icon="height" value={fmt(batiment.hauteur_mean, ' m')} label="Hauteur" />
          <Chip icon="stairs" value={fmtNum(batiment.nb_niveau)} label="Niveaux" />
          <Chip
            icon="square_foot"
            value={fmtNum(batiment.surface_emprise_sol, 0) ? `${fmtNum(batiment.surface_emprise_sol, 0)} m²` : null}
            label="Emprise au sol"
          />
          <Chip icon="bricks" value={batiment.mat_mur_txt} label="Murs" />
          <Chip icon="roofing" value={batiment.mat_toit_txt} label="Toiture" />
          <Chip
            icon="door_front"
            value={fmtNum(batiment.nb_log) ? `${fmtNum(batiment.nb_log)}` : null}
            label="Logements"
          />
        </div>
      )}

      {/* Onglets : Jumeau 3D (three.js) ↔ Vue terrain 3D (CesiumJS) */}
      <div className="bim-view-tabs" role="tablist" aria-label="Mode de visualisation 3D">
        <button
          type="button"
          role="tab"
          aria-selected={view === 'bim'}
          className={`bim-view-tab${view === 'bim' ? ' active' : ''}`}
          onClick={() => {
            /* Retour sur le Jumeau 3D : l'iframe a été démontée pendant la
               Vue terrain — on réaffiche le voile et on réenvoie le rapport
               (typhoon:sim) au nouveau viewer une fois rechargé. */
            setView('bim');
            setLoaded(false);
          }}
        >
          <md-icon>view_in_ar</md-icon>
          <span>Jumeau 3D</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === 'terrain'}
          className={`bim-view-tab${view === 'terrain' ? ' active' : ''}`}
          onClick={() => setView('terrain')}
        >
          <md-icon>public</md-icon>
          <span>Vue terrain 3D</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === 'disaster'}
          className={`bim-view-tab${view === 'disaster' ? ' active' : ''}`}
          onClick={() => setView('disaster')}
        >
          <md-icon>crisis_alert</md-icon>
          <span>Simulation catastrophe</span>
        </button>
      </div>

      {view === 'bim' ? (
        <div className="bim-frame-wrap">
          {!loaded && (
            <div className="bim-loading" role="status" aria-live="polite">
              <md-icon>view_in_ar</md-icon>
              <span>Chargement du jumeau 3D…</span>
              <md-linear-progress indeterminate />
            </div>
          )}
          <iframe
            ref={iframeRef}
            key={iframeKey}
            className="bim-frame"
            src={iframeSrc}
            title="Jumeau numérique 3D du bâtiment — thingraph/bim-viewer"
            allow="webgl; xr-spatial-tracking"
            loading="eager"
            onLoad={() => setLoaded(true)}
          />
        </div>
      ) : view === 'disaster' ? (
        adaptedDiagnostic ? (
          <Suspense
            fallback={
              <div className="bim-loading cesium-suspense" role="status" aria-live="polite">
                <md-icon>crisis_alert</md-icon>
                <span>Chargement de la simulation catastrophe…</span>
                <md-linear-progress indeterminate />
              </div>
            }
          >
            <DisasterView adaptedDiagnostic={adaptedDiagnostic} />
          </Suspense>
        ) : (
          <div className="analyse-empty">
            <md-icon>crisis_alert</md-icon>
            <h2>Simulation indisponible</h2>
            <p>Diagnostiquez d'abord une adresse pour lancer une simulation catastrophe.</p>
          </div>
        )
      ) : (
        <div className="cesium-panel">
          {terrainAleas.length > 0 && (
            <div className="cesium-layerbar" role="group" aria-label="Couches de risque sur le globe">
              {terrainAleas.map((a) => {
                const visible = visibleLayerKeys.has(a.code);
                return (
                  <button
                    key={a.code}
                    type="button"
                    className={`cesium-layer-chip${visible ? ' on' : ''}`}
                    aria-pressed={visible}
                    title={`${a.libelle} — ${visible ? 'couche visible' : 'couche masquée'}`}
                    onClick={() => onToggleLayer(a.code)}
                  >
                    <md-icon>{ALEA_ICONS[a.code] || ALEA_ICON_FALLBACK}</md-icon>
                    <span>{a.libelle}</span>
                    <md-icon className="cesium-chip-eye">
                      {visible ? 'visibility' : 'visibility_off'}
                    </md-icon>
                  </button>
                );
              })}
            </div>
          )}
          {simulableAleas.length > 0 && (
            <div className="cesium-simbar" role="group" aria-label="Simulations d'aléas sur le globe">
              <span className="cesium-simbar-title">
                <md-icon>science</md-icon>
                <span>Simulations</span>
              </span>
              <button
                type="button"
                className={`cesium-sim-btn source-btn${sourceMode ? ' active' : ''}`}
                disabled={sim?.status === 'queued' || sim?.status === 'running'}
                title="Placer une source d'eau sur le globe et voir l'inondation se propager depuis ce point (relief réel RGE ALTI)"
                onClick={() => setSourceMode((m) => !m)}
              >
                <md-icon>{sourceMode ? 'close' : 'water_drop'}</md-icon>
                <span>{sourceMode ? 'Annuler' : 'Placer une source'}</span>
              </button>
              {sourceMode && (
                <span className="cesium-sim-hint" role="status" aria-live="polite">
                  <md-icon>touch_app</md-icon>
                  <span>Cliquez sur le globe pour placer la source d'eau</span>
                </span>
              )}
              {source && !sourceMode && (
                <div className="cesium-source-ctrl" role="group" aria-label="Source manuelle d'inondation">
                  <span className="cesium-source-info">
                    <md-icon>water_drop</md-icon>
                    <span>
                      Source {source.lat.toFixed(4)}, {source.lon.toFixed(4)}
                    </span>
                  </span>
                  <label className="cesium-source-range">
                    <span className="cesium-source-range-label">Intensité</span>
                    <input
                      type="range"
                      min={0.1}
                      max={1}
                      step={0.05}
                      value={intensite}
                      aria-label="Intensité de la source d'eau"
                      onChange={(e) => onIntensiteChange(Number(e.target.value))}
                    />
                    <span className="cesium-source-range-val">
                      {Math.round(intensite * 100)}%
                    </span>
                  </label>
                  <button
                    type="button"
                    className="cesium-source-close"
                    title="Retirer la source"
                    aria-label="Retirer la source"
                    onClick={clearSource}
                  >
                    <md-icon>close</md-icon>
                  </button>
                </div>
              )}
              {simulableAleas.map((a) => {
                const active = sim?.code === a.code && sim.status !== 'error';
                return (
                  <button
                    key={a.code}
                    type="button"
                    className={`cesium-sim-btn${active ? ' active' : ''}`}
                    disabled={sim?.status === 'queued' || sim?.status === 'running'}
                    title={SIMULABLE_ALEAS[a.code].hint}
                    onClick={() => {
                      setSourceMode(false);
                      void launchSimulation(a.code);
                    }}
                  >
                    <md-icon>{SIMULABLE_ALEAS[a.code].icon}</md-icon>
                    <span>{SIMULABLE_ALEAS[a.code].libelle}</span>
                  </button>
                );
              })}
              {sim && (
                <span className={`cesium-sim-status s-${sim.status}`} role="status" aria-live="polite">
                  {sim.status === 'queued' && (
                    <>
                      <md-linear-progress indeterminate />
                      <span>Mise en file…</span>
                    </>
                  )}
                  {sim.status === 'running' && (
                    <>
                      <md-linear-progress indeterminate />
                      <span>Calcul de la simulation…</span>
                    </>
                  )}
                  {sim.status === 'ready' && (
                    <>
                      <md-icon>play_circle</md-icon>
                      <span>
                        {SIMULABLE_ALEAS[sim.code]?.libelle ?? sim.code}
                        {sim.label ? ` — ${sim.label}` : ''} · lecture en cours
                        (contrôles dans la timeline ci-dessous)
                      </span>
                    </>
                  )}
                  {sim.status === 'error' && (
                    <>
                      <md-icon>error</md-icon>
                      <span>{sim.error || 'Simulation en échec.'}</span>
                    </>
                  )}
                </span>
              )}
              {sim && sim.status !== 'error' && (
                <button
                  type="button"
                  className="cesium-sim-stop"
                  aria-label="Arrêter la simulation"
                  title="Arrêter la simulation"
                  onClick={stopSimulation}
                >
                  <md-icon>stop</md-icon>
                </button>
              )}
            </div>
          )}
          <Suspense
            fallback={
              <div className="bim-loading cesium-suspense" role="status" aria-live="polite">
                <md-icon>public</md-icon>
                <span>Chargement du globe 3D…</span>
                <md-linear-progress indeterminate />
              </div>
            }
          >
            <CesiumViewer
              lat={report.lat}
              lon={report.lon}
              codeInsee={report.code_insee}
              aleas={report.aleas}
              visibleLayerKeys={visibleLayerKeys}
              simulation={simForGlobe}
              onSimulationError={(code, message) =>
                setSim((prev) =>
                  prev && prev.code === code
                    ? { code, status: 'error', error: `Chargement CZML : ${message}` }
                    : prev
                )
              }
              sourceMode={sourceMode}
              source={source}
              onSourcePicked={onSourcePicked}
              buildingUrl={modelUrl}
            />
          </Suspense>
          <p className="cesium-note" role="note">
            <md-icon>terrain</md-icon>
            <span>
              Relief mondial libre (Esri World Elevation3D) · imagerie CARTO ·{' '}
              couches BRGM Géorisques avec le même toggle que l'étape 2 ·{' '}
              simulations CZML du pipeline backend (moteurs stylisés — pas de
              modélisation physique réglementaire).
              <strong> Vue géospatiale à but pédagogique — ne remplace pas une
              étude d'ingénierie.</strong>
            </span>
          </p>
        </div>
      )}

      {!batiment && (
        <div className="bim-banner">
          <md-icon>info</md-icon>
          <span>
            Emprise BDNB indisponible pour cette adresse — affichage d'une
            géométrie générique (10 × 10 × 6 m). Essayez une adresse voisine
            pour un modèle fidèle.
          </span>
        </div>
      )}

      {view === 'bim' && report.aleas?.some((a) => a.present === true) && (
        <p className="bim-sim-note" role="note">
          <md-icon>science</md-icon>
          <span>
            Simulations visualisables dans le viewer (panneau « Simulations », en
            haut à droite) : l'intensité suit les niveaux Géorisques du rapport.{' '}
            <strong>Simulation visuelle à but pédagogique — ne remplace pas une
            étude d'ingénierie (modélisation hydraulique, thermique ou sismique
            réglementaire).</strong>
          </span>
        </p>
      )}

      <p className="bim-footnote">
        Générateur glTF maison (footprint BDNB → extrusion, aucun GPU backend) · rendu{' '}
        <strong>thingraph/bim-viewer</strong> (three.js) en iframe · orbit,
        section, mesures et simulations dans le viewer — navigation clavier : A / D / W / S
      </p>
    </div>
  );
}

/* ─────────── Petits blocs réutilisables ─────────── */

function Chip({
  icon,
  value,
  label,
}: {
  icon: string;
  value: string | number | null | undefined;
  label: string;
}) {
  const str = value == null || value === '' ? null : String(value);
  return (
    <span className={`bim-chip${str == null ? ' na' : ''}`}>
      <md-icon>{icon}</md-icon>
      <span className="bim-chip-label">{label}</span>
      <span className="bim-chip-value">{str ?? 'non renseignée'}</span>
    </span>
  );
}

function fmtNum(v: number | null | undefined, digits = 0): string | null {
  if (v == null || Number.isNaN(v)) return null;
  return v.toLocaleString('fr-FR', { maximumFractionDigits: digits });
}

function fmt(v: number | null | undefined, suffix = ''): string | null {
  const n = fmtNum(v, 1);
  return n == null ? null : `${n}${suffix}`;
}
