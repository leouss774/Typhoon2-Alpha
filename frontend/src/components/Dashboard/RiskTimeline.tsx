interface ProjectionRisque {
  horizon: string;
  score_actuel: number;
  score_projete: number;
  aggravation: number;
  scenario: string;
  zones_projetees: Record<string, { risque_projete: number; evolution: string }>;
}

interface RiskTimelineProps {
  projection: ProjectionRisque | null;
}

function scoreColor(s: number): string {
  if (s >= 60) return "#ef4444";
  if (s >= 35) return "#eab308";
  return "#22c55e";
}

function scoreNiveau(s: number): string {
  if (s >= 60) return "Élevé";
  if (s >= 35) return "Modéré";
  return "Faible";
}

export default function RiskTimeline({ projection }: RiskTimelineProps) {
  if (!projection) return null;

  const { score_actuel, score_projete, aggravation, scenario, zones_projetees } = projection;

  // Projeter les scores intermédiaires (2030, 2035, 2040, 2045)
  const annees = [2025, 2030, 2035, 2040, 2045, 2050];
  const delta = (score_projete - score_actuel) / 5; // par palier de 5 ans
  const scores = annees.map((annee, i) => ({
    annee,
    score: Math.round(score_actuel + delta * i),
  }));

  const barMaxH = 140;
  const barW = 28;

  return (
    <div className="bank-section">
      <h3 className="bank-section-title" style={{ color: "var(--color-risk-eleve)", marginBottom: "4px" }}>
        Projection d'Evolution du Risque
        <span style={{ marginLeft: "8px", fontSize: "0.65rem", fontWeight: 400, color: "var(--color-text-secondary)" }}>
          — Horizon 2050
        </span>
      </h3>

      <div style={{ display: "flex", gap: "20px", flexWrap: "wrap" }}>
        {/* Graphique à barres */}
        <div style={{ flex: 1, minWidth: "280px" }}>
          <div style={{ display: "flex", alignItems: "flex-end", gap: "8px", height: `${barMaxH + 40}px`, padding: "0 8px" }}>
            {scores.map((s, idx) => {
              const h = Math.max(4, (s.score / 100) * barMaxH);
              const color = scoreColor(s.score);
              const isLast = s.annee === 2050;
              return (
                <div
                  key={s.annee}
                  style={{
                    flex: 1,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "flex-end",
                    height: "100%",
                  }}
                >
                  {/* Valeur */}
                  <div style={{ fontSize: isLast ? "0.8rem" : "0.65rem", fontWeight: isLast ? 700 : 400, color, marginBottom: "4px" }}>
                    {s.score}
                  </div>
                  {/* Barre */}
                  <div
                    style={{
                      width: barW,
                      height: h,
                      background: `linear-gradient(180deg, ${color}, ${color}88)`,
                      borderRadius: "4px 4px 0 0",
                      opacity: isLast ? 1 : 0.5 + (1 - Math.abs(idx - 3) / 5) * 0.5,
                      transition: "height 0.3s",
                      position: "relative",
                    }}
                  />
                  {/* Année */}
                  <div style={{ fontSize: "0.6rem", color: isLast ? "var(--color-text)" : "var(--color-text-secondary)", fontWeight: isLast ? 700 : 400, marginTop: "4px" }}>
                    {s.annee}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Métriques à droite */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", minWidth: "160px" }}>
          <div style={{ padding: "10px", borderRadius: "8px", background: "var(--color-bg)", border: "1px solid #30363d", textAlign: "center" }}>
            <div style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Score 2025
            </div>
            <div style={{ fontSize: "1.2rem", fontWeight: 700, color: scoreColor(score_actuel) }}>
              {score_actuel}
              <span style={{ fontSize: "0.65rem", color: "var(--color-text-secondary)", fontWeight: 400 }}>/100</span>
            </div>
            <div style={{ fontSize: "0.6rem", color: scoreColor(score_actuel) }}>
              {scoreNiveau(score_actuel)}
            </div>
          </div>

          <div style={{ padding: "10px", borderRadius: "8px", background: aggravation > 0 ? "rgba(239,68,68,0.08)" : "var(--color-bg)", border: `1px solid ${aggravation > 0 ? "#ef444444" : "#30363d"}`, textAlign: "center" }}>
            <div style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Projection 2050
            </div>
            <div style={{ fontSize: "1.2rem", fontWeight: 700, color: scoreColor(score_projete) }}>
              {score_projete}
              <span style={{ fontSize: "0.65rem", color: "var(--color-text-secondary)", fontWeight: 400 }}>/100</span>
            </div>
            <div style={{ fontSize: "0.6rem", color: scoreColor(score_projete) }}>
              {scoreNiveau(score_projete)} {aggravation > 0 ? `(+${aggravation} pts)` : ""}
            </div>
          </div>

          {scenario && (
            <div style={{ padding: "6px 10px", borderRadius: "6px", background: "rgba(234,179,8,0.08)", border: "1px solid rgba(234,179,8,0.3)", fontSize: "0.65rem", color: "var(--color-text-secondary)", textAlign: "center" }}>
              Scenario : {scenario}
            </div>
          )}
        </div>
      </div>

      {/* Zones projetées */}
      {Object.keys(zones_projetees || {}).length > 0 && (
        <div style={{ marginTop: "12px", display: "flex", gap: "6px", flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px", marginRight: "4px" }}>
            Par zone :
          </span>
          {Object.entries(zones_projetees).map(([zone, zdata]) => (
            <span
              key={zone}
              style={{
                padding: "2px 8px", borderRadius: "10px", fontSize: "0.6rem", fontWeight: 600,
                background: `${scoreColor(zdata.risque_projete)}18`,
                color: scoreColor(zdata.risque_projete),
                border: `1px solid ${scoreColor(zdata.risque_projete)}44`,
              }}
            >
              {zone}: {zdata.risque_projete}/100 ({zdata.evolution})
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
