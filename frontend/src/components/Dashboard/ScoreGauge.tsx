interface ScoreGaugeProps {
  score: number;
  niveau: string;
}

function getColor(score: number): string {
  if (score >= 75) return "#ef4444";
  if (score >= 50) return "#f97316";
  if (score >= 25) return "#eab308";
  return "#22c55e";
}

function getLabel(niveau: string): string {
  const labels: Record<string, string> = {
    faible: "Faible",
    modéré: "Modéré",
    élevé: "Élevé",
    critique: "Critique",
  };
  return labels[niveau] || niveau;
}

export default function ScoreGauge({ score, niveau }: ScoreGaugeProps) {
  const color = getColor(score);
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="score-gauge-card">
      <h3 className="score-gauge-title">Score global de risque</h3>
      <div className="score-gauge-container">
        <svg width="200" height="200" viewBox="0 0 200 200">
          {/* Cercle de fond */}
          <circle
            cx="100"
            cy="100"
            r={radius}
            fill="none"
            stroke="#e5e7eb"
            strokeWidth="12"
          />
          {/* Cercle de progression */}
          <circle
            cx="100"
            cy="100"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform="rotate(-90 100 100)"
            style={{ transition: "stroke-dashoffset 1s ease-in-out" }}
          />
          {/* Texte au centre */}
          <text x="100" y="90" textAnchor="middle" fontSize="36" fontWeight="bold" fill={color}>
            {score.toFixed(0)}
          </text>
          <text x="100" y="120" textAnchor="middle" fontSize="14" fill="#6b7280">
            / 100
          </text>
        </svg>
        <span className="score-gauge-label" style={{ color }}>
          {getLabel(niveau)}
        </span>
      </div>
    </div>
  );
}
