import { useState } from "react";
import HouseSection from "./HouseSection";
import RiskHeatmap from "./RiskHeatmap";
import TimelineSlider from "./TimelineSlider";
import RenovationSlider from "./RenovationSlider";

interface DigitalTwinProps {
  scores: Record<string, { score: number; niveau: string; label: string }>;
  projections: Record<string, number>;
}

export default function DigitalTwin({ scores, projections }: DigitalTwinProps) {
  const [annee, setAnnee] = useState(2025);
  const [apresTravaux, setApresTravaux] = useState(false);

  const currentScores = Object.entries(scores).reduce(
    (acc, [key, val]) => ({
      ...acc,
      [key]: annee === 2050 && projections[key] ? projections[key] : val.score,
    }),
    {} as Record<string, number>
  );

  const displayScores = apresTravaux
    ? Object.entries(currentScores).reduce(
        (acc, [key, val]) => ({ ...acc, [key]: Math.max(0, val - val * 0.4) }),
        {} as Record<string, number>
      )
    : currentScores;

  return (
    <div className="digital-twin">
      <h3>Jumeau numérique</h3>
      <div className="digital-twin-visual">
        <RiskHeatmap scores={scores} />
        <HouseSection scores={displayScores} apresTravaux={apresTravaux} />
      </div>
      <div className="digital-twin-controls">
        <TimelineSlider value={annee} onChange={setAnnee} />
        <RenovationSlider value={apresTravaux} onChange={setApresTravaux} />
      </div>
    </div>
  );
}
