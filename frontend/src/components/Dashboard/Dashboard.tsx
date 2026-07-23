import { useAnalysis } from "../../hooks/useAnalysis";
import ScoreGauge from "./ScoreGauge";
import RiskCards from "./RiskCards";
import PropertyMap from "./PropertyMap";
import DigitalTwin from "../DigitalTwin/DigitalTwin";
import RecommendationList from "../Recommendations/RecommendationList";
import ChatInterface from "../Chat/ChatInterface";

interface DashboardProps {
  sessionId: string;
}

export default function Dashboard({ sessionId }: DashboardProps) {
  const { data, loading, error } = useAnalysis(sessionId);

  if (loading) {
    return (
      <div className="dashboard-loading">
        <div className="spinner" />
        <p>Analyse en cours...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-error">
        <p>❌ {error}</p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h2>Diagnostic de résilience climatique</h2>
        <p className="dashboard-address">{data.adresse}</p>
      </header>

      <div className="dashboard-grid">
        {/* Ligne 1 : Score + Carte */}
        <div className="dashboard-row">
          <ScoreGauge score={data.score_global} niveau={data.niveau_risque} />
          <PropertyMap lat={data.coordonnees.lat} lng={data.coordonnees.lng} adresse={data.adresse} />
        </div>

        {/* Ligne 2 : Risques + Jumeau numérique */}
        <div className="dashboard-row">
          <RiskCards
            scores={data.scores_par_alea}
            dominants={data.risques_dominants}
          />
          <DigitalTwin
            scores={data.scores_par_alea}
            projections={data.projections_2050}
          />
        </div>

        {/* Ligne 3 : Recommandations + Chat */}
        <div className="dashboard-row dashboard-row-full">
          <RecommendationList recommandations={data.recommandations} />
          <ChatInterface sessionId={sessionId} />
        </div>
      </div>
    </div>
  );
}
