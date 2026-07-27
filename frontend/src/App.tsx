import { useState, useEffect } from "react";
import Dashboard from "./components/Dashboard/Dashboard";
import ClientForm from "./components/Form/ClientForm";

type Page = "form" | "dashboard";

function App() {
  // 1. Initialiser le state depuis l'URL (Deep Linking / Rafraichissement)
  const [page, setPage] = useState<Page>(() => {
    const params = new URLSearchParams(window.location.search);
    return (params.get("page") as Page) || "dashboard";
  });
  
  const [sessionId, setSessionId] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("sessionId") || "demo-session-001";
  });

  const isBankRoute = window.location.pathname.startsWith("/bank");

  // 2. Synchroniser l'URL avec le state à chaque changement (History API)
  useEffect(() => {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("page", page);
    currentUrl.searchParams.set("sessionId", sessionId);
    window.history.replaceState({}, "", currentUrl.toString());
  }, [page, sessionId]);

  const handleAnalyseLancee = (newSessionId: string) => {
    setSessionId(newSessionId);
    setPage("dashboard");
  };

  return (
    <div className="app" style={{ minHeight: "100vh", background: "#04070c" }}>
      <header className="app-header" style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "12px 24px", background: "rgba(6,14,26,0.9)",
        borderBottom: "1px solid #1c5a9c"
      }}>
        <div className="app-logo" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 24 }}>{isBankRoute ? "🏦" : "🌪️"}</span>
          <h1 style={{ margin: 0, fontSize: 20, color: "#4da6ff" }}>
            {isBankRoute ? "Typhoon - Portail Bancaire" : "Typhoon"}
          </h1>
        </div>
        <nav className="app-nav" style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => setPage("dashboard")}
            style={{
              padding: "8px 16px", borderRadius: 6, border: "1px solid #1c5a9c",
              background: page === "dashboard" ? "#4da6ff" : "rgba(20,40,65,0.8)",
              color: page === "dashboard" ? "#04070c" : "#cfe8ff",
              fontSize: 13, fontWeight: page === "dashboard" ? 700 : 400,
              cursor: "pointer", transition: "all .15s"
            }}
          >Dashboard</button>
          {isBankRoute && (
            <button
              onClick={() => setPage("form")}
              style={{
                padding: "8px 16px", borderRadius: 6, border: "1px solid #1c5a9c",
                background: page === "form" ? "#4da6ff" : "rgba(20,40,65,0.8)",
                color: page === "form" ? "#04070c" : "#cfe8ff",
                fontSize: 13, fontWeight: page === "form" ? 700 : 400,
                cursor: "pointer", transition: "all .15s"
              }}
            >Nouvelle analyse crédit</button>
          )}
          <button
            onClick={() => window.location.href = isBankRoute ? "/" : "/bank"}
            style={{
              padding: "8px 16px", borderRadius: 6, border: "1px dashed #d29922",
              background: isBankRoute ? "rgba(210,153,34,0.2)" : "transparent",
              color: "#d29922",
              fontSize: 13, fontWeight: 700,
              cursor: "pointer", transition: "all .15s", marginLeft: "10px"
            }}
          >
            {isBankRoute ? "Quitter Portail Banque" : "Accès Banquier"}
          </button>
        </nav>
      </header>

      <main style={{ paddingTop: 24 }}>
        {page === "dashboard" && <Dashboard sessionId={sessionId} isBankRoute={isBankRoute} />}
        {page === "form" && <ClientForm onAnalyseLancee={handleAnalyseLancee} isBankRoute={isBankRoute} />}
      </main>
    </div>
  );
}

export default App;
