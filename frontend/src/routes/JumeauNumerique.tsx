// =============================================================================
//   TYPHOON — /jumeau : jumeau numérique 3D (port React du front natif
//   frontend/jumeau_numerique/index.html, écran app-ui).
//
//   Le moteur Three.js (src/jumeau/scene-engine.js) est porté TEL QUEL depuis
//   le fichier natif et adresse le DOM par #id (scene-container, toggle-panel,
//   info-panel, …). Cette route reproduit donc fidèlement le markup attendu,
//   monte le moteur après le premier rendu (useEffect) et le démonte au
//   départ (disposeScene) — compatible StrictMode (double montage en dev).
// =============================================================================

import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { API } from '../zone/config';
import '../styles/jumeau.css';

export function JumeauNumerique() {
  useEffect(() => {
    // Import dynamique : three.js (≈600 ko) n'est chargé que sur cette
    // route, pas dans le bundle principal (le build garde ainsi le chunk
    // global sous contrôle). Le moteur peut lire window.TYPHOON_API en
    // repli (recherche artisans).
    (window as any).TYPHOON_API = API;
    let disposed = false;
    let stop: (() => void) | null = null;
    import('../jumeau/scene-engine')
      .then(({ initScene, disposeScene }) => {
        // En StrictMode (dev), le premier .then voit toujours disposed === true
        // et appelle disposeScene() : c'est un no-op sûr (état encore vierge),
        // il précède l'initScene du second montage dans l'ordre d'exécution.
        if (disposed) {
          disposeScene();
          return;
        }
        initScene();
        stop = disposeScene;
      })
      .catch((err) => {
        const el = document.getElementById('scene-container');
        if (el && !disposed) {
          el.innerHTML =
            '<div style="padding:40px;text-align:center;color:#C0392B;font-size:13px;line-height:1.6">' +
            '<strong>Le moteur 3D n\'a pas pu être chargé.</strong><br>' +
            'Rechargez la page ou réessayez dans quelques instants.' +
            '</div>';
        }
        console.error('Échec du chargement du moteur 3D :', err);
      });
    return () => {
      disposed = true;
      stop?.();
    };
  }, []);

  return (
    <div className="jumeau-app">
      <header className="jumeau-topbar">
        <div className="jumeau-brand">
          <Link to="/" className="jumeau-brand-back" aria-label="Retour à l'accueil">
            <md-icon aria-hidden="true">arrow_back</md-icon>
          </Link>
          <div>
            <h1>Jumeau numérique 3D</h1>
            <div className="jumeau-brand-tag">Diagnostic climatique immobilier</div>
          </div>
        </div>
      </header>

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
          <h3>Jumeau numérique — Diagnostic</h3>
          <div className="addr-line" id="addr-line">—</div>
          <div id="toggle-buttons">
            <button id="btn-2025" type="button" className="active">2025</button>
            <button id="btn-2050" type="button">2050</button>
          </div>
          <div id="global-score">Score global : <strong id="score-value">--</strong> / 100</div>
          <div id="reco-status"
            style={{ display: 'none', alignItems: 'center', gap: 6, marginTop: 6, fontSize: 11.5, color: '#4E5860', fontWeight: 600 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--brand)', flexShrink: 0 }}></span>
            Recommandations en cours de génération…
          </div>
          <div style={{ marginTop: 8 }}>
            <button type="button" id="btn-climat-toggle"
              style={{ background: '#F1F6F9', border: '1px solid #DCE6EC', color: '#316f96', padding: '6px 12px', borderRadius: 6, fontSize: 11.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
              Climat 2050
            </button>
          </div>
          <div style={{ marginTop: 8 }}>
            <Link to="/property-id" className="jumeau-pid-link">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              Voir mon Property ID →
            </Link>
          </div>
          <div id="climat-panel">
            <div style={{ fontSize: 11, color: '#316f96', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
              Projection climatique 2050
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <strong id="temp-value" style={{ color: '#DC4B39', fontSize: 26, lineHeight: 1 }}>—</strong>
            </div>
            <div style={{ color: '#8B959D', fontSize: 10.5, marginTop: 2 }}>Pic de chaleur max estimé</div>
            <div style={{ marginTop: 6, fontSize: 10, color: '#A7ADB2' }}>Source : <span id="climat-sources-badge">—</span></div>
            <div id="copernicus-badge" style={{ display: 'none', marginTop: 6, background: '#dceef4', color: '#316f96', fontSize: 10, padding: '3px 8px', borderRadius: 999, fontWeight: 700 }}>
              Données Copernicus disponibles
            </div>
            <div id="dvf-badge" style={{ display: 'none', marginTop: 4, background: '#E4F5EC', color: '#1F9D6C', fontSize: 10, padding: '3px 8px', borderRadius: 999, fontWeight: 700 }}>
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

          <div id="info-zone-header" style={{ marginBottom: 8 }}>
            <h3 id="info-title">Zone</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <div className="badge" id="info-badge" style={{ marginBottom: 0 }}>Risque</div>
              <p id="info-alea" style={{ margin: 0, fontSize: 13.5, color: '#1E2A33' }}></p>
            </div>
            <div id="info-score-bar-track"><div id="info-score-bar-fill"></div></div>
            <p id="info-justif" style={{ color: '#4E5860', fontSize: 12, margin: '4px 0 0' }}></p>
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

          <div id="info-conclusion" style={{ margin: '8px 0 4px', padding: '10px 12px', background: 'rgba(49,111,150,0.06)', border: '1px solid rgba(49,111,150,0.15)', borderRadius: 8, display: 'none' }}>
            <div id="info-diagnostic-header" style={{ fontSize: 13, fontWeight: 700, color: '#1E2A33', marginBottom: 6 }}>Diagnostic &amp; Risques</div>
            <div id="info-etat" style={{ fontSize: 13.5, color: '#333E47', lineHeight: 1.6, marginBottom: 8, padding: '6px 8px', background: 'rgba(255,255,255,0.5)', borderRadius: 6 }}></div>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#4E5860', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>Facteurs Clés</div>
            <div style={{ marginTop: 0 }}>
              <div id="info-aggravants" style={{ marginBottom: 5 }}></div>
              <div id="info-attenuants"></div>
            </div>
          </div>

          <div id="info-recos"></div>

          <button type="button" id="info-export-pdf">⬇ Exporter en PDF</button>
        </div>

        <div id="hint">Glisser = orbiter · Molette = zoom · Clic sur une zone = détails</div>

        {/* Le moteur lit cet input en repli pour l'API (recherche artisans). */}
        <input id="api-base-input" type="hidden" defaultValue={API} aria-hidden="true" />
      </div>
    </div>
  );
}
