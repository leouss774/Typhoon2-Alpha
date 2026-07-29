"use client";

import { useState } from "react";
import ClientForm from "@/components/Form/ClientForm";
import Dashboard from "@/components/Dashboard/Dashboard";

export default function BankPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [page, setPage] = useState<"dashboard" | "form">("form");
  const [dashboardKey, setDashboardKey] = useState(0);

  const handleAnalyseLancee = (newSessionId: string) => {
    setSessionId(newSessionId);
    setDashboardKey((k) => k + 1);
    setPage("dashboard");
  };

  return (
    <div style={{ paddingTop: 24 }}>
      {page === "dashboard" && (
        <Dashboard
          key={dashboardKey}
          sessionId={sessionId}
          isBankRoute={true}
        />
      )}
      {page === "form" && (
        <ClientForm
          onAnalyseLancee={handleAnalyseLancee}
          isBankRoute={true}
        />
      )}
    </div>
  );
}
