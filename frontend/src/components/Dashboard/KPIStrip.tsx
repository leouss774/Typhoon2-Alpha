interface KPIStripProps {
  valeur_marche: number;
  valeur_ajustee: number;
  score: number;
  taux: number;
  confiance: number;
  decote: number;
}

function formatEur(val: number): string {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency", currency: "EUR", maximumFractionDigits: 0,
  }).format(val);
}

export default function KPIStrip({
  valeur_marche, valeur_ajustee, score, taux, confiance, decote,
}: KPIStripProps) {
  const scoreColor = score >= 60 ? "#ef4444" : score >= 35 ? "#eab308" : "#22c55e";
  const confianceColor = confiance >= 80 ? "#22c55e" : confiance >= 50 ? "#eab308" : "#ef4444";

  const kpis = [
    {
      label: "Score Risque",
      value: `${score}/100`,
      color: scoreColor,
      tooltip: "Score de risque bancaire global (0=faible, 100=eleve)",
    },
    {
      label: "Valeur DVF",
      value: formatEur(valeur_marche),
      color: "var(--color-text)",
      tooltip: "Valeur de marche estimee via DGFiP",
    },
    {
      label: "Garantie",
      value: formatEur(valeur_ajustee),
      color: "var(--color-primary)",
      tooltip: "Valeur de garantie finale apres decote risque",
    },
    {
      label: "Taux",
      value: `${taux?.toFixed(2) || "N/A"}%`,
      color: scoreColor,
      tooltip: "Taux d'interet propose (tout compris)",
    },
    {
      label: "Decote",
      value: decote === 0 ? "Aucune" : `-${decote}%`,
      color: decote === 0 ? "#22c55e" : "#ef4444",
      tooltip: "Decote appliquee pour risque climatique",
    },
    {
      label: "Confiance",
      value: `${confiance}%`,
      color: confianceColor,
      tooltip: "Indice de confiance dans les donnees DVF",
    },
  ];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
        gap: "8px",
        marginBottom: "4px",
      }}
    >
      {kpis.map((kpi) => (
        <div
          key={kpi.label}
          title={kpi.tooltip}
          style={{
            padding: "10px 12px",
            borderRadius: "10px",
            background: "var(--color-bg)",
            border: `1px solid ${kpi.color}22`,
            textAlign: "center",
            cursor: "help",
            transition: "all 0.2s ease",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = `${kpi.color}55`;
            e.currentTarget.style.transform = "translateY(-2px)";
            e.currentTarget.style.boxShadow = `0 4px 12px ${kpi.color}11`;
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = `${kpi.color}22`;
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow = "none";
          }}
        >
          <div style={{ width: "20px", height: "3px", borderRadius: "2px", background: kpi.color, margin: "0 auto 4px auto" }} />
          <div style={{ fontSize: "0.55rem", color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "2px" }}>
            {kpi.label}
          </div>
          <div style={{ fontSize: "0.95rem", fontWeight: 700, color: kpi.color }}>
            {kpi.value}
          </div>
        </div>
      ))}
    </div>
  );
}
