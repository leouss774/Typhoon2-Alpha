interface RiskItem {
  nom: string;
  score: number;
  niveau: string;
  zone_impactee: string;
  description: string;
}

interface RiskRadarProps {
  risques: RiskItem[];
}  const AXIS_CONFIG = [
  { label: "Inondation", key: "inondation", max: 100 },
  { label: "Secheresse", key: "rga", max: 100 },
  { label: "Canicule", key: "canicule", max: 100 },
  { label: "Tempete", key: "tempete", max: 100 },
  { label: "Seisme", key: "seisme", max: 100 },
  { label: "Feu", key: "feu", max: 100 },
];

function normaliserNom(nom: string): string {
  const n = nom.toLowerCase();
  if (n.includes("inond") || n.includes("crue")) return "inondation";
  if (n.includes("séche") || n.includes("rga") || n.includes("retrait")) return "rga";
  if (n.includes("canic") || n.includes("chaleur")) return "canicule";
  if (n.includes("tempê") || n.includes("vent") || n.includes("cyclone")) return "tempete";
  if (n.includes("séism") || n.includes("tremblement")) return "seisme";
  if (n.includes("feu") || n.includes("forêt") || n.includes("incendie")) return "feu";
  return n;
}

export default function RiskRadar({ risques }: RiskRadarProps) {
  if (!risques || risques.length === 0) return null;

  // Mapper les risques aux axes
  const scores: Record<string, number> = {};
  for (const r of risques) {
    const key = normaliserNom(r.nom);
    scores[key] = r.score;
  }

  const W = 240;
  const H = 240;
  const CX = W / 2;
  const CY = H / 2;
  const R = 85;
  const N = AXIS_CONFIG.length;
  const ANGLE_STEP = (2 * Math.PI) / N;
  // Démarrer à -90° (vers le haut)
  const START_ANGLE = -Math.PI / 2;

  function coords(angle: number, radius: number): [number, number] {
    return [CX + radius * Math.cos(angle), CY + radius * Math.sin(angle)];
  }

  // Centiles (25%, 50%, 75%)
  const centiles = [0.25, 0.5, 0.75];

  // Couleur selon score
  function scoreColor(s: number): string {
    if (s >= 60) return "#ef4444";
    if (s >= 35) return "#eab308";
    return "#22c55e";
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        {/* Grille des centiles */}
        {centiles.map((c) => {
          const r = R * c;
          const pts = Array.from({ length: N }, (_, i) =>
            coords(START_ANGLE + i * ANGLE_STEP, r)
          );
          return (
            <polygon
              key={c}
              points={pts.map((p) => p.join(",")).join(" ")}
              fill="none"
              stroke="#30363d"
              strokeWidth="0.5"
              strokeDasharray="3,3"
            />
          );
        })}

        {/* Lignes des axes */}
        {AXIS_CONFIG.map((_, i) => {
          const [x, y] = coords(START_ANGLE + i * ANGLE_STEP, R);
          return <line key={i} x1={CX} y1={CY} x2={x} y2={y} stroke="#30363d" strokeWidth="0.5" />;
        })}

        {/* Labels des axes */}
        {AXIS_CONFIG.map((axis, i) => {
          const [x, y] = coords(START_ANGLE + i * ANGLE_STEP, R + 18);
          return (
            <text
              key={i}
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="#8b949e"
              fontSize="8"
              fontWeight="500"
            >
              {axis.label}
            </text>
          );
        })}

        {/* Zone de données */}
        {(() => {
          const vals = AXIS_CONFIG.map((a) => (scores[a.key] || 0) / a.max);
          const pts = vals.map((v, i) => coords(START_ANGLE + i * ANGLE_STEP, R * v));
          return (
            <>
              <polygon
                points={pts.map((p) => p.join(",")).join(" ")}
                fill="rgba(20, 184, 166, 0.15)"
                stroke="#14b8a6"
                strokeWidth="2"
              />
              {pts.map(([x, y], i) => (
                <circle key={i} cx={x} cy={y} r="4" fill={scoreColor(vals[i] * 100)} stroke="#1e293b" strokeWidth="1.5" />
              ))}
            </>
          );
        })()}
      </svg>

      {/* Légende compacte */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", justifyContent: "center", marginTop: "4px" }}>
        {AXIS_CONFIG.map((axis) => {
          const s = scores[axis.key] || 0;
          return (
            <div
              key={axis.key}
              style={{
                padding: "2px 8px", borderRadius: "10px", fontSize: "0.6rem",
                background: `${scoreColor(s)}18`,
                color: scoreColor(s),
                border: `1px solid ${scoreColor(s)}44`,
                fontWeight: 600,
              }}
              title={`${axis.label}: ${s}/100`}
            >
              {s}
              <span style={{ opacity: 0.6 }}>/{axis.max}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
