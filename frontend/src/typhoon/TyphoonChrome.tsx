import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ACCENTS, BRAND_ACCENT, useTyphoonTheme } from './useTyphoonTheme';

function ThemeIconSun() {
  return (
    <svg className="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2" />
      <path d="M12 20v2" />
      <path d="m4.93 4.93 1.41 1.41" />
      <path d="m17.66 17.66 1.41 1.41" />
      <path d="M2 12h2" />
      <path d="M20 12h2" />
      <path d="m6.34 17.66-1.41 1.41" />
      <path d="m19.07 4.93-1.41 1.41" />
    </svg>
  );
}

function ThemeIconMoon() {
  return (
    <svg className="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function PaletteIcon() {
  return (
    <svg className="icon-palette" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22a10 10 0 1 1 10-10c0 1.7-1.3 3-3 3h-2a2 2 0 0 0-2 2c0 .6.2 1 .6 1.4.4.4.6.8.6 1.4 0 1.7-1.3 3-3 3z" />
      <circle cx="7.5" cy="11.5" r=".5" fill="currentColor" />
      <circle cx="11" cy="7.5" r=".5" fill="currentColor" />
      <circle cx="15.5" cy="7.5" r=".5" fill="currentColor" />
    </svg>
  );
}

export function TyphoonControls() {
  const { theme, accent, panelOpen, setPanelOpen, toggleTheme, resetAccent, pickAccent } = useTyphoonTheme();

  return (
    <>
      <button
        type="button"
        className="theme-toggle"
        aria-label="Basculer le mode clair / sombre"
        title="Mode clair / sombre"
        onClick={toggleTheme}
      >
        <ThemeIconSun />
        <ThemeIconMoon />
      </button>
      <div className={`color-control ${panelOpen ? 'open' : ''}`}>
        <button
          type="button"
          className="color-toggle"
          title="Changer la couleur d'accent"
          aria-label="Changer la couleur d'accent"
          aria-expanded={panelOpen}
          onClick={() => setPanelOpen((o) => !o)}
        >
          <PaletteIcon />
          <span className="accent-dot" style={{ background: accent }} />
        </button>
        <div className="accent-panel" role="dialog" aria-label="Couleur d'accent">
          <div className="accent-panel-title">Couleur d'accent</div>
          <div className="accent-swatches">
            {ACCENTS.map((hex) => (
              <button
                key={hex}
                type="button"
                className={`accent-swatch ${accent.toLowerCase() === hex.toLowerCase() ? 'active' : ''}`}
                style={{ '--swatch': hex } as React.CSSProperties}
                aria-label={`Accent ${hex}`}
                title={hex}
                onClick={() => pickAccent(hex)}
              />
            ))}
          </div>
          <button type="button" className="accent-reset" aria-label="Rétablir le bleu d'origine" title="Rétablir le bleu d'origine" onClick={resetAccent}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
            <span>Rétablir le bleu d'origine</span>
          </button>
        </div>
      </div>
    </>
  );
}

export function TyphoonNavbar({ current }: { current?: 'home' | 'faq' | 'contact' }) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const is = (key: 'home' | 'faq' | 'contact') =>
    current === key || (!current && location.pathname === (key === 'home' ? '/' : `/${key}`));

  return (
    <div className="navbar landingpage">
      <div
        data-animation="default"
        data-collapse="medium"
        data-duration="400"
        data-easing="ease"
        data-easing2="ease"
        role="banner"
        className="webflow-native-navbar w-nav"
      >
        <div className="navbar-outer">
          <div className="navbar-inner">
            <Link
              to="/"
              aria-current={is('home') ? 'page' : undefined}
              className="navbar-logo-div visible-on-desktop w-nav-brand"
              aria-label="home"
            >
              <img src="/vetter-consulting/assets/img/typhoon-logo.svg" loading="eager" alt="Typhoon" className="logo" />
            </Link>
            <div className="nav-static-item">
              <div className="nav-arrow-div">
                <img src="/vetter-consulting/assets/img/typhoon-logo.svg" loading="lazy" alt="Typhoon" className="nav-arrow" />
              </div>
              <div className="nav-link-static">Menü</div>
            </div>
            <nav role="navigation" className={`nav-menu-wrapper w-nav-menu ${menuOpen ? 'menu-open' : ''}`}>
              <ul role="list" className="nav-menu-right w-list-unstyled">
                <li className="nav-item">
                  <Link to="/" className={`nav-link ${is('home') ? 'w--current' : ''}`}>
                    Home
                  </Link>
                </li>
                <li className="nav-item">
                  <Link to="/faq" className={`nav-link ${is('faq') ? 'w--current' : ''}`}>
                    FAQ
                  </Link>
                </li>
                <li className="nav-item">
                  <Link to="/contact" className={`nav-link ${is('contact') ? 'w--current' : ''}`}>
                    Contact
                  </Link>
                </li>
                <li className="nav-item">
                  <Link to="/zone" className="primary-btn w-inline-block">
                    <span className="btn-txt-container">
                      <span className="btn-txt">C'est parti</span>
                      <span className="btn-txt">C'est parti</span>
                    </span>
                  </Link>
                </li>
                <li className="mobile-margin-top-10" />
              </ul>
            </nav>
            <div className="nav-area-left mobile">
              <div
                className={`menu-button w-nav-button ${menuOpen ? 'w--open' : ''}`}
                style={{ WebkitUserSelect: 'text' }}
                aria-label="menu"
                role="button"
                tabIndex={0}
                aria-controls="w-nav-overlay-0"
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((o) => !o)}
              >
                <div className="hamburger-menu-dark">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" style={{ width: '100%', height: '100%' }} preserveAspectRatio="xMidYMid meet">
                    <path fill="rgb(255,255,255)" d="M0.25,12.25 C0.25,12.25 18.25,12.25 18.25,12.25 C18.25,12.25 18.25,10.25 18.25,10.25 C18.25,10.25 0.25,10.25 0.25,10.25 C0.25,10.25 0.25,12.25 0.25,12.25z" />
                    <path fill="rgb(255,255,255)" d="M0.25,7.25 C0.25,7.25 18.25,7.25 18.25,7.25 C18.25,7.25 18.25,5.25 18.25,5.25 C18.25,5.25 0.25,5.25 0.25,5.25 C0.25,5.25 0.25,7.25 0.25,7.25z" />
                    <path fill="rgb(255,255,255)" d="M0.25,0.25 C0.25,0.25 18.25,0.25 18.25,0.25 C18.25,0.25 18.25,2.25 18.25,2.25 C18.25,2.25 0.25,2.25 0.25,2.25 C0.25,2.25 0.25,0.25 0.25,0.25z" />
                  </svg>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="w-nav-overlay" data-wf-ignore="" id="w-nav-overlay-0" />
      </div>
      <TyphoonControls />
    </div>
  );
}

export function TyphoonFooter() {
  return (
    <div className="footer">
      <div className="footer-outer">
        <div className="footer-inner">
          <div className="footer-row mid">
            <div className="footer-column bottom-aligned">
              <img src="/vetter-consulting/assets/img/typhoon-wordmark.svg" alt="Typhoon" className="footer-logo" />
            </div>
            <div className="footer-column _2nd">
              <div className="align-vertically-2 is-right-aligned-desktop-only">
                <a href="https://www.linkedin.com/in/tobias--vetter/" target="_blank" rel="noreferrer" className="footer-url is-small">
                  LinkedIn
                </a>
                <a href="https://www.youtube.com/@tobias.vetter" target="_blank" rel="noreferrer" className="footer-url is-small">
                  YouTube
                </a>
                <a
                  href="https://www.instagram.com/tobiasvetter_?igsh=MWphY2M5dWJoaGY5cg=="
                  target="_blank"
                  rel="noreferrer"
                  className="footer-url is-small"
                >
                  Instagram
                </a>
              </div>
            </div>
          </div>
          <div className="footer-row">
            <div className="footer-column">
              <div className="align-vertically">
                <div className="copytext">Adresse</div>
                <div className="footer-txt is-small">75008 Paris, France</div>
              </div>
            </div>
            <div className="footer-column bottom-aligned">
              <a href="https://vetter-consulting.webflow.io/legal/impressum" className="footer-url-small">
                Mentions légales
              </a>
              <a href="https://vetter-consulting.webflow.io/legal/datenschutz" className="footer-url-small">
                Politique de confidentialité
              </a>
            </div>
          </div>
          <div className="footer-row ai-act">
            <div className="footer-column">
              <div className="align-vertically">
                <img
                  src="/vetter-consulting/assets/img/created-with-ai-label.png"
                  alt="Créé avec une IA générative"
                  className="ai-label"
                />
                <div className="copytext is-small is-grey">
                  Transparence IA — Règlement (UE) 2024/1689 (AI Act), art. 50
                </div>
                <div className="footer-txt is-small">
                  Ce site et ses contenus ont été générés avec l'assistance d'une IA générative (propulsée par Mistral AI).
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export { BRAND_ACCENT };
