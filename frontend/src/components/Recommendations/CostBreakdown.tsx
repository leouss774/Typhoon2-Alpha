import type { Recommandation } from "../../types/models";

interface CostBreakdownProps {
  recommandations: Recommandation[];
}

export default function CostBreakdown({ recommandations }: CostBreakdownProps) {
  return (
    <div className="cost-breakdown">
      <h4>Détail des coûts</h4>
      <table className="cost-table">
        <thead>
          <tr>
            <th>Travaux</th>
            <th>Estimation basse</th>
            <th>Estimation haute</th>
            <th>Gain résilience</th>
          </tr>
        </thead>
        <tbody>
          {recommandations.map((rec, i) => (
            <tr key={i}>
              <td>{rec.titre}</td>
              <td>{rec.cout_estime_bas.toLocaleString("fr-FR")}€</td>
              <td>{rec.cout_estime_haut.toLocaleString("fr-FR")}€</td>
              <td>+{rec.gain_resilience_pct}%</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td><strong>Total</strong></td>
            <td><strong>{recommandations.reduce((s, r) => s + r.cout_estime_bas, 0).toLocaleString("fr-FR")}€</strong></td>
            <td><strong>{recommandations.reduce((s, r) => s + r.cout_estime_haut, 0).toLocaleString("fr-FR")}€</strong></td>
            <td><strong>+{(recommandations.reduce((s, r) => s + r.gain_resilience_pct, 0) / recommandations.length || 0).toFixed(0)}%</strong></td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
