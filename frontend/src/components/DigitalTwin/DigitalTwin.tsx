import { useState, useMemo } from "react";
import { JumeauNumerique } from "./JumeauNumerique";
import TimelineSlider from "./TimelineSlider";
import RenovationSlider from "./RenovationSlider";

interface DigitalTwinProps {
  payload: any; // Le JSON JumeauPayload qui vient de l'orchestrateur
}

export default function DigitalTwin({ payload }: DigitalTwinProps) {
  const [annee, setAnnee] = useState<2025 | 2050>(2025);
  const [apresTravaux, setApresTravaux] = useState(false);
  
  // États pour le panneau latéral (info-panel)
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [selectedZoneData, setSelectedZoneData] = useState<any>(null);
  
  // États pour Mistral (Test de vulnérabilité)
  const [vulnTestResult, setVulnTestResult] = useState<any>(null);
  const [isLoadingMistral, setIsLoadingMistral] = useState(false);

  // 1. Choix du dataset selon l'année
  const baseZones = annee === 2050 && payload.projection_2050 
    ? payload.projection_2050.zones 
    : payload.zones;

  // 2. Simulation globale "Après travaux"
  const displayZones = useMemo(() => {
    if (!apresTravaux) return baseZones;
    const improvedZones = { ...baseZones };
    Object.keys(improvedZones).forEach((key) => {
      improvedZones[key] = {
        ...improvedZones[key],
        risque: Math.max(0, Math.floor(improvedZones[key].risque * 0.6)), 
      };
    });
    return improvedZones;
  }, [baseZones, apresTravaux]);

  // 3. Gestion du CLIC sur une zone 3D -> Appel Mistral
  const handleZoneClick = async (zoneName: string, zoneData: any) => {
    setSelectedZone(zoneName);
    setSelectedZoneData(zoneData);
    setVulnTestResult(null); // On reset le test précédent
    setIsLoadingMistral(true);

    try {
      // Appel à ta route FastAPI créée précédemment
      const response = await fetch(`/api/jumeau/vulnerability-test?zone_name=${zoneName}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // On envoie les données de la zone pour que Mistral ait le contexte
        body: JSON.stringify(zoneData), 
      });

      if (!response.ok) throw new Error("Erreur réseau API Mistral");
      
      const data = await response.json();
      setVulnTestResult(data); // On stocke la réponse Pydantic
    } catch (error) {
      console.error("Erreur lors du test de vulnérabilité:", error);
      // Fallback UI en cas d'erreur
      setVulnTestResult({ error: "Impossible de générer le test avec Mistral pour le moment." });
    } finally {
      setIsLoadingMistral(false);
    }
  };

  // Helper pour la couleur du badge
  const getBadgeColor = (niveau: string) => {
    switch (niveau) {
      case "critique": return "#da3633"; // Rouge
      case "eleve": return "#db6d28";    // Orange foncé
      case "modere": return "#d29922";   // Orange
      case "faible": return "#3fb950";   // Vert
      default: return "#4da6ff";
    }
  };

  return (
    <div className="digital-twin" style={{ position: "relative", width: "100%", height: "100vh", overflow: "hidden" }}>
      
      {/* --- Rendu 3D --- */}
      <JumeauNumerique 
        zonesData={displayZones} 
        geometrie={payload.geometrie} 
        onZoneClick={(zoneName) => handleZoneClick(zoneName, displayZones[zoneName])} 
      />

      {/* --- Panneau de gauche (Contrôles) --- */}
      <div style={{ position: "absolute", top: "20px", left: "20px", background: "rgba(6, 14, 26, 0.8)", padding: "15px", borderRadius: "10px", border: "1px solid #1c5a9c", color: "white" }}>
        <h3 style={{ margin: "0 0 10px 0", fontSize: "12px", color: "#4da6ff", textTransform: "uppercase" }}>Projection Temporelle</h3>
        <TimelineSlider value={annee} onChange={(val) => setAnnee(val as 2025 | 2050)} />
        <div style={{ marginTop: "15px" }}>
          <RenovationSlider value={apresTravaux} onChange={setApresTravaux} />
        </div>
        <div style={{ marginTop: "15px", fontSize: "14px", color: "#7fb4e8" }}>
          Score global : <strong style={{ color: "#e8f4ff", fontSize: "24px" }}>{annee === 2050 && payload.projection_2050 ? payload.projection_2050.score_global : payload.score_global}</strong>
        </div>
      </div>

      {/* --- Panneau de droite (Informations & Mistral) --- */}
      {selectedZone && selectedZoneData && (
        <div style={{ 
          position: "absolute", top: "20px", right: "20px", width: "320px", 
          background: "rgba(6, 14, 26, 0.9)", border: "1px solid #1c5a9c", 
          borderRadius: "10px", padding: "18px", color: "#cfe8ff", backdropFilter: "blur(8px)"
        }}>
          {/* En-tête de la zone */}
          <h2 style={{ margin: "0 0 10px 0", textTransform: "capitalize", color: "#e8f4ff" }}>
            {selectedZone.replace("_", " ")}
          </h2>
          
          <span style={{ 
            display: "inline-block", padding: "4px 10px", borderRadius: "12px", 
            backgroundColor: getBadgeColor(selectedZoneData.niveau), color: "#000", fontWeight: "bold", fontSize: "12px", marginBottom: "15px" 
          }}>
            {selectedZoneData.niveau.toUpperCase()} — {selectedZoneData.risque}/100
          </span>

          <p style={{ fontSize: "13px", lineHeight: 1.5, color: "#9fc4e8" }}>{selectedZoneData.justification}</p>

          {/* Recommandations de base (RAG) */}
          {selectedZoneData.recommandations?.map((reco: any, idx: number) => (
            <div key={idx} style={{ background: "rgba(20, 40, 65, 0.8)", border: "1px solid #1c5a9c", borderRadius: "8px", padding: "10px", marginTop: "10px", fontSize: "12px" }}>
              <strong>{reco.travaux}</strong><br/>
              {reco.cout_estime} • Gain : +{reco.gain_resilience}%
            </div>
          ))}

          <hr style={{ borderColor: "#1c5a9c", margin: "15px 0" }} />

          {/* Section Agent Mistral Dynamique */}
          <h3 style={{ fontSize: "14px", color: "#4da6ff", marginBottom: "10px" }}>🧠 Test de Vulnérabilité IA</h3>
          
          {isLoadingMistral ? (
            <div style={{ fontSize: "13px", color: "#9fc4e8", fontStyle: "italic", animation: "pulse 1.5s infinite" }}>
              L'agent Mistral génère un scénario climatique...
            </div>
          ) : vulnTestResult ? (
            vulnTestResult.error ? (
              <p style={{ color: "#da3633", fontSize: "12px" }}>{vulnTestResult.error}</p>
            ) : (
              <div style={{ fontSize: "13px" }}>
                <p><strong>Scénario :</strong> {vulnTestResult.scenario}</p>
                <p style={{ color: "#9fc4e8" }}>{vulnTestResult.resume}</p>
                
                <div style={{ display: "flex", justifyContent: "space-between", margin: "10px 0", background: "#0a192f", padding: "8px", borderRadius: "6px" }}>
                  <span>Avant: <strong style={{color:"#da3633"}}>{vulnTestResult.score_avant}</strong></span>
                  <span>Après travaux: <strong style={{color:"#3fb950"}}>{vulnTestResult.score_apres_travaux}</strong></span>
                </div>

                {vulnTestResult.points_de_vigilance?.length > 0 && (
                  <ul style={{ paddingLeft: "15px", color: "#d29922", fontSize: "12px" }}>
                    {vulnTestResult.points_de_vigilance.map((pt: string, i: number) => <li key={i}>{pt}</li>)}
                  </ul>
                )}
              </div>
            )
          ) : (
            <p style={{ fontSize: "12px", color: "#5fb2ff", opacity: 0.7 }}>Cliquez pour simuler.</p>
          )}

        </div>
      )}
    </div>
  );
}