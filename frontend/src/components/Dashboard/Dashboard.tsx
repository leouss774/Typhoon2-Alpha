import React, { useMemo, useEffect, useState } from "react";
import ScoreGauge from "./ScoreGauge";
import RiskCards from "./RiskCards";
import PropertyMap from "./PropertyMap";
import DigitalTwin from "../DigitalTwin/DigitalTwin";
import RecommendationList from "../Recommendations/RecommendationList";
import ChatInterface from "../Chat/ChatInterface";

// Fallback : le JSON statique de démo si pas d'API
import demoData from "../../../assessment_complet.json";

interface DashboardProps {
  sessionId: string;
}

export default function Dashboard({ sessionId }: DashboardProps) {
  const [apiData, setApiData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Tentative de chargement depuis l'API ou localStorage
  useEffect(() => {
    const stored = localStorage.getItem("typhoon_analysis_" + sessionId);
    if (stored) {
      try {
        setApiData(JSON.parse(stored));
        return;
      } catch {}
    }

    // Si sessionId est une session API (commence par "session-"), on appelle le backend
    if (sessionId.startsWith("session-") && sessionId !== "demo-session-001") {
      setLoading(true);
      fetch(`http://localhost:8000/api/analysis/${sessionId}`)
        .then(res => res.ok ? res.json() : null)
        .then(data => { if (data) { setApiData(data); localStorage.setItem("typhoon_analysis_" + sessionId, JSON.stringify(data)); } })
        .catch(err => { console.warn("Fallback vers données démo :", err); })
        .finally(() => setLoading(false));
    }
  }, [sessionId]);

  // Données effectives : API > Demo
  const data = apiData || demoData;
  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "80vh", color: "#4da6ff", fontSize: 18 }}>
        <span>⏳ Analyse en cours...</span>
      </div>
    );
  }

  // 2. L'ADAPTATEUR : On transforme le JSON métier en JSON compatible 3D
  const jumeauPayload = useMemo(() => {
    const zonesBackend = data.recommandations.zones;
    const projectionsBackend = data.recommandations.projection_2050.zones;

    // Zone par défaut (pour les murs manquants comme Sud, Est, Ouest)
    const defaultZone = { 
      risque: 20, 
      niveau: "faible", 
      alea_principal: "Sain", 
      justification: "Aucun risque majeur identifié pour cette exposition.", 
      recommandations: [] 
    };

    // On s'assure que la 3D a bien ses 7 zones pour 2025
    const zones2025 = {
      fondations: zonesBackend.fondations || defaultZone,
      murs_nord: zonesBackend.murs_nord || defaultZone,
      murs_sud: zonesBackend.murs_sud || defaultZone,
      murs_est: zonesBackend.murs_est || defaultZone,
      murs_ouest: zonesBackend.murs_ouest || defaultZone,
      toiture: zonesBackend.toiture || defaultZone,
      sous_sol: zonesBackend.sous_sol || defaultZone,
    };

    // On construit la vue 2050 en fusionnant la base 2025 et les aggravations 2050
    const zones2050: Record<string, any> = {};
    Object.keys(zones2025).forEach((key) => {
      const base = zones2025[key as keyof typeof zones2025];
      const proj = projectionsBackend[key as keyof typeof projectionsBackend];
      
      zones2050[key] = {
        ...base,
        // Si le backend a une projection, on l'utilise, sinon on garde le score 2025
        risque: proj ? proj.risque_projete : base.risque,
        justification: proj ? proj.evolution : base.justification,
        niveau: proj ? (proj.risque_projete >= 60 ? "eleve" : "modere") : base.niveau,
      };
    });

    return {
      score_global: data.analyse_risques.score.global,
      zones: zones2025,
      projection_2050: {
        score_global: data.recommandations.projection_2050.score_global,
        zones: zones2050
      },
      // Dimensions de la maison par défaut pour le frontend (en attendant le module Python)
      geometrie: { largeur_m: 8.5, profondeur_m: 6.0, orientation_deg: 15 }
    };
  }, []);

  return (
    <div className="dashboard" style={{ padding: "20px" }}>
      <header className="dashboard-header" style={{ marginBottom: "20px" }}>
        <h2 style={{ color: "#4da6ff", margin: "0 0 5px 0" }}>Diagnostic de résilience climatique</h2>
        <p className="dashboard-address" style={{ color: "#e8f4ff", margin: 0, fontSize: "16px" }}>
          📍 {data.adresse}
        </p>
      </header>

      <div className="dashboard-grid" style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
        
        {/* Ligne 1 : Résumé rapide (Scores statiques) */}
        <div className="dashboard-row" style={{ display: "flex", gap: "20px" }}>
          {/* Si tes composants ScoreGauge/PropertyMap plantent, commente-les pour la démo */}
          {/* <ScoreGauge score={data.resume.score_global} niveau="eleve" /> */}
          {/* <PropertyMap lat={data.coordonnees.latitude} lng={data.coordonnees.longitude} adresse={data.adresse} /> */}
        </div>

        {/* Ligne 2 : LE JUMEAU NUMÉRIQUE 3D */}
        <div className="dashboard-row" style={{ display: "flex", gap: "20px", height: "600px" }}>
          {/* <RiskCards scores={data.analyse_risques.scores_par_alea} dominants={[]} /> */}
          
          <div style={{ flex: 1, background: "#04070c", borderRadius: "12px", border: "1px solid #1c5a9c", overflow: "hidden" }}>
            {/* On injecte l'adaptateur dans la 3D */}
            <DigitalTwin payload={jumeauPayload} />
          </div>
        </div>

        {/* Ligne 3 : Synthèse financière */}
        <div style={{ background: "rgba(6, 14, 26, 0.8)", padding: "20px", borderRadius: "12px", border: "1px solid #1c5a9c", color: "white" }}>
          <h3 style={{ color: "#4da6ff", marginTop: 0 }}>Synthèse de la Rénovation</h3>
          <p>Coût total estimé : <strong>{data.resume.cout_total_travaux}</strong></p>
          <p>Aides mobilisables (Anah, Fonds Barnier) : <strong style={{ color: "#3fb950" }}>{data.resume.aides_mobilisables}</strong></p>
          <p style={{ fontSize: "18px" }}>Reste à charge net : <strong>{data.resume.reste_a_charge_net}</strong></p>
        </div>

      </div>
    </div>
  );
}