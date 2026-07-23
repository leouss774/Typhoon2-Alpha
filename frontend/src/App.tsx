import { useState } from "react";
import Dashboard from "./components/Dashboard/Dashboard";
import ClientForm from "./components/Form/ClientForm";

type Page = "form" | "dashboard";

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [sessionId, setSessionId] = useState("demo-session-001");

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
          <span style={{ fontSize: 24 }}>🌪️</span>
          <h1 style={{ margin: 0, fontSize: 20, color: "#4da6ff" }}>Typhoon</h1>
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
          <button
            onClick={() => setPage("form")}
            style={{
              padding: "8px 16px", borderRadius: 6, border: "1px solid #1c5a9c",
              background: page === "form" ? "#4da6ff" : "rgba(20,40,65,0.8)",
              color: page === "form" ? "#04070c" : "#cfe8ff",
              fontSize: 13, fontWeight: page === "form" ? 700 : 400,
              cursor: "pointer", transition: "all .15s"
            }}
          >Nouvelle analyse</button>
        </nav>
      </header>

      <main style={{ paddingTop: 24 }}>
        {page === "dashboard" && <Dashboard sessionId={sessionId} />}
        {page === "form" && <ClientForm onAnalyseLancee={handleAnalyseLancee} />}
      </main>
    </div>
  );
}

export default App;
