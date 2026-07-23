import { useState } from "react";
import Dashboard from "./components/Dashboard/Dashboard";

type Page = "form" | "dashboard";

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [sessionId, setSessionId] = useState("demo-session-001");

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-logo">
          <span className="app-logo-icon">🌪️</span>
          <h1>Typhoon</h1>
        </div>
        <nav className="app-nav">
          <button
            className={`nav-btn ${page === "dashboard" ? "active" : ""}`}
            onClick={() => setPage("dashboard")}
          >
            Dashboard
          </button>
          <button
            className={`nav-btn ${page === "form" ? "active" : ""}`}
            onClick={() => setPage("form")}
          >
            Nouvelle analyse
          </button>
        </nav>
      </header>

      <main className="app-main">
        {page === "dashboard" && <Dashboard sessionId={sessionId} />}
        {page === "form" && (
          <div className="form-placeholder">
            <h2>Formulaire client</h2>
            <p>Interface de soumission d'une nouvelle analyse à implémenter.</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
