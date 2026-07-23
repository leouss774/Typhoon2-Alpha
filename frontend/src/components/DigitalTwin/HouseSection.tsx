interface HouseSectionProps {
  scores: Record<string, number>;
  apresTravaux: boolean;
}

function getColor(score: number): string {
  if (score >= 75) return "#ef4444";
  if (score >= 50) return "#f97316";
  if (score >= 25) return "#eab308";
  return "#22c55e";
}

function getOpacity(score: number): number {
  return 0.3 + (score / 100) * 0.5;
}

export default function HouseSection({ scores, apresTravaux }: HouseSectionProps) {
  const rgaScore = scores.rga ?? scores.RGA ?? 0;
  const inondationScore = scores.inondation ?? scores.Inondation ?? 0;
  const tempeteScore = scores.tempete ?? scores.Tempete ?? 0;

  return (
    <div className="house-section">
      <svg viewBox="0 0 400 350" className="house-svg">
        {/* Sol */}
        <rect x="0" y="280" width="400" height="70" fill="#92400e" opacity="0.3" />
        <text x="200" y="330" textAnchor="middle" fontSize="11" fill="#6b7280">Sol argileux</text>

        {/* Fondations - colorées par risque RGA */}
        <rect
          x="60" y="250" width="280" height="30" rx="3"
          fill={getColor(rgaScore)}
          opacity={getOpacity(rgaScore)}
          stroke={getColor(rgaScore)}
          strokeWidth="2"
        />
        <text x="200" y="268" textAnchor="middle" fontSize="10" fill="white" fontWeight="bold">
          Fondations {rgaScore > 0 ? `${rgaScore}/100` : ""}
        </text>

        {/* Sous-sol / Vide sanitaire */}
        <rect x="70" y="220" width="260" height="30" fill="#e5e7eb" stroke="#d1d5db" strokeWidth="1" />
        <text x="200" y="238" textAnchor="middle" fontSize="9" fill="#6b7280">Sous-sol</text>

        {/* Murs - colorés par risque inondation */}
        <rect
          x="60" y="100" width="280" height="120"
          fill={getColor(inondationScore)}
          opacity={getOpacity(inondationScore) * 0.7}
          stroke={getColor(inondationScore)}
          strokeWidth="2"
        />
        <text x="200" y="155" textAnchor="middle" fontSize="11" fill="white" fontWeight="bold">
          Murs extérieurs
        </text>
        <text x="200" y="170" textAnchor="middle" fontSize="10" fill="white" opacity="0.9">
          {inondationScore > 0 ? `Inondation: ${inondationScore}/100` : ""}
        </text>

        {/* Fenêtres */}
        <rect x="100" y="130" width="40" height="50" rx="3" fill="#bfdbfe" stroke="#60a5fa" strokeWidth="1" opacity="0.8" />
        <rect x="260" y="130" width="40" height="50" rx="3" fill="#bfdbfe" stroke="#60a5fa" strokeWidth="1" opacity="0.8" />

        {/* Porte */}
        <rect x="180" y="140" width="40" height="80" rx="3" fill="#8b5cf6" opacity="0.6" stroke="#7c3aed" strokeWidth="1" />
        <circle cx="212" cy="180" r="2" fill="white" />

        {/* Toit - coloré par risque tempête */}
        <polygon
          points="40,100 200,20 360,100"
          fill={getColor(tempeteScore)}
          opacity={getOpacity(tempeteScore) * 0.8}
          stroke={getColor(tempeteScore)}
          strokeWidth="2"
        />
        <text x="200" y="70" textAnchor="middle" fontSize="11" fill="white" fontWeight="bold">
          Toiture {tempeteScore > 0 ? `${tempeteScore}/100` : ""}
        </text>

        {/* Cheminée */}
        <rect x="270" y="35" width="20" height="40" fill="#9ca3af" rx="2" />
        <rect x="265" y="30" width="30" height="8" fill="#6b7280" rx="2" />

        {/* Éléments décoratifs */}
        {apresTravaux && (
          <>
            {/* Marquage "travaux effectués" */}
            <rect x="140" y="10" width="120" height="24" rx="12" fill="#22c55e" opacity="0.9" />
            <text x="200" y="27" textAnchor="middle" fontSize="11" fill="white" fontWeight="bold">
              ✅ Travaux effectués
            </text>
          </>
        )}
      </svg>
      <div className="house-legend">
        <span><span style={{ color: "#ef4444" }}>●</span> Critique</span>
        <span><span style={{ color: "#f97316" }}>●</span> Élevé</span>
        <span><span style={{ color: "#eab308" }}>●</span> Modéré</span>
        <span><span style={{ color: "#22c55e" }}>●</span> Faible</span>
      </div>
    </div>
  );
}
