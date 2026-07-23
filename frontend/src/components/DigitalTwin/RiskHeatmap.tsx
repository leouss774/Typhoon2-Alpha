interface RiskHeatmapProps {
  scores: Record<string, { score: number; niveau: string; label: string }>;
}

function getColor(score: number): string {
  if (score >= 75) return "#ef4444";
  if (score >= 50) return "#f97316";
  if (score >= 25) return "#eab308";
  return "#22c55e";
}

const ALEA_ICONS: Record<string, string> = {
  rga: "🏔️",
  inondation: "🌊",
  tempete: "🌪️",
  feu_foret: "🔥",
  submersion: "🌊",
};

export default function RiskHeatmap({ scores }: RiskHeatmapProps) {
  return (
    <div className="risk-heatmap">
      <h4>Zones de risque</h4>
      <div className="risk-heatmap-rows">
        {Object.entries(scores).map(([code, data]) => (
          <div key={code} className="risk-heatmap-row">
            <span className="risk-heatmap-icon">{ALEA_ICONS[code] || "⚠️"}</span>
            <div className="risk-heatmap-info">
              <span className="risk-heatmap-label">{data.label}</span>
              <div className="risk-heatmap-bar-bg">
                <div
                  className="risk-heatmap-bar-fill"
                  style={{
                    width: `${data.score}%`,
                    backgroundColor: getColor(data.score),
                  }}
                />
              </div>
            </div>
            <span
              className="risk-heatmap-score"
              style={{ color: getColor(data.score) }}
            >
              {data.score}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
