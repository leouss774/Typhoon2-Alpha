import type { Recommandation } from "../../types/models";
import CostBreakdown from "./CostBreakdown";

interface RecommendationListProps {
  recommandations: Recommandation[];
}

export default function RecommendationList({ recommandations }: RecommendationListProps) {
  const totalBas = recommandations.reduce((s, r) => s + r.cout_estime_bas, 0);
  const totalHaut = recommandations.reduce((s, r) => s + r.cout_estime_haut, 0);
  const gainMoyen =
    recommandations.reduce((s, r) => s + r.gain_resilience_pct, 0) / recommandations.length || 0;

  return (
    <div className="recommendations">
      <h3>📋 Recommandations de travaux</h3>
      <div className="recommendations-summary">
        <span>Coût total estimé : <strong>{totalBas.toLocaleString("fr-FR")}€ – {totalHaut.toLocaleString("fr-FR")}€</strong></span>
        <span>Gain résilience moyen : <strong>{gainMoyen.toFixed(0)}%</strong></span>
      </div>
      <div className="recommendations-list">
        {recommandations.map((rec, i) => (
          <div key={i} className={`recommendation-item priority-${rec.priorite}`}>
            <div className="recommendation-header">
              <span className="recommendation-priority">#{rec.priorite}</span>
              <h4>{rec.titre}</h4>
              <span className="recommendation-gain">+{rec.gain_resilience_pct}%</span>
            </div>
            <p className="recommendation-desc">{rec.description}</p>
          </div>
        ))}
      </div>
      <CostBreakdown recommandations={recommandations} />
    </div>
  );
}
