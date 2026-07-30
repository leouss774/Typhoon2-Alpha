import { useEffect, useState } from "react";

interface AnneeData {
  annee: number;
  prix_m2_median: number;
  prix_m2_moyen: number;
  nb_transactions: number;
  valeur_moyenne: number;
  valeur_min: number;
  valeur_max: number;
}

interface PriceChartProps {
  adresse: string;
  type_bien?: string;
  surface?: number;
}

export default function PriceChart({ adresse, type_bien = "Maison", surface = 100 }: PriceChartProps) {
  const [data, setData] = useState<AnneeData[]>([]);
  const [tendance, setTendance] = useState("");
  const [loading, setLoading] = useState(false);
  const [prixActuel, setPrixActuel] = useState<number | null>(null);
  const [nbTx, setNbTx] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!adresse || adresse === "Adresse inconnue") return;

    setLoading(true);
    setError(null);

    fetch("/api/bank/market-trends", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ adresse, type_bien, surface }),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((json) => {
        setData(json.evolution || []);
        setTendance(json.tendance || "stable");
        setPrixActuel(json.valeur_actuelle);
        setNbTx(json.nb_transactions || 0);
      })
      .catch((err) => {
        console.warn("Erreur chargement PriceChart:", err.message);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }, [adresse, type_bien, surface]);

  if (loading) {
    return (
      <div className="bank-section" style={{ textAlign: "center", padding: "30px", color: "var(--color-text-secondary)" }}>
        ⏳ Chargement de l'évolution des prix...
      </div>
    );
  }

  if (error || data.length === 0) {
    return null; // Silently hide if no data
  }

  // Trouver les valeurs min/max pour l'échelle
  const maxPm2 = Math.max(...data.map((d) => d.prix_m2_median)) * 1.15;
  const minPm2 = Math.min(...data.map((d) => d.prix_m2_median)) * 0.85;
  const range = maxPm2 - minPm2;

  const formatEur = (val: number) =>
    new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(val);

  // Couleur de la tendance
  const tendanceColor = tendance.includes("hausse")
    ? "#22c55e"
    : tendance.includes("baisse")
    ? "#ef4444"
    : "#eab308";

  // Largeur/hauteur du SVG
  const W = 600;
  const H = 220;
  const PAD = { top: 20, right: 20, bottom: 45, left: 60 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top - PAD.bottom;

  const barWidth = Math.max(30, Math.min(60, chartW / data.length - 12));

  return (
    <div className="bank-section">
      <h3 className="bank-section-title" style={{ color: "var(--color-primary)", marginBottom: "4px" }}>
        📈 Évolution du prix au m² — Données DVF réelles
      </h3>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap" }}>
        <span
          style={{
            padding: "4px 12px",
            borderRadius: "12px",
            fontSize: "0.75rem",
            fontWeight: 700,
            background: `${tendanceColor}18`,
            color: tendanceColor,
            border: `1px solid ${tendanceColor}44`,
          }}
        >
          {tendance.includes("hausse") && "📈"}
          {tendance.includes("baisse") && "📉"}
          {tendance.includes("stable") && "➡️"}{" "}
          Tendance : {tendance}
        </span>
        {prixActuel && (
          <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
            Prix actuel estimé : <strong style={{ color: "var(--color-text)" }}>{formatEur(prixActuel)}</strong>
          </span>
        )}
        <span style={{ fontSize: "0.7rem", color: "var(--color-text-secondary)", marginLeft: "auto" }}>
          {nbTx > 0 && `${nbTx} transaction(s)`} • {data.length} année(s)
        </span>
      </div>

      <div style={{ overflowX: "auto", paddingBottom: "4px" }}>
        <svg viewBox={`0 0 ${W} ${H + 30}`} style={{ width: "100%", maxWidth: `${W}px`, height: "auto", display: "block", margin: "0 auto" }}>
          {/* Ligne de base */}
          <line x1={PAD.left} y1={PAD.top + chartH} x2={PAD.left + chartW} y2={PAD.top + chartH} stroke="#30363d" strokeWidth="1" />

          {/* Barres + labels axe Y */}
          {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
            const y = PAD.top + chartH - chartH * frac;
            const val = minPm2 + range * frac;
            return (
              <g key={frac}>
                <line x1={PAD.left} y1={y} x2={PAD.left + chartW} y2={y} stroke="#30363d" strokeWidth="0.5" strokeDasharray="4,4" />
                <text x={PAD.left - 8} y={y + 4} textAnchor="end" fill="#8b949e" fontSize="10">
                  {Math.round(val)}€
                </text>
              </g>
            );
          })}

          {/* Barres par année */}
          {data.map((d, i) => {
            const x = PAD.left + (chartW / data.length) * i + (chartW / data.length - barWidth) / 2;
            const barH = ((d.prix_m2_median - minPm2) / range) * chartH;
            const y = PAD.top + chartH - barH;
            const isLatest = i === data.length - 1;

            // Couleur: dégradé du vert (récent) au bleu (ancien)
            const intensity = isLatest ? 0 : 0.3 + (i / data.length) * 0.5;
            const r = 15 + Math.round(intensity * 100);
            const g = 118 + Math.round((1 - intensity) * 80);
            const b = 110 + Math.round((1 - intensity) * 80);
            // S'assurer que les valeurs restent dans [0,255]
            const barColor = `rgb(${Math.min(50, r)}, ${Math.min(180, g)}, ${Math.min(180, b)})`;
            const barColorLatest = "rgb(255, 107, 74)";

            return (
              <g key={d.annee}>
                {/* Barre */}
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={barH > 0 ? barH : 2}
                  fill={isLatest ? barColorLatest : barColor}
                  rx="3"
                  opacity={isLatest ? 1 : 0.7}
                >
                  <title>
                    {d.annee} : {d.prix_m2_median}€/m² ({d.nb_transactions} transactions)
                  </title>
                </rect>

                {/* Valeur au-dessus de la barre */}
                <text
                  x={x + barWidth / 2}
                  y={y - 6}
                  textAnchor="middle"
                  fill={isLatest ? "#FF6B4A" : "#8b949e"}
                  fontSize={isLatest ? "11" : "9"}
                  fontWeight={isLatest ? "700" : "400"}
                >
                  {Math.round(d.prix_m2_median)}€
                </text>

                {/* Année en dessous */}
                <text
                  x={x + barWidth / 2}
                  y={PAD.top + chartH + 16}
                  textAnchor="middle"
                  fill={isLatest ? "var(--color-ink)" : "var(--color-text-secondary)"}
                  fontSize="10"
                  fontWeight={isLatest ? "700" : "400"}
                >
                  {d.annee}
                </text>

                {/* Ligne de tendance (connexion entre les barres) */}
                {i > 0 && (
                  <line
                    x1={PAD.left + (chartW / data.length) * (i - 1) + (chartW / data.length - barWidth) / 2 + barWidth / 2}
                    y1={PAD.top + chartH - ((data[i - 1].prix_m2_median - minPm2) / range) * chartH}
                    x2={x + barWidth / 2}
                    y2={y}
                    stroke="#FF6B4A"
                    strokeWidth="2"
                    strokeDasharray={isLatest ? "" : "4,3"}
                    opacity="0.5"
                  />
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Légende */}
      <div style={{ display: "flex", gap: "16px", justifyContent: "center", fontSize: "0.7rem", color: "var(--color-text-secondary)", marginTop: "8px" }}>
        <span>📊 Prix médian au m² par année (transactions réelles DVF)</span>
        <span>🔗 Ligne de tendance</span>
      </div>
    </div>
  );
}
