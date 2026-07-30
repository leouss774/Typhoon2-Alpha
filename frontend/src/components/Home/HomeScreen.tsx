import "./HomeScreen.css";

interface HomeScreenProps {
  onStart: () => void;
  isBankRoute?: boolean;
}

export default function HomeScreen({ onStart, isBankRoute }: HomeScreenProps) {
  return (
    <div className="home-screen">
      {/* ===== HERO ===== */}
      <section className="home-hero">
        <div className="home-hero-content">
          <div className="home-eyebrow">
            <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2 4 5v6c0 5 3.5 9 8 11 4.5-2 8-6 8-11V5z"/><path d="m9 12 2 2 4-4"/>
            </svg>
            Intelligence Climatique
          </div>
          <h1 className="home-hero-title">
            Anticipez les risques <em>climatiques</em> de votre bien immobilier
          </h1>
          <p className="home-hero-lead">
            Diagnostic multi-agents basé sur les données publiques (Géorisques, BDNB, IGN, Open-Meteo).
            Jumeau numérique 3D, scoring des risques et {isBankRoute ? "décision bancaire" : "certification climatique"}.
          </p>
          <div className="home-hero-ctas">
            <button onClick={onStart} className="btn-primary btn-hero">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
              </svg>
              Diagnostiquer mon bien
            </button>
            {!isBankRoute && (
              <a href="/bank" className="home-hero-link">
                🏦 Accès Banquier →
              </a>
            )}
            {isBankRoute && (
              <a href="/" className="home-hero-link">
                ← Site principal
              </a>
            )}
          </div>
        </div>
        <div className="home-hero-visual">
          <div className="hv-stack">
            <div className="hv-card">
              <div className="hv-row">
                <div>
                  <div className="hv-label">Score Global</div>
                  <div className="hv-value hv-value-lg">68/100</div>
                </div>
                <span className="hv-badge risk-high">Élevé</span>
              </div>
              <div className="hv-bar-track">
                <div className="hv-bar-fill" style={{ width: "68%" }} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <div className="hv-card" style={{ flex: 1, marginBottom: 0 }}>
                <div className="hv-label">Risques identifiés</div>
                <div className="hv-value">RGA • Inondation</div>
              </div>
              <div className="hv-card" style={{ flex: 1, marginBottom: 0 }}>
                <div className="hv-label">Travaux estimés</div>
                <div className="hv-value">19 000 – 58 000€</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== TRUST BAR ===== */}
      <div className="home-trustbar">
        {[
          { num: "7+", lbl: "Sources de données" },
          { num: "4", lbl: "Agents IA" },
          { num: "3D", lbl: "Jumeau Numérique" },
          { num: "🏦", lbl: "Décision Bancaire" },
        ].map((stat, i) => (
          <div key={i} className="trust-stat">
            <div className="trust-stat-num">{stat.num}</div>
            <div className="trust-stat-lbl">{stat.lbl}</div>
          </div>
        ))}
      </div>

      {/* ===== FEATURES ===== */}
      <section className="home-features">
        <div className="section-eyebrow">Fonctionnalités</div>
        <h2 className="section-title">Un diagnostic complet en un clic</h2>
        <p className="section-lead">
          De la collecte des données publiques à la visualisation 3D, en passant par le scoring et {isBankRoute ? "la décision bancaire" : "la certification"}.
        </p>
        <div className="home-feature-grid">
          {[
            { icon: "🌍", title: "Données Officielles", desc: "Géorisques, BDNB, IGN, Open-Meteo, DVF — des sources fiables et gratuites." },
            { icon: "🎯", title: "Scoring Multi-Risques", desc: "RGA, inondation, canicule, tempête, feu de forêt — 7 zones du bâtiment analysées." },
            { icon: "🏗️", title: "Jumeau Numérique 3D", desc: "Visualisation interactive du bien avec codes couleur par niveau de risque." },
            { icon: "💰", title: isBankRoute ? "Décision Bancaire" : "Certification", desc: isBankRoute ? "Intégration du scoring dans la décision de crédit immobilier avec calcul actuariel." : "Génération d'un certificat de résilience avec estimation des travaux." },
            { icon: "📋", title: "Recommandations", desc: "Travaux priorisés avec coûts estimés, aides mobilisables et gain de résilience." },
            { icon: "🔮", title: "Projection 2050", desc: "Anticipez l'évolution des risques climatiques à horizon 2050 selon les scénarios CMIP6." },
          ].map((f, i) => (
            <div key={i} className="feature-card">
              <div className="fc-icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ===== DEUX MODES ===== */}
      <section className="home-modes">
        <div className="modes-head">
          <div className="section-eyebrow">Deux modes</div>
          <h2 className="section-title">Pour les particuliers &amp; les professionnels</h2>
        </div>
        <div className="mode-grid">
          <div className="mode-card mode-a">
            <div className="mode-kicker">Particuliers</div>
            <h3>Diagnostic et certification de votre bien</h3>
            <p>Évaluez la résilience climatique de votre logement, obtenez un certificat et planifiez vos travaux.</p>
            <ul>
              <li>
                <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="#3FE28F" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m7 10 2 2 4-4"/><circle cx="10" cy="10" r="8"/></svg>
                Score de risque par zone du bâtiment
              </li>
              <li>
                <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="#3FE28F" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m7 10 2 2 4-4"/><circle cx="10" cy="10" r="8"/></svg>
                Recommandations de travaux priorisées
              </li>
              <li>
                <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="#3FE28F" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m7 10 2 2 4-4"/><circle cx="10" cy="10" r="8"/></svg>
                Aides financières mobilisables
              </li>
            </ul>
            <button onClick={onStart} className="btn-ghost" style={{ color: "#fff", borderColor: "rgba(255,255,255,0.5)", alignSelf: "flex-start", position: "relative", zIndex: 2 }}>
              Diagnostiquer →
            </button>
          </div>
          <div className="mode-card mode-b">
            <div className="mode-kicker mode-kicker-b">Professionnels</div>
            <div className="map-fx" />
            <div className="pin low" style={{ top: "25%", left: "35%" }} />
            <div className="pin mod" style={{ top: "40%", left: "55%" }} />
            <div className="pin high" style={{ top: "55%", left: "25%" }} />
            <h3>Analyse de crédit &amp; décision bancaire</h3>
            <p>Évaluez le risque climatique des biens financés avec scoring bancaire, taux ajustés et simulation actuarielle.</p>
            <ul>
              <li>
                <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="#5DB2FF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m7 10 2 2 4-4"/><circle cx="10" cy="10" r="8"/></svg>
                Score de risque bancaire (0-100)
              </li>
              <li>
                <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="#5DB2FF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m7 10 2 2 4-4"/><circle cx="10" cy="10" r="8"/></svg>
                Valorisation DVF + décote climatique
              </li>
              <li>
                <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="#5DB2FF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m7 10 2 2 4-4"/><circle cx="10" cy="10" r="8"/></svg>
                Projection 2050 et conditions de prêt
              </li>
            </ul>
            <a href="/bank" className="btn-ghost mode-btn-b" style={{ alignSelf: "flex-start" }}>
              Accès Banquier →
            </a>
          </div>
        </div>
      </section>

      {/* ===== TRUST / SECTEURS ===== */}
      <section className="home-trust">
        <div className="section-eyebrow">Cas d'usage</div>
        <h2 className="section-title">Adapter à votre métier</h2>
        <p className="section-lead">
          Typhoon s'intègre dans vos processus métier, que vous soyez assureur, banquier, agent immobilier ou promoteur.
        </p>
        <div className="trust-grid">
          {[
            {
              icon: "🛡️",
              sector: "Assurance",
              usecase: "Devis personnalisé intégrant le risque climatique. Filtrage amont des biens à très haut risque.",
              logos: ["Score risque", "Devis", "CatNat"],
            },
            {
              icon: "🏦",
              sector: "Banque & Financement",
              usecase: "Analyse de crédit avec scoring climatique, valorisation ajustée et conditions de prêt différenciées.",
              logos: ["Scoring", "DVF", "Taux directeurs"],
            },
            {
              icon: "🏠",
              sector: "Agents & Promoteurs",
              usecase: "Recherche de biens intégrant la résilience climatique et argumentaire de vente basé sur le score.",
              logos: ["Recherche", "Score", "Promotion"],
            },
          ].map((t, i) => (
            <div key={i} className="trust-card">
              <div className="trust-icon">{t.icon}</div>
              <div className="trust-sector">{t.sector}</div>
              <p className="trust-usecase">{t.usecase}</p>
              <div className="trust-logos">
                {t.logos.map((logo) => (
                  <span key={logo} className="trust-logo">{logo}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ===== CTA FINAL ===== */}
      <section className="home-cta-final">
        <div className="cta-card">
          <div className="cta-content">
            <h2>Prêt à diagnostiquer votre bien ?</h2>
            <p>Gratuit, sans engagement. Données officielles et certification incluse.</p>
          </div>
          <button onClick={onStart} className="btn-primary" style={{ fontSize: 16, padding: "16px 32px" }}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
            </svg>
            Diagnostiquer mon bien
          </button>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer className="home-footer">
        <span className="footer-note">© 2026 Typhoon — Diagnostic Climatique Immobilier</span>
        <div className="footer-links">
          <a href="#">Mentions légales</a>
          <a href="#">Contact</a>
          <a href="mailto:bonjour@typhoon.immo">bonjour@typhoon.immo</a>
        </div>
      </footer>
    </div>
  );
}
