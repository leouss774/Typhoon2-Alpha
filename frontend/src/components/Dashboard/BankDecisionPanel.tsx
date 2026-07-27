
interface BankDecisionProps {
  decision: {
    valeur_marche: number;
    valeur_ajustee: number;
    decote_pct: number;
    taux_propose: number;
    majoration_taux: number;
    exigences: string[];
    points_a_verifier: string[];
    indice_confiance: number;
    score_climatique: number;
    score_risque_bancaire: number;
    statut_dossier: string;
    niveau_risque_global?: string;
    impact_esg?: string;
    points_forts?: string[];
    points_faibles?: string[];
    recommandation_garantie?: string;
    conditions_suspensives?: string[];
    hard_stops: string[];
    avis_analyste: string;
  };
}

export default function BankDecisionPanel({ decision }: BankDecisionProps) {
  if (!decision || Object.keys(decision).length === 0) {
    return null; // Pas de données bancaires
  }

  // Formatage monétaire
  const formatEur = (val: number) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(val);

  // Couleurs statuts
  const getStatusColor = (statut: string) => {
    if (statut === "Fast-Track") return "#3fb950";
    if (statut === "Refus Automatique") return "#ff4d4f";
    return "#faad14";
  };
  const statusColor = getStatusColor(decision.statut_dossier);
  const confidenceColor = decision.indice_confiance >= 90 ? "#3fb950" : decision.indice_confiance >= 70 ? "#faad14" : "#ff4d4f";

  const getRiskLevelColor = (risk?: string) => {
    if (risk === "Faible") return "#3fb950";
    if (risk === "Élevé") return "#ff4d4f";
    return "#faad14";
  };
  const riskLevelColor = getRiskLevelColor(decision.niveau_risque_global);

  return (
    <div style={{
      background: "linear-gradient(145deg, rgba(6, 14, 26, 0.8) 0%, rgba(10, 20, 35, 0.95) 100%)",
      padding: "28px",
      borderRadius: "16px",
      border: `1px solid ${statusColor}`,
      boxShadow: `0 8px 32px 0 rgba(0, 0, 0, 0.37), 0 0 15px 0 ${statusColor}40`,
      backdropFilter: "blur(8px)",
      color: "white",
      marginTop: "20px",
      fontFamily: "'Inter', sans-serif"
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "24px", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "16px" }}>
        <div>
          <h3 style={{ margin: 0, fontSize: "24px", display: "flex", alignItems: "center", gap: "12px", background: "linear-gradient(90deg, #4da6ff, #99c2ff)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            🏦 Décision de Financement Bancaire (IA)
          </h3>
          <p style={{ margin: "4px 0 0 0", fontSize: "14px", color: "#8b949e" }}>
            Analyse générée par le modèle Mistral, restreinte par le schéma métier de la banque.
          </p>
        </div>
        <div style={{ textAlign: "right" }}>
          <span style={{ 
            background: `linear-gradient(135deg, ${statusColor} 0%, ${statusColor}dd 100%)`, 
            color: "#000", padding: "8px 16px", borderRadius: "20px", fontWeight: "900", fontSize: "14px",
            boxShadow: `0 4px 10px ${statusColor}60`
          }}>
            {decision.statut_dossier}
          </span>
        </div>
      </div>

      {/* Jauges de confiance */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "28px", padding: "16px", background: "rgba(0,0,0,0.2)", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ fontSize: "14px", color: "#cfe8ff", fontWeight: 600 }}>Fiabilité de l'Analyse :</div>
        <div style={{ flex: 1, height: "12px", background: "#1c2128", borderRadius: "6px", overflow: "hidden", border: "1px solid #30363d" }}>
          <div style={{ 
            width: `${decision.indice_confiance}%`, height: "100%", 
            background: `linear-gradient(90deg, ${confidenceColor}88, ${confidenceColor})`,
            boxShadow: `0 0 10px ${confidenceColor}`,
            transition: "width 1s ease-in-out"
          }} />
        </div>
        <strong style={{ color: confidenceColor, fontSize: "18px", textShadow: `0 0 8px ${confidenceColor}80` }}>
          {decision.indice_confiance}%
        </strong>
      </div>

      {/* Synthèse SWOT / OAD */}
      {decision.niveau_risque_global && (
        <div style={{ marginBottom: "28px", display: "grid", gridTemplateColumns: "1fr 2fr", gap: "20px" }}>
          
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div style={{ background: "rgba(0,0,0,0.2)", borderRadius: "8px", border: `1px solid ${riskLevelColor}50`, padding: "16px", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", flex: 1 }}>
              <span style={{ fontSize: "12px", color: "#8b949e", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "4px" }}>Score de Risque Bancaire</span>
              <div style={{ display: "flex", alignItems: "baseline", gap: "4px", marginBottom: "4px" }}>
                <strong style={{ fontSize: "28px", color: riskLevelColor, textShadow: `0 0 10px ${riskLevelColor}80` }}>{decision.score_risque_bancaire}</strong>
                <span style={{ fontSize: "14px", color: "#8b949e" }}>/ 100</span>
              </div>
              <strong style={{ fontSize: "14px", color: riskLevelColor }}>({decision.niveau_risque_global})</strong>
            </div>
            
            {decision.impact_esg && (
              <div style={{ background: "linear-gradient(135deg, rgba(63,185,80,0.1) 0%, rgba(31,111,235,0.1) 100%)", borderRadius: "8px", border: "1px solid rgba(63,185,80,0.3)", padding: "12px", textAlign: "center" }}>
                <span style={{ fontSize: "11px", color: "#8b949e", textTransform: "uppercase", display: "block", marginBottom: "4px" }}>🌱 Bilan ESG / Climat</span>
                <strong style={{ fontSize: "13px", color: "#3fb950" }}>{decision.impact_esg}</strong>
              </div>
            )}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div style={{ background: "rgba(63, 185, 80, 0.05)", borderRadius: "8px", border: "1px solid rgba(63, 185, 80, 0.2)", padding: "16px", display: "flex", flexDirection: "column" }}>
              <h5 style={{ margin: "0 0 12px 0", color: "#3fb950", fontSize: "13px", textTransform: "uppercase", display: "flex", alignItems: "center", gap: "8px" }}>✅ Points Forts</h5>
              <ul style={{ margin: 0, paddingLeft: "20px", color: "#e6edf3", fontSize: "13px", lineHeight: "1.5", flex: 1 }}>
                {(decision.points_forts || []).map((pt, i) => <li key={i} style={{marginBottom: "4px"}}>{pt}</li>)}
              </ul>
            </div>
            
            <div style={{ background: "rgba(255, 77, 79, 0.05)", borderRadius: "8px", border: "1px solid rgba(255, 77, 79, 0.2)", padding: "16px", display: "flex", flexDirection: "column" }}>
              <h5 style={{ margin: "0 0 12px 0", color: "#ff4d4f", fontSize: "13px", textTransform: "uppercase", display: "flex", alignItems: "center", gap: "8px" }}>⚠️ Points Faibles</h5>
              <ul style={{ margin: 0, paddingLeft: "20px", color: "#ffb3b3", fontSize: "13px", lineHeight: "1.5", flex: 1 }}>
                {(decision.points_faibles || []).map((pt, i) => <li key={i} style={{marginBottom: "4px"}}>{pt}</li>)}
              </ul>
            </div>
          </div>

        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginBottom: "24px" }}>
        
        {/* Colonne Valeur */}
        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "20px", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.05)", transition: "transform 0.2s" }}>
          <h4 style={{ color: "#cfe8ff", margin: "0 0 16px 0", fontSize: "16px", textTransform: "uppercase", letterSpacing: "1px" }}>Évaluation du Bien</h4>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
            <span style={{ color: "#8b949e" }}>Valeur DVF (OpenData)</span>
            <strong style={{ fontSize: "16px" }}>{formatEur(decision.valeur_marche)}</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
            <span style={{ color: "#8b949e" }}>Score Climatique (Géorisques)</span>
            <strong style={{ fontSize: "16px", color: decision.score_climatique > 60 ? "#ff4d4f" : decision.score_climatique > 30 ? "#faad14" : "#3fb950" }}>
              {decision.score_climatique} / 100
            </strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
            <span style={{ color: "#ff4d4f" }}>Décote Risque Climatique</span>
            <strong style={{ color: "#ff4d4f", fontSize: "16px" }}>-{decision.decote_pct}%</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", borderTop: "1px solid #30363d", paddingTop: "12px", marginTop: "12px" }}>
            <span style={{ color: "#cfe8ff", fontWeight: "bold" }}>Valeur de Garantie Finale</span>
            <strong style={{ color: "#4da6ff", fontSize: "20px", textShadow: "0 0 10px rgba(77, 166, 255, 0.3)" }}>{formatEur(decision.valeur_ajustee)}</strong>
          </div>
        </div>

        {/* Colonne Taux & Conditions */}
        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "20px", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.05)" }}>
          <h4 style={{ color: "#cfe8ff", margin: "0 0 16px 0", fontSize: "16px", textTransform: "uppercase", letterSpacing: "1px" }}>Conditions du Prêt</h4>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
            <span style={{ color: "#8b949e" }}>Taux de base bancaire</span>
            <strong style={{ fontSize: "16px" }}>{(decision.taux_propose - decision.majoration_taux).toFixed(2)} %</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
            <span style={{ color: "#8b949e" }}>Ajustement Actuariel (Risque)</span>
            <span style={{ color: decision.majoration_taux > 0 ? "#ff4d4f" : "#3fb950", fontSize: "16px", fontWeight: "bold" }}>
              {decision.majoration_taux > 0 ? "+" : ""}{decision.majoration_taux.toFixed(2)} %
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", borderTop: "1px solid #30363d", paddingTop: "12px", marginTop: "12px" }}>
            <span style={{ color: "#cfe8ff", fontWeight: "bold" }}>Taux Proposé Final</span>
            <strong style={{ color: statusColor, fontSize: "20px", textShadow: `0 0 10px ${statusColor}40` }}>{decision.taux_propose.toFixed(2)} %</strong>
          </div>
        </div>
      </div>

      {/* Conditions Suspensives et Garanties */}
      <div style={{ marginBottom: "28px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
        {/* Conditions Suspensives */}
        {decision.conditions_suspensives && decision.conditions_suspensives.length > 0 && (
          <div style={{ background: "rgba(163, 113, 247, 0.08)", borderLeft: "4px solid #a371f7", padding: "16px 20px", borderRadius: "8px" }}>
            <h4 style={{ color: "#d2a8ff", margin: "0 0 12px 0", fontSize: "14px", textTransform: "uppercase", letterSpacing: "1px" }}>⚖️ Clauses Suspensives au Contrat</h4>
            <ul style={{ margin: 0, paddingLeft: "24px", color: "#e6edf3", fontSize: "14px", lineHeight: "1.6" }}>
              {decision.conditions_suspensives.map((cond, idx) => (
                <li key={idx} style={{ marginBottom: "4px" }}>{cond}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Garantie Recommandée */}
        {decision.recommandation_garantie && (
          <div style={{ background: "rgba(88, 166, 255, 0.08)", borderLeft: "4px solid #58a6ff", padding: "16px 20px", borderRadius: "8px" }}>
            <h4 style={{ color: "#79c0ff", margin: "0 0 12px 0", fontSize: "14px", textTransform: "uppercase", letterSpacing: "1px" }}>🛡️ Montage Juridique (Garantie)</h4>
            <p style={{ margin: 0, color: "#e6edf3", fontSize: "15px", fontWeight: "bold", lineHeight: "1.6" }}>
              {decision.recommandation_garantie}
            </p>
          </div>
        )}
      </div>

      {/* Hard Stops */}
      {decision.hard_stops && decision.hard_stops.length > 0 && (
        <div style={{ background: "linear-gradient(90deg, rgba(255, 77, 79, 0.15) 0%, rgba(255, 77, 79, 0.05) 100%)", borderLeft: "4px solid #ff4d4f", padding: "16px 20px", borderRadius: "8px", marginBottom: "24px" }}>
          <h4 style={{ color: "#ff4d4f", margin: "0 0 12px 0", fontSize: "15px", textTransform: "uppercase", letterSpacing: "1px" }}>🚫 Hard Stops Détectés (Refus Automatique)</h4>
          <ul style={{ margin: 0, paddingLeft: "24px", color: "#ffb3b3", fontSize: "14px", lineHeight: "1.6" }}>
            {decision.hard_stops.map((stop, idx) => (
              <li key={idx} style={{ marginBottom: "4px", fontWeight: 500 }}>{stop}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Checklist de Vérification */}
      {decision.points_a_verifier && decision.points_a_verifier.length > 0 && (
        <div style={{ background: "linear-gradient(90deg, rgba(210, 153, 34, 0.15) 0%, rgba(210, 153, 34, 0.05) 100%)", borderLeft: "4px solid #d29922", padding: "16px 20px", borderRadius: "8px", marginBottom: "24px" }}>
          <h4 style={{ color: "#d29922", margin: "0 0 12px 0", fontSize: "15px", textTransform: "uppercase", letterSpacing: "1px" }}>⚠️ Exigences & Vérifications KYC Requises</h4>
          <ul style={{ margin: 0, paddingLeft: "24px", color: "#ffe6b3", fontSize: "14px", lineHeight: "1.6" }}>
            {decision.points_a_verifier.map((pt, idx) => (
              <li key={idx} style={{ marginBottom: "4px" }}>{pt}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Avis Analyste & Traçabilité */}
      <div style={{ background: "rgba(31, 111, 235, 0.08)", border: "1px solid rgba(31, 111, 235, 0.3)", padding: "20px", borderRadius: "12px", position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: 0, left: 0, width: "4px", height: "100%", background: "#1f6feb" }} />
        <h4 style={{ color: "#58a6ff", margin: "0 0 12px 0", fontSize: "15px", textTransform: "uppercase", letterSpacing: "1px" }}>
          Avis Argumenté du Comité (IA)
        </h4>
        <p style={{ margin: "0 0 20px 0", color: "#e6edf3", fontStyle: "italic", lineHeight: "1.6", fontSize: "15px" }}>"{decision.avis_analyste}"</p>
        
        <div style={{ borderTop: "1px dashed rgba(88, 166, 255, 0.3)", paddingTop: "16px" }}>
          <h5 style={{ margin: "0 0 8px 0", color: "#8b949e", fontSize: "12px", textTransform: "uppercase" }}>🔍 Auditabilité & Traçabilité des Données</h5>
          <p style={{ margin: 0, fontSize: "12px", color: "#8b949e", lineHeight: "1.5" }}>
            <strong>Sources OpenData :</strong> Validation KYC via l'<em>Observatoire DPE de l'ADEME</em> (Surface, Année). Valeur immobilière ancrée sur <em>DVF (Gouvernement)</em>. Scores de risque climatique via <em>Géorisques (BRGM)</em> et <em>IGN</em>. <br/>
            <strong>Calcul Actuariel :</strong> Les taux directeurs, les primes de risques et les décotes sont déterminés par des règles mathématiques strictes (moteur Python) et non inventés par l'IA. <br/>
            <strong>Garde-fous IA :</strong> L'Agent Mistral est confiné à un rôle de synthèse (avis argumenté et extraction des exigences) avec validation stricte du schéma de données.
          </p>
        </div>
      </div>

    </div>
  );
}
