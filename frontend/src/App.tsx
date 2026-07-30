import { useState, useEffect, useCallback } from "react";
import Dashboard from "./components/Dashboard/Dashboard";
import ClientForm from "./components/Form/ClientForm";
import HomeScreen from "./components/Home/HomeScreen";

type Page = "home" | "form" | "dashboard";

function App() {
  const isBankRoute = window.location.pathname.startsWith("/bank");

  // On lit les params URL au premier rendu (permet le refresh / le deep-linking)
  const [page, setPage] = useState<Page>(() => {
    const params = new URLSearchParams(window.location.search);
    if (isBankRoute) {
      // Route banque : par défaut le formulaire, mais on respecte le param ?page=
      return (params.get("page") as Page) || "form";
    }
    // Route publique : page d'accueil par défaut
    return (params.get("page") as Page) || "home";
  });

  const [sessionId, setSessionId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    const sid = params.get("sessionId");
    if (sid) return sid;
    return isBankRoute ? null : null; // Pas de session par défaut, on commence par l'accueil
  });

  // Compteur de clés pour forcer le remount du Dashboard à chaque nouvelle analyse
  const [dashboardKey, setDashboardKey] = useState(0);

  // Synchroniser l'URL avec le state (History API)
  useEffect(() => {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("page", page);
    if (sessionId) {
      currentUrl.searchParams.set("sessionId", sessionId);
    } else {
      currentUrl.searchParams.delete("sessionId");
    }
    window.history.replaceState({}, "", currentUrl.toString());
  }, [page, sessionId]);

  const handleAnalyseLancee = useCallback((newSessionId: string) => {
    // Nettoie l'ancienne analyse du sessionStorage avant de charger la nouvelle
    if (sessionId && isBankRoute) {
      sessionStorage.removeItem("typhoon_bank_" + sessionId);
    }
    setSessionId(newSessionId);
    setDashboardKey(k => k + 1); // force Dashboard à se remonter à zéro
    setPage("dashboard");
  }, [sessionId, isBankRoute]);

  const handleStartDiagnostic = useCallback(() => {
    setSessionId(null);
    setPage("form");
  }, []);

  // Masquer le header sur la page d'accueil (elle a son propre header)
  const isHome = page === "home" && !isBankRoute;

  if (isHome) {
    return <HomeScreen onStart={handleStartDiagnostic} />;
  }

  return (
    <div className="app" style={{ minHeight: "100vh", background: "#FFFFFF" }}>
      <header className="app-header" style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "12px 24px", background: "rgba(255,255,255,0.92)",
        borderBottom: "1px solid #E7DED6", backdropFilter: "blur(10px)"
      }}>
        <a href={isBankRoute ? "/bank" : "/"} style={{ textDecoration: "none" }}>
          <div className="app-logo" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div className="mark" style={{
              width: 38, height: 38, borderRadius: 10,
              background: "linear-gradient(135deg, #FF9269, #FF6B4A)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 19, boxShadow: "0 0 18px rgba(255,107,74,0.45)"
            }}>
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2 4 5v6c0 5 3.5 9 8 11 4.5-2 8-6 8-11V5z"/>
                <path d="m9 12 2 2 4-4"/>
              </svg>
            </div>
            <div>
              <div className="name" style={{ fontFamily: "'Source Serif 4', Georgia, serif", color: "#1E2A33", fontSize: 19, fontWeight: 700, letterSpacing: "0.02em" }}>
                {isBankRoute ? "Typhoon Banque" : "Typhoon"}
              </div>
              <div className="baseline" style={{ color: "#FF6B4A", fontSize: 10.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }}>
                {isBankRoute ? "Analyse de Crédit" : "Diagnostic Climatique"}
              </div>
            </div>
          </div>
        </a>
        <nav className="app-nav" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {!isBankRoute && (
            <button
              onClick={() => setPage("home")}
              style={{
                padding: "8px 16px", borderRadius: 8, border: "1px solid #E7DED6",
                background: "none",
                color: "#4B5760",
                fontSize: 13, fontWeight: 700,
                cursor: "pointer", transition: "all .15s"
              }}
            >Accueil</button>
          )}
          <button
            onClick={() => setPage("dashboard")}
            style={{
              padding: "8px 16px", borderRadius: 8, border: "1px solid #E7DED6",
              background: page === "dashboard" ? "#FF6B4A" : "none",
              color: page === "dashboard" ? "#FFFFFF" : "#4B5760",
              fontSize: 13, fontWeight: 700,
              cursor: "pointer", transition: "all .15s"
            }}
          >Dashboard</button>
          {isBankRoute && (
            <button
              onClick={() => { setSessionId(null); setPage("form"); }}
              style={{
                padding: "8px 16px", borderRadius: 8, border: "1px solid #E7DED6",
                background: page === "form" ? "#FF6B4A" : "none",
                color: page === "form" ? "#FFFFFF" : "#4B5760",
                fontSize: 13, fontWeight: 700,
                cursor: "pointer", transition: "all .15s"
              }}
            >Nouvelle analyse crédit</button>
          )}
          <button
            onClick={() => window.location.href = isBankRoute ? "/" : "/bank"}
            className="btn-ghost"
            style={{
              padding: "8px 16px", borderRadius: 8,
              border: "1px dashed #E7DED6",
              background: "transparent",
              color: "#FF6B4A", fontSize: 13, fontWeight: 700,
              cursor: "pointer", transition: "all .15s", marginLeft: 10
            }}
          >
            {isBankRoute ? "← Retour site principal" : "🏦 Accès Banquier"}
          </button>
        </nav>
      </header>

      <main style={{ paddingTop: 24 }}>
        {page === "dashboard" && <Dashboard key={dashboardKey} sessionId={sessionId} isBankRoute={isBankRoute} />}
        {page === "form" && <ClientForm onAnalyseLancee={handleAnalyseLancee} isBankRoute={isBankRoute} />}
      </main>
    </div>
  );
}

export default App;
