"use client";

import { useState } from "react";
import ClientForm from "@/components/Form/ClientForm";
import Dashboard from "@/components/Dashboard/Dashboard";

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string | null>("demo-session-001");
  const [page, setPage] = useState<"dashboard" | "form">("dashboard");
  const [dashboardKey, setDashboardKey] = useState(0);
  const [showHome, setShowHome] = useState(true);

  const handleAnalyseLancee = (newSessionId: string) => {
    setSessionId(newSessionId);
    setDashboardKey((k) => k + 1);
    setPage("form");
    setShowHome(false);
  };

  const handleStartDiagnostic = () => {
    setShowHome(false);
    setPage("form");
  };

  // Home screen with hero
  if (showHome) {
    return <HomeScreen onStart={handleStartDiagnostic} />;
  }

  return (
    <div style={{ paddingTop: 24 }}>
      {page === "dashboard" && (
        <>
          <Dashboard key={dashboardKey} sessionId={sessionId} />
          <div style={{ textAlign: "center", padding: 12, marginTop: 8 }}>
            <button
              onClick={() => setPage("form")}
              className="btn-primary"
              style={{ fontSize: 14, padding: "12px 24px" }}
            >
              + Nouvelle analyse
            </button>
          </div>
        </>
      )}
      {page === "form" && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "radial-gradient(circle at 50% 18%, #FFF2EC 0%, #FFFFFF 65%)",
            overflowY: "auto",
            padding: "40px 20px",
          }}
        >
          <ClientForm onAnalyseLancee={handleAnalyseLancee} />
        </div>
      )}
    </div>
  );
}

function HomeScreen({ onStart }: { onStart: () => void }) {
  return (
    <div
      style={{
        overflowY: "auto",
        height: "100%",
        background: "#FFFFFF",
      }}
    >
      {/* Hero Section */}
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "1.05fr 0.95fr",
          gap: 40,
          alignItems: "center",
          padding: "70px 5vw 60px",
          maxWidth: 1280,
          margin: "0 auto",
        }}
      >
        <div>
          <div className="section-eyebrow" style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "#FFE4DA", padding: "6px 14px", borderRadius: 999 }}>
            🔥 Intelligence Climatique
          </div>
          <h1 className="section-title" style={{ fontSize: 44, lineHeight: 1.14, margin: "18px 0" }}>
            Anticipez les risques <em style={{ color: "#FF6B4A", fontStyle: "normal" }}>climatiques</em> de votre bien immobilier
          </h1>
          <p style={{ color: "#4B5760", fontSize: 16, lineHeight: 1.6, maxWidth: 480, marginBottom: 30 }}>
            Diagnostic multi-agents basé sur les données publiques (Géorisques, BDNB, IGN, Open-Meteo).
            Jumeau numérique 3D, scoring des risques et décision bancaire.
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <button onClick={onStart} className="btn-primary" style={{ fontSize: 15, padding: "15px 26px" }}>
              🔍 Diagnostiquer mon bien
            </button>
            <a href="/bank" className="btn-ghost" style={{ fontSize: 14 }}>
              🏦 Accès Banquier
            </a>
          </div>
        </div>

        <div
          style={{
            position: "relative",
            border: "1px solid #E7DED6",
            borderRadius: 8,
            padding: 28,
            minHeight: 400,
            display: "flex",
            flexDirection: "column",
            justifyContent: "flex-end",
            overflow: "hidden",
            background: "#1E2A33 url('/api/placeholder/600/400') center/cover no-repeat",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "linear-gradient(180deg, rgba(30,42,51,0.05) 0%, rgba(30,42,51,0.45) 55%, rgba(30,42,51,0.78) 100%)",
            }}
          />
          <div style={{ position: "relative", zIndex: 1 }}>
            <div style={{ background: "rgba(255,255,255,0.97)", border: "1px solid #E7DED6", borderRadius: 6, padding: "14px 18px", marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                <div>
                  <div style={{ color: "#8B959D", fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>Score Global</div>
                  <div style={{ color: "#1E2A33", fontSize: 22, fontWeight: 800 }}>68/100</div>
                </div>
                <span className="badge badge-eleve">Élevé</span>
              </div>
              <div style={{ height: 6, borderRadius: 999, background: "#F1ECE6", overflow: "hidden", marginTop: 8 }}>
                <div style={{ height: "100%", borderRadius: 999, background: "linear-gradient(90deg, #FFB89C, #FF6B4A)", width: "68%" }} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <div style={{ flex: 1, background: "rgba(255,255,255,0.97)", border: "1px solid #E7DED6", borderRadius: 6, padding: "10px 14px", textAlign: "center" }}>
                <div style={{ color: "#8B959D", fontSize: 10, fontWeight: 700, textTransform: "uppercase" }}>Risques</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#1E2A33" }}>RGA • Inondation</div>
              </div>
              <div style={{ flex: 1, background: "rgba(255,255,255,0.97)", border: "1px solid #E7DED6", borderRadius: 6, padding: "10px 14px", textAlign: "center" }}>
                <div style={{ color: "#8B959D", fontSize: 10, fontWeight: 700, textTransform: "uppercase" }}>Travaux</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#1E2A33" }}>19 000€ – 58 000€</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Trust Bar */}
      <div style={{ borderTop: "1px solid #E7DED6", borderBottom: "1px solid #E7DED6", background: "#FAF6F2", padding: "22px 5vw", display: "flex", justifyContent: "center", gap: 42, flexWrap: "wrap" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-head)", color: "#1E2A33" }}>7+</div>
          <div style={{ color: "#8B959D", fontSize: 12 }}>Sources de données</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-head)", color: "#1E2A33" }}>4</div>
          <div style={{ color: "#8B959D", fontSize: 12 }}>Agents IA</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-head)", color: "#1E2A33" }}>3D</div>
          <div style={{ color: "#8B959D", fontSize: 12 }}>Jumeau Numérique</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-head)", color: "#1E2A33" }}>🏦</div>
          <div style={{ color: "#8B959D", fontSize: 12 }}>Décision Bancaire</div>
        </div>
      </div>

      {/* Features */}
      <section style={{ maxWidth: 1180, margin: "0 auto", padding: "70px 5vw", textAlign: "center" }}>
        <div className="section-eyebrow">Fonctionnalités</div>
        <h2 className="section-title">Un diagnostic complet en un clic</h2>
        <p className="section-lead" style={{ margin: "0 auto 46px" }}>
          De la collecte des données publiques à la visualisation 3D, en passant par le scoring et la décision bancaire.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 22, textAlign: "left" }}>
          {[
            { icon: "🌍", title: "Données Officielles", desc: "Géorisques, BDNB, IGN, Open-Meteo, DVF — des sources fiables et gratuites." },
            { icon: "🎯", title: "Scoring Multi-Risques", desc: "RGA, inondation, canicule, tempête, feu de forêt — 7 zones du bâtiment analysées." },
            { icon: "🏗️", title: "Jumeau Numérique 3D", desc: "Visualisation interactive du bien avec codes couleur par niveau de risque." },
            { icon: "💰", title: "Décision Bancaire", desc: "Intégration du scoring dans la décision de crédit immobilier avec calcul actuariel." },
            { icon: "📋", title: "Recommandations", desc: "Travaux priorisés avec coûts estimés, aides mobilisables et gain de résilience." },
            { icon: "🔮", title: "Projection 2050", desc: "Anticipez l'évolution des risques climatiques à horizon 2050." },
          ].map((f, i) => (
            <div key={i} style={{ background: "#FFFFFF", border: "1px solid #E7DED6", borderRadius: 6, padding: "26px 24px", transition: "box-shadow .2s, transform .2s" }}>
              <div style={{ width: 46, height: 46, borderRadius: 6, background: "#FFE4DA", color: "#FF6B4A", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, marginBottom: 16 }}>
                {f.icon}
              </div>
              <h3 style={{ fontSize: 17, color: "#1E2A33", marginBottom: 8, fontWeight: 700 }}>{f.title}</h3>
              <p style={{ fontSize: 13.5, color: "#4B5760", lineHeight: 1.55, margin: 0 }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section style={{ textAlign: "center", padding: "40px 5vw 80px" }}>
        <button onClick={onStart} className="btn-primary" style={{ fontSize: 16, padding: "16px 32px" }}>
          🔍 Diagnostiquer mon bien maintenant
        </button>
      </section>
    </div>
  );
}
