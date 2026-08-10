// =============================================================================
//   TYPHOON — /jumeau : jumeau numérique 3D (port React du front natif
//   frontend/jumeau_numerique/index.html, écran app-ui).
//
//   Design : Material 3 (m3.material.io) thème sombre D03, identique au /zone.
//   Composants @material/web (md-icon, md-icon-button, md-elevated-button).
//
//   Le moteur Three.js (src/jumeau/scene-engine.js) est porté TEL QUEL depuis
//   le fichier natif et adresse le DOM par #id (scene-container, toggle-panel,
//   info-panel, …). Cette route reproduit donc fidèlement le markup attendu,
//   monte le moteur après le premier rendu (useEffect) et le démonte au
//   départ (disposeScene) — compatible StrictMode (double montage en dev).
//   Tous les #id et classes lus par le moteur sont conservés à l'identique ;
//   seuls les styles sont redéfinis en M3 sombre (jumeau.css).
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { API } from '../zone/config';
import '../styles/jumeau.css';

type SceneEngine = typeof import('../jumeau/scene-engine');
type DiagStatus = 'demo' | 'loading' | 'ready' | 'error';

export function JumeauNumerique() {
  const engineRef = useRef<SceneEngine | null>(null);
  const loadingRef = useRef(false);
  const [adresse, setAdresse] = useState(
    () => new URLSearchParams(window.location.search).get('adresse') ?? ''
  );
  const [status, setStatus] = useState<DiagStatus>('demo');
  const [error, setError] = useState('');

  const runDiagnostic = (addr: string) => {
    const engine = engineRef.current;
    const value = addr.trim();
    if (!engine || !value || loadingRef.current) return;
    loadingRef.current = true;
    setStatus('loading');
    setError('');
    engine
      .loadFromAddress(value)
      .then(() => setStatus('ready'))
      .catch((err: unknown) => {
        setStatus('error');
        setError(
          err instanceof Error ? err.message : 'Erreur inconnue — vérifiez que le backend tourne.'
        );
      })
      .finally(() => {
        loadingRef.current = false;
      });
  };

  useEffect(() => {
    // Import dynamique : three.js (≈600 ko) n'est chargé que sur cette
    // route, pas dans le bundle principal (le build garde ainsi le chunk
    // global sous contrôle). Le moteur peut lire window.TYPHOON_API en
    // repli (recherche artisans).
    (window as any).TYPHOON_API = API;
    let disposed = false;
    let stop: (() => void) | null = null;
    import('../jumeau/scene-engine')
      .then((engine) => {
        const { initScene, disposeScene } = engine;
        // En StrictMode (dev), le premier .then voit toujours disposed === true
        // et appelle disposeScene() : c'est un no-op sûr (état encore vierge),
        // il précède l'initScene du second montage dans l'ordre d'exécution.
        if (disposed) {
          disposeScene();
          return;
        }
        initScene();
        stop = disposeScene;
        engineRef.current = engine;
        // Arrivée depuis /zone (ou lien partagé) : ?adresse=... lance le
        // diagnostic réel dès que la scène est prête, sans clic supplémentaire.
        const fromUrl = new URLSearchParams(window.location.search).get('adresse');
        if (fromUrl && fromUrl.trim()) runDiagnostic(fromUrl);
      })
      .catch((err) => {
        const el = document.getElementById('scene-container');
        if (el && !disposed) {
          el.innerHTML =
            '<div style="padding:40px;text-align:center;color:var(--md-sys-color-error,#ffb4ab);font-size:13px;line-height:1.6">' +
            '<strong>Le moteur 3D n\'a pas pu être chargé.</strong><br>' +
            'Rechargez la page ou réessayez dans quelques instants.' +
            '</div>';
        }
        console.error('Échec du chargement du moteur 3D :', err);
      });
    return () => {
      disposed = true;
      engineRef.current = null;
      stop?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="jumeau-app">
      {/* ── Topbar M3 ── */}
      <header className="jumeau-topbar">
        <div className="jumeau-brand">
          <Link to="/" className="jumeau-brand-back" aria-label="Retour à l'accueil">
            <md-icon aria-hidden="true">arrow_back</md-icon>
          </Link>
          <div className="jumeau-brand-text">
            <h1>Jumeau numérique 3D</h1>
            <div className="jumeau-brand-tag">Diagnostic climatique immobilier</div>
          </div>
        </div>
        {/* ── Diagnostic réel par adresse (flux /diagnostic/fast) ── */}
        <form
          className="jumeau-addr-form"
          onSubmit={(e) => {
            e.preventDefault();
            runDiagnostic(adresse);
          }}
        >
          <input
            className="jumeau-addr-input"
            type="text"
            value={adresse}
            onChange={(e) => setAdresse(e.target.value)}
            placeholder="8 Allée du Port Maillard, 44000 Nantes"
            aria-label="Adresse du bien à diagnostiquer"
            disabled={status === 'loading'}
          />
          <md-filled-button trailing-icon type="submit" disabled={status === 'loading' || !adresse.trim()}>
            {status === 'loading' ? 'Diagnostic…' : 'Diagnostiquer'}
            <md-icon slot="icon" aria-hidden="true">view_in_ar</md-icon>
          </md-filled-button>
        </form>
        <span className="jumeau-sovereign-badge">Souverain FR / UE</span>
      </header>

      {/* Bandeau d'état sous la topbar : démo / chargement / erreur */}
      {status === 'demo' && (
        <div className="jumeau-status is-demo" role="status">
          <md-icon aria-hidden="true">info</md-icon>
          <span>
            Données de démonstration affichées — saisissez l'adresse du bien pour générer son
            jumeau réel (emprise BDNB, scores de risque, recommandations).
          </span>
        </div>
      )}
      {status === 'loading' && (
        <div className="jumeau-status is-loading" role="status" aria-live="polite">
          <md-icon aria-hidden="true">progress_activity</md-icon>
          <span>
            Diagnostic en cours — géocodage, Géorisques, BDNB, scoring… La maison s'affiche dès
            que les scores sont prêts ; les recommandations arrivent ensuite en arrière-plan.
          </span>
          <md-linear-progress indeterminate />
        </div>
      )}
      {status === 'error' && (
        <div className="jumeau-status is-error" role="alert">
          <md-icon aria-hidden="true">error</md-icon>
          <span>Échec du diagnostic : {error}</span>
          <button type="button" className="jumeau-status-retry" onClick={() => runDiagnostic(adresse)}>
            Réessayer
          </button>
        </div>
      )}

      {/* ── Scène (zone plein écran) ── */}
      <div className="jumeau-scene">
        <div id="scene-container"></div>

        {/* Tooltip flottant (positionné par le moteur au survol) */}
        <div id="zone-tooltip"></div>

        {/* Légende couleurs de risque */}
        <div id="risk-legend">
          <div className="rl-item"><span className="rl-dot" style={{ background: '#1F9D6C' }}></span>Faible</div>
          <div className="rl-item"><span className="rl-dot" style={{ background: '#D98A2B' }}></span>Modéré</div>
          <div className="rl-item"><span className="rl-dot" style={{ background: '#BF5E00' }}></span>Élevé</div>
          <div className="rl-item"><span className="rl-dot" style={{ background: '#C0392B' }}></span>Critique</div>
        </div>

        {/* Panneau gauche : bascule 2025/2050, score global, climat */}
        <div id="toggle-panel">
          <div className="tp-head">
            <md-icon aria-hidden="true">view_in_ar</md-icon>
            <h3>Jumeau numérique — Diagnostic</h3>
          </div>
          <div className="addr-line" id="addr-line">—</div>

          <div id="toggle-buttons">
            <button id="btn-2025" type="button" className="active">2025</button>
            <button id="btn-2050" type="button">2050</button>
          </div>

          <div id="global-score">
            Score global : <strong id="score-value">--</strong> / 100
          </div>

          <div id="reco-status" className="reco-status">
            <span className="reco-status-dot"></span>
            Recommandations en cours de génération…
          </div>

          <div className="tp-actions">
            <button type="button" id="btn-climat-toggle">
              Climat 2050
            </button>
            <Link to="/property-id" className="jumeau-pid-link">
              <md-icon aria-hidden="true">description</md-icon>
              Voir mon Property ID →
            </Link>
          </div>

          <div id="climat-panel">
            <div className="climat-title">Projection climatique 2050</div>
            <div className="climat-temp-row">
              <strong id="temp-value">—</strong>
              <span>°C</span>
            </div>
            <div className="climat-sub">Pic de chaleur max estimé</div>
            <div className="climat-source">Source : <span id="climat-sources-badge">—</span></div>
            <div id="copernicus-badge" className="data-badge badge-copernicus">
              Données Copernicus disponibles
            </div>
            <div id="dvf-badge" className="data-badge badge-dvf">
              Données de marché (DVF) disponibles
            </div>
          </div>
        </div>

        {/* Panneau droit : détail de zone cliquée */}
        <div id="info-panel">
          <div id="info-risk-filter">
            <button type="button" className="risk-filter-btn active" data-filter="tous">Tous</button>
            <button type="button" className="risk-filter-btn" data-filter="critique">Critique</button>
            <button type="button" className="risk-filter-btn" data-filter="eleve">Élevé</button>
            <button type="button" className="risk-filter-btn" data-filter="modere">Modéré</button>
          </div>

          <div id="info-zone-tabs"></div>

          <div id="info-zone-header">
            <h3 id="info-title">Zone</h3>
            <div className="info-badge-row">
              <div className="badge" id="info-badge">Risque</div>
              <p id="info-alea"></p>
            </div>
            <div id="info-score-bar-track"><div id="info-score-bar-fill"></div></div>
            <p id="info-justif"></p>
          </div>

          <div id="info-cost-summary">
            <div className="cost-summary-row">
              <span className="cs-label">Cout total estime</span>
              <span className="cs-value" id="cs-total">—</span>
            </div>
            <div className="cost-summary-row">
              <span className="cs-label">Couverture aides</span>
              <span className="cs-value accent" id="cs-aides">—</span>
            </div>
            <div className="cost-summary-row">
              <span className="cs-label">Reste a charge estime</span>
              <span className="cs-value" id="cs-reste">—</span>
            </div>
            <div className="cost-summary-progress">
              <div className="cp-fill" id="cs-progress" style={{ width: '0%' }}></div>
            </div>
          </div>

          <div id="info-conclusion">
            <div id="info-diagnostic-header">Diagnostic &amp; Risques</div>
            <div id="info-etat"></div>
            <div className="info-factors-title">Facteurs Clés</div>
            <div>
              <div id="info-aggravants"></div>
              <div id="info-attenuants"></div>
            </div>
          </div>

          <div id="info-recos"></div>

          <md-elevated-button id="info-export-pdf" class="info-export-btn">
            <md-icon slot="icon" aria-hidden="true">picture_as_pdf</md-icon>
            Exporter en PDF
          </md-elevated-button>
        </div>

        <div id="hint">
          <md-icon aria-hidden="true">pan_tool_alt</md-icon>
          <span>Glisser = orbiter · Molette = zoom · Clic sur une zone = détails</span>
        </div>

        {/* Le moteur lit cet input en repli pour l'API (recherche artisans). */}
        <input id="api-base-input" type="hidden" defaultValue={API} aria-hidden="true" />
      </div>
    </div>
  );
}
