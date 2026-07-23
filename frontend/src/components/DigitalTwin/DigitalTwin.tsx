import { useState } from "react";
import { JumeauNumerique } from "./JumeauNumerique";

interface DigitalTwinProps {
  payload: any;
}

export default function DigitalTwin({ payload }: DigitalTwinProps) {
  const [annee, setAnnee] = useState<2025 | 2050>(2025);
  
  const [hoveredZoneName, setHoveredZoneName] = useState<string | null>(null);
  const [pinnedZoneName, setPinnedZoneName] = useState<string | null>(null);
  
  const [vulnTestResult, setVulnTestResult] = useState<any>(null);
  const [isLoadingMistral, setIsLoadingMistral] = useState(false);

  // Choix du dataset selon l'année
  const displayZones = annee === 2050 && payload.projection_2050 
    ? payload.projection_2050.zones 
    : payload.zones;

  const activeZoneName = pinnedZoneName ?? hoveredZoneName;
  const activeZoneData = activeZoneName ? displayZones[activeZoneName] : null;

  const handleZoneHover = (zoneName: string | null) => {
    setHoveredZoneName(zoneName);
  };

  const handleZoneClick = async (zoneName: string, zoneData: any) => {
    if (pinnedZoneName === zoneName) {
      setPinnedZoneName(null);
      setVulnTestResult(null);
      return;
    }
    setPinnedZoneName(zoneName);
    setVulnTestResult(null);
    setIsLoadingMistral(true);

    try {
      const response = await fetch(`/api/jumeau/vulnerability-test?zone_name=${zoneName}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(zoneData), 
      });
      if (!response.ok) throw new Error("Erreur réseau API Mistral");
      const data = await response.json();
      setVulnTestResult(data);
    } catch (error) {
      console.error("Erreur lors du test de vulnérabilité:", error);
      setVulnTestResult({ error: "Impossible de générer le test avec Mistral pour le moment." });
    } finally {
      setIsLoadingMistral(false);
    }
  };

  const getBadgeColor = (niveau: string) => {
    switch (niveau) {
      case "critique": return "#da3633";
      case "eleve": return "#db6d28";
      case "modere": return "#d29922";
      case "faible": return "#3fb950";
      default: return "#4da6ff";
    }
  };

  return (
    <div className="digital-twin" style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden" }}>
      
      <JumeauNumerique 
        zonesData={displayZones}
        onZoneClick={(zoneName) => handleZoneClick(zoneName, displayZones[zoneName])} 
        onZoneHover={handleZoneHover}
      />

      {/* Panneau de gauche - Boutons 2025/2050 (comme le HTML) */}
      <div style={{ position: "absolute", top: "20px", left: "20px", background: "rgba(6, 14, 26, 0.8)", border: "1px solid #1c5a9c", borderRadius: "10px", padding: "14px 18px", color: "#cfe8ff", zIndex: 10, backdropFilter: "blur(8px)", boxShadow: "0 0 20px rgba(30, 130, 255, 0.15)" }}>
        <h3 style={{ margin: "0 0 10px 0", fontSize: "12px", fontWeight: 600, color: "#4da6ff", textTransform: "uppercase", letterSpacing: "0.08em" }}>Projection temporelle</h3>
        <div style={{ display: "flex", gap: "6px" }}>
          <button
            onClick={() => setAnnee(2025)}
            style={{
              background: annee === 2025 ? "#4da6ff" : "rgba(20, 40, 65, 0.8)",
              border: "1px solid #1c5a9c",
              color: annee === 2025 ? "#04070c" : "#cfe8ff",
              padding: "8px 16px", borderRadius: "6px", cursor: "pointer",
              fontSize: "13px", fontWeight: annee === 2025 ? 700 : 400,
              transition: "all .15s"
            }}
          >2025</button>
          <button
            onClick={() => setAnnee(2050)}
            style={{
              background: annee === 2050 ? "#4da6ff" : "rgba(20, 40, 65, 0.8)",
              border: "1px solid #1c5a9c",
              color: annee === 2050 ? "#04070c" : "#cfe8ff",
              padding: "8px 16px", borderRadius: "6px", cursor: "pointer",
              fontSize: "13px", fontWeight: annee === 2050 ? 700 : 400,
              transition: "all .15s"
            }}
          >2050</button>
        </div>
        <div style={{ marginTop: "10px", fontSize: "12px", color: "#7fb4e8" }}>
          Score global : <strong style={{ color: "#e8f4ff", fontSize: "22px", textShadow: "0 0 12px rgba(77,166,255,0.6)" }}>{annee === 2050 && payload.projection_2050 ? payload.projection_2050.score_global : payload.score_global}</strong>
        </div>
      </div>

      {/* Hint text */}
      <div style={{ position: "absolute", bottom: "16px", left: "20px", color: "#3d6a94", fontSize: "12px", zIndex: 10 }}>
        Glisser = orbiter · Molette = zoom · Clic sur une zone = détails
      </div>

      {/* Panneau de droite (Informations & Mistral) */}
      {activeZoneName && activeZoneData && (
        <div style={{ 
          position: "absolute", top: "20px", right: "20px", width: "320px", 
          background: "rgba(6, 14, 26, 0.9)", border: "1px solid #1c5a9c", 
          borderRadius: "10px", padding: "18px", color: "#cfe8ff", backdropFilter: "blur(8px)",
          transition: 'opacity 0.2s ease'
        }}>
          {/* En-tête de la zone + indicateur d'épinglage */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <h2 style={{ margin: 0, textTransform: 'capitalize', color: '#e8f4ff' }}>
              {activeZoneName.replace("_", " ")}
            </h2>
            {pinnedZoneName === activeZoneName && (
              <span style={{ fontSize: '12px', color: '#4da6ff', fontWeight: 'bold' }}>📌</span>
            )}
          </div>
          
          <span style={{ 
            display: "inline-block", padding: "4px 10px", borderRadius: "12px", 
            backgroundColor: getBadgeColor(activeZoneData.niveau), color: "#000", fontWeight: "bold", fontSize: "12px", marginBottom: "15px" 
          }}>
            {activeZoneData.niveau.toUpperCase()} — {activeZoneData.risque}/100
          </span>

          <p style={{ fontSize: "13px", lineHeight: 1.5, color: "#9fc4e8" }}>{activeZoneData.justification}</p>

          {/* Recommandations de base (RAG) */}
          {activeZoneData.recommandations?.map((reco: any, idx: number) => (
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