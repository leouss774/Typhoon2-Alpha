interface RiskCardsProps {
  scores: Record<string, { score: number; niveau: string; label: string }>;
  dominants: string[];
}

function getColor(niveau: string): string {
  const colors: Record<string, string> = {
    faible: "#22c55e",
    modéré: "#eab308",
    élevé: "#f97316",
    critique: "#ef4444",
  };
  return colors[niveau] || "#6b7280";
}

export default function RiskCards({ scores, dominants }: RiskCardsProps) {
  const topRisks = dominants
    .map((code) => scores[code])
    .filter(Boolean)
    .slice(0, 3);

  return (
    <div className="risk-cards">
      <h3>Risques dominants</h3>
      <div className="risk-cards-list">
        {topRisks.map((risk) => (
          <div
            key={risk.label}
            className="risk-card"
            style={{ borderLeftColor: getColor(risk.niveau) }}
          >
            <div className="risk-card-header">
              <span className="risk-card-label">{risk.label}</span>
              <span
                className="risk-card-badge"
                style={{ backgroundColor: getColor(risk.niveau) }}
              >
                {risk.niveau}
              </span>
            </div>
            <div className="risk-card-score">
              <div
                className="risk-card-bar"
                style={{
                  width: `${risk.score}%`,
                  backgroundColor: getColor(risk.niveau),
                }}
              />
            </div>
            <span className="risk-card-value">{risk.score}/100</span>
          </div>
        ))}
      </div>
    </div>
  );
}
