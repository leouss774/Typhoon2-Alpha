import { useMemo } from "react";

interface RiskIdentifie {
  nom: string;
  score: number;
  niveau: string;
  zone_impactee: string;
  description: string;
}

interface GarantieAssurance {
  type: string;
  obligatoire: boolean;
  detail: string;
}

interface PreventionRecommandation {
  zone: string;
  travaux: string;
  cout_estime: string;
  gain_resilience: number;
  priorite: number;
  aide_financiere: string;
}

interface ProjectionRisque {
  horizon: string;
  score_actuel: number;
  score_projete: number;
  aggravation: number;
  scenario: string;
  zones_projetees: Record<string, { risque_projete: number; evolution: string }>;
}

interface BankDecision {
  // Section 1
  score_risque_bancaire: number;
  score_climatique: number;
  niveau_risque_global: string;
  impact_esg: string;
  // Section 2
  risques_identifies: RiskIdentifie[];
  // Section 3
  valeur_marche: number;
  valeur_ajustee: number;
  decote_pct: number;
  source_valorisation: string;
  // Section 4
  garanties_assurance: GarantieAssurance[];
  recommandation_garantie: string;
  // Section 5
  prevention_recommandations: PreventionRecommandation[];
  cout_total_prevention: string;
  // Section 6
  projection_risque: ProjectionRisque | null;
  // Section 7
  niveau_risque_bancaire: string;
  indice_confiance: number;
  avis_analyste: string;
  rapport_synthetique: string;
  synthese_points_cles: string[];
  analyse_complete_url: string;
  // Legacy
  taux_propose: number;
  majoration_taux: number;
  exigences: string[];
  points_a_verifier: string[];
  points_forts: string[];
  points_faibles: string[];
  hard_stops: string[];
  conditions_suspensives: string[];
}

interface BankDecisionProps {
  decision: BankDecision;
}

export default function BankDecisionPanel({ decision }: BankDecisionProps) {
  if (!decision || Object.keys(decision).length === 0) return null;

  // ── Formatting helpers ─────────────────────────────────────────────
  const formatEur = (val: number) =>
    new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(val);

  const riskLevelColor = (() => {
    if (decision.niveau_risque_global === "Faible") return "#3fb950";
    if (decision.niveau_risque_global === "Élevé") return "#ff4d4f";
    return "#faad14";
  })();

  const scoreColor = (s: number) => (s >= 60 ? "#ff4d4f" : s >= 35 ? "#faad14" : "#3fb950");
  const niveauBadgeColor = (n: string) => {
    if (n === "critique" || n === "eleve") return "#ff4d4f";
    if (n === "modere") return "#faad14";
    return "#3fb950";
  };

  // ── Classement des recommandations par zone ────────────────────────
  const recosByZone = useMemo(() => {
    const map: Record<string, PreventionRecommandation[]> = {};
    for (const r of decision.prevention_recommandations || []) {
      if (!map[r.zone]) map[r.zone] = [];
      map[r.zone].push(r);
    }
    return map;
  }, [decision.prevention_recommandations]);

  // ── Style réutilisable pour les sections ───────────────────────────
  const sectionStyle = {
    background: "linear-gradient(135deg, rgba(6, 14, 26, 0.95) 0%, rgba(10, 20, 35, 0.98) 100%)",
    padding: "24px",
    borderRadius: "14px",
    border: "1px solid rgba(255,255,255,0.08)",
    boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
    backdropFilter: "blur(12px)" as const,
  };

  const sectionTitleStyle = {
    fontSize: "18px",
    fontWeight: 700,
    margin: "0 0 16px 0",
    display: "flex" as const,
    alignItems: "center" as const,
    gap: "10px",
    letterSpacing: "0.3px",
  };

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px", fontFamily: "'Inter', -apple-system, sans-serif", color: "#e6edf3" }}>
      
      {/* ──────── HEADER : Titre + téléchargement PDF + confiance ──────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ fontSize: "28px" }}>🏦</span>
          <div>
            <h2 style={{ margin: 0, fontSize: "22px", background: "linear-gradient(90deg, #4da6ff, #99c2ff)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              Analyse de Risque Crédit
            </h2>
            <p style={{ margin: "2px 0 0 0", fontSize: "13px", color: "#8b949e" }}>
              📋 Outil d'aide à la décision — Aucune décision automatique
            </p>
          </div>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <a
            href={decision.analyse_complete_url || "#"}
            download
            style={{
              padding: "8px 16px", borderRadius: "8px",
              background: "linear-gradient(135deg, #1f6feb, #58a6ff)",
              color: "#fff", border: "none",
              fontWeight: 700, fontSize: "13px",
              textDecoration: "none", cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: "6px",
              boxShadow: "0 2px 8px rgba(31,111,235,0.4)"
            }}
          >
            📄 Télécharger le rapport
          </a>
          <div style={{
            background: "rgba(255,255,255,0.06)", borderRadius: "20px",
            padding: "6px 14px", border: "1px solid rgba(255,255,255,0.1)",
            fontSize: "13px", fontWeight: 600, color: "#cfe8ff"
          }}>
            Confiance {decision.indice_confiance}%
          </div>
        </div>
      </div>

      {/* ──────── SECTION 1 : 📊 Score de risque du bien ──────── */}
      <div style={sectionStyle}>
        <h3 style={{ ...sectionTitleStyle, color: "#58a6ff" }}>
          📊 Score de Risque du Bien
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "16px" }}>
          <div style={{ background: "rgba(0,0,0,0.25)", borderRadius: "10px", padding: "16px", textAlign: "center", border: `1px solid ${riskLevelColor}40` }}>
            <span style={{ fontSize: "11px", color: "#8b949e", textTransform: "uppercase", letterSpacing: "1px" }}>Score Bancaire</span>
            <div style={{ fontSize: "36px", fontWeight: 900, color: riskLevelColor, textShadow: `0 0 12px ${riskLevelColor}60`, margin: "4px 0" }}>
              {decision.score_risque_bancaire}
              <span style={{ fontSize: "16px", color: "#8b949e", fontWeight: 400 }}>/100</span>
            </div>
            <span style={{ fontSize: "13px", color: riskLevelColor, fontWeight: 600 }}>{decision.niveau_risque_global}</span>
          </div>
          <div style={{ background: "rgba(0,0,0,0.25)", borderRadius: "10px", padding: "16px", textAlign: "center" }}>
            <span style={{ fontSize: "11px", color: "#8b949e", textTransform: "uppercase", letterSpacing: "1px" }}>Score Climatique</span>
            <div style={{ fontSize: "36px", fontWeight: 900, color: scoreColor(decision.score_climatique), margin: "4px 0" }}>
              {decision.score_climatique}
              <span style={{ fontSize: "16px", color: "#8b949e", fontWeight: 400 }}>/100</span>
            </div>
            <span style={{ fontSize: "13px", color: scoreColor(decision.score_climatique) }}>
              Source : Géorisques
            </span>
          </div>
          <div style={{ background: "rgba(0,0,0,0.25)", borderRadius: "10px", padding: "16px", textAlign: "center" }}>
            <span style={{ fontSize: "11px", color: "#8b949e", textTransform: "uppercase", letterSpacing: "1px" }}>Impact ESG</span>
            <div style={{ fontSize: "16px", fontWeight: 700, color: "#3fb950", margin: "8px 0 4px" }}>
              {decision.impact_esg}
            </div>
            <span style={{ fontSize: "12px", color: "#8b949e" }}>
              {decision.impact_esg === "Éligible au Prêt Vert" ? "✅ Éligible au financement vert" : "Bilan climatique standard"}
            </span>
          </div>
        </div>
      </div>

      {/* ──────── SECTION 2 : ⚠️ Principaux risques identifiés ──────── */}
      <div style={sectionStyle}>
        <h3 style={{ ...sectionTitleStyle, color: "#ff7b72" }}>
          ⚠️ Principaux Risques Identifiés
        </h3>
        {decision.risques_identifies && decision.risques_identifies.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {decision.risques_identifies.map((risk, idx) => {
              const barColor = niveauBadgeColor(risk.niveau);
              return (
                <div key={idx} style={{
                  display: "flex", alignItems: "center", gap: "14px",
                  padding: "12px 16px", background: "rgba(0,0,0,0.2)",
                  borderRadius: "10px", border: "1px solid rgba(255,255,255,0.05)"
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                      <strong style={{ fontSize: "14px" }}>{risk.nom}</strong>
                      <span style={{ fontSize: "12px", color: barColor, fontWeight: 700 }}>
                        {risk.score}/100 — {risk.niveau}
                      </span>
                    </div>
                    <div style={{
                      width: "100%", height: "6px", background: "#1c2128",
                      borderRadius: "3px", overflow: "hidden"
                    }}>
                      <div style={{
                        width: `${risk.score}%`, height: "100%",
                        background: `linear-gradient(90deg, ${barColor}88, ${barColor})`,
                        borderRadius: "3px", transition: "width 1s ease"
                      }} />
                    </div>
                    <div style={{ fontSize: "12px", color: "#8b949e", marginTop: "4px" }}>
                      Zone impactée : <strong>{risk.zone_impactee}</strong>
                      {risk.description && ` — ${risk.description.slice(0, 100)}`}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p style={{ color: "#8b949e", fontStyle: "italic" }}>Aucun risque majeur identifié.</p>
        )}
      </div>

      {/* ──────── SECTION 3 : 💰 Valeur ajustée du bien ──────── */}
      <div style={sectionStyle}>
        <h3 style={{ ...sectionTitleStyle, color: "#79c0ff" }}>
          💰 Valeur Ajustée du Bien
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "16px" }}>
          <div style={{ background: "rgba(0,0,0,0.2)", padding: "16px", borderRadius: "10px" }}>
            <span style={{ fontSize: "12px", color: "#8b949e" }}>Valeur Marché (DVF)</span>
            <div style={{ fontSize: "22px", fontWeight: 700, color: "#e6edf3", marginTop: "4px" }}>
              {formatEur(decision.valeur_marche)}
            </div>
            <span style={{ fontSize: "11px", color: "#58a6ff" }}>Source : {decision.source_valorisation || "OpenData"}</span>
          </div>
          <div style={{ background: "rgba(0,0,0,0.2)", padding: "16px", borderRadius: "10px" }}>
            <span style={{ fontSize: "12px", color: "#ff4d4f" }}>Décote Risque Climatique</span>
            <div style={{ fontSize: "22px", fontWeight: 700, color: "#ff4d4f", marginTop: "4px" }}>
              -{decision.decote_pct}%
            </div>
            <span style={{ fontSize: "11px", color: "#8b949e" }}>Prime actuarielle appliquée</span>
          </div>
          <div style={{
            background: "linear-gradient(135deg, rgba(77,166,255,0.12), rgba(77,166,255,0.05))",
            padding: "16px", borderRadius: "10px",
            border: "1px solid rgba(77,166,255,0.3)"
          }}>
            <span style={{ fontSize: "12px", color: "#cfe8ff", fontWeight: 600 }}>Valeur de Garantie Finale</span>
            <div style={{ fontSize: "24px", fontWeight: 900, color: "#4da6ff", marginTop: "4px", textShadow: "0 0 15px rgba(77,166,255,0.4)" }}>
              {formatEur(decision.valeur_ajustee)}
            </div>
            <span style={{ fontSize: "11px", color: "#8b949e" }}>Montant retenu pour le prêt</span>
          </div>
        </div>
      </div>

      {/* ──────── SECTION 4 : 🛡️ Garanties d'assurance recommandées ──────── */}
      <div style={sectionStyle}>
        <h3 style={{ ...sectionTitleStyle, color: "#d2a8ff" }}>
          🛡️ Garanties d'Assurance Recommandées
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
          {decision.garanties_assurance && decision.garanties_assurance.map((g, idx) => (
            <div key={idx} style={{
              padding: "14px 16px", borderRadius: "10px",
              background: g.obligatoire ? "rgba(163,113,247,0.08)" : "rgba(255,255,255,0.03)",
              border: g.obligatoire ? "1px solid rgba(163,113,247,0.2)" : "1px solid rgba(255,255,255,0.05)",
              display: "flex", gap: "12px", alignItems: "flex-start"
            }}>
              <span style={{ fontSize: "18px", marginTop: "2px" }}>
                {g.obligatoire ? "🔴" : "🟡"}
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong style={{ fontSize: "14px", color: g.obligatoire ? "#d2a8ff" : "#e6edf3" }}>
                    {g.type}
                  </strong>
                  <span style={{
                    fontSize: "10px", fontWeight: 700, textTransform: "uppercase",
                    padding: "2px 8px", borderRadius: "10px",
                    background: g.obligatoire ? "rgba(163,113,247,0.2)" : "rgba(255,255,255,0.1)",
                    color: g.obligatoire ? "#d2a8ff" : "#8b949e",
                  }}>
                    {g.obligatoire ? "Obligatoire" : "Recommandée"}
                  </span>
                </div>
                <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#8b949e", lineHeight: "1.4" }}>
                  {g.detail}
                </p>
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: "12px", padding: "10px 14px", background: "rgba(88,166,255,0.06)", borderRadius: "8px", border: "1px solid rgba(88,166,255,0.15)" }}>
          <span style={{ fontSize: "12px", color: "#79c0ff" }}>
            🏛️ Montage juridique recommandé : <strong>{decision.recommandation_garantie}</strong>
          </span>
        </div>
      </div>

      {/* ──────── SECTION 5 : 🏗️ Recommandations de prévention ──────── */}
      <div style={sectionStyle}>
        <h3 style={{ ...sectionTitleStyle, color: "#7ee787" }}>
          🏗️ Recommandations de Prévention
        </h3>
        {decision.prevention_recommandations && decision.prevention_recommandations.length > 0 ? (
          <>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "14px" }}>
              {Object.entries(recosByZone).map(([zone, recos]) => (
                <span key={zone} style={{
                  padding: "4px 10px", borderRadius: "12px", fontSize: "12px",
                  background: "rgba(126,231,135,0.1)", border: "1px solid rgba(126,231,135,0.2)",
                  color: "#7ee787"
                }}>
                  🏗️ {zone} ({recos.length})
                </span>
              ))}
              <span style={{ padding: "4px 10px", borderRadius: "12px", fontSize: "12px", background: "rgba(255,255,255,0.06)", color: "#cfe8ff" }}>
                💰 Total : {decision.cout_total_prevention}
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {decision.prevention_recommandations.map((r, idx) => (
                <div key={idx} style={{
                  display: "flex", gap: "12px", alignItems: "center",
                  padding: "10px 14px", background: "rgba(0,0,0,0.15)",
                  borderRadius: "8px", border: "1px solid rgba(255,255,255,0.04)"
                }}>
                  <span style={{
                    minWidth: "20px", height: "20px", borderRadius: "50%",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    background: r.priorite <= 3 ? "#ff4d4f" : r.priorite <= 6 ? "#faad14" : "#3fb950",
                    color: "#000", fontSize: "10px", fontWeight: 900
                  }}>
                    {r.priorite}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: "13px", fontWeight: 600 }}>{r.travaux}</div>
                    <div style={{ fontSize: "11px", color: "#8b949e", marginTop: "2px" }}>
                      Zone : {r.zone} — Coût : {r.cout_estime} — Gain résilience : +{r.gain_resilience}%
                      {r.aide_financiere && ` — Aide : ${r.aide_financiere}`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p style={{ color: "#8b949e", fontStyle: "italic" }}>
            Aucune recommandation de prévention spécifique pour ce bien.
          </p>
        )}
      </div>

      {/* ──────── SECTION 6 : 📈 Projection de l'évolution du risque ──────── */}
      <div style={sectionStyle}>
        <h3 style={{ ...sectionTitleStyle, color: "#ffa657" }}>
          📈 Projection de l'Évolution du Risque
        </h3>
        {decision.projection_risque ? (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "16px", marginBottom: "16px" }}>
              <div style={{ background: "rgba(0,0,0,0.2)", borderRadius: "10px", padding: "14px", textAlign: "center" }}>
                <span style={{ fontSize: "11px", color: "#8b949e", textTransform: "uppercase" }}>Score Actuel</span>
                <div style={{ fontSize: "28px", fontWeight: 900, color: "#3fb950", marginTop: "4px" }}>
                  {decision.projection_risque.score_actuel}
                </div>
              </div>
              <div style={{ background: "rgba(0,0,0,0.2)", borderRadius: "10px", padding: "14px", textAlign: "center" }}>
                <span style={{ fontSize: "11px", color: "#8b949e", textTransform: "uppercase" }}>Projection 2050</span>
                <div style={{ fontSize: "28px", fontWeight: 900, color: "#ff4d4f", marginTop: "4px" }}>
                  {decision.projection_risque.score_projete}
                </div>
              </div>
              <div style={{
                background: decision.projection_risque.aggravation > 0 ? "rgba(255,77,79,0.08)" : "rgba(63,185,80,0.08)",
                borderRadius: "10px", padding: "14px", textAlign: "center",
                border: `1px solid ${decision.projection_risque.aggravation > 0 ? "rgba(255,77,79,0.3)" : "rgba(63,185,80,0.3)"}`
              }}>
                <span style={{ fontSize: "11px", color: "#8b949e", textTransform: "uppercase" }}>Aggravation</span>
                <div style={{
                  fontSize: "28px", fontWeight: 900,
                  color: decision.projection_risque.aggravation > 0 ? "#ff4d4f" : "#3fb950",
                  marginTop: "4px"
                }}>
                  {decision.projection_risque.aggravation > 0 ? "+" : ""}{decision.projection_risque.aggravation}
                  <span style={{ fontSize: "14px", color: "#8b949e", fontWeight: 400 }}> pts</span>
                </div>
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.15)", borderRadius: "8px", padding: "12px 16px" }}>
              <span style={{ fontSize: "12px", color: "#8b949e" }}>
                Scénario :<strong style={{ color: "#e6edf3" }}> {decision.projection_risque.scenario}</strong>
                {' — '}Horizon :<strong style={{ color: "#e6edf3" }}> {decision.projection_risque.horizon}</strong>
              </span>
              {Object.keys(decision.projection_risque.zones_projetees || {}).length > 0 && (
                <div style={{ marginTop: "8px", display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {Object.entries(decision.projection_risque.zones_projetees).map(([zone, zdata]) => (
                    <span key={zone} style={{
                      padding: "3px 8px", borderRadius: "6px", fontSize: "11px",
                      background: "rgba(255,166,87,0.1)", color: "#ffa657"
                    }}>
                      {zone}: {zdata.risque_projete}/100 ({zdata.evolution})
                    </span>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <p style={{ color: "#8b949e", fontStyle: "italic" }}>
            Données de projection climatique non disponibles pour ce bien.
          </p>
        )}
      </div>

      {/* ──────── SECTION 7 : 📄 Rapport d'analyse synthétique ──────── */}
      <div style={sectionStyle}>
        <h3 style={{ ...sectionTitleStyle, color: "#cfe8ff" }}>
          📄 Rapport d'Analyse Synthétique
        </h3>
        
        {/* Points clés */}
        {decision.synthese_points_cles && decision.synthese_points_cles.length > 0 && (
          <div style={{
            display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "16px"
          }}>
            {decision.synthese_points_cles.map((pt, idx) => (
              <span key={idx} style={{
                padding: "6px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: 600,
                background: "linear-gradient(135deg, rgba(77,166,255,0.15), rgba(77,166,255,0.05))",
                border: "1px solid rgba(77,166,255,0.25)", color: "#79c0ff"
              }}>
                {pt}
              </span>
            ))}
          </div>
        )}

        {/* Rapport synthétique */}
        <div style={{
          background: "rgba(0,0,0,0.2)", borderRadius: "10px",
          padding: "16px 20px", border: "1px solid rgba(255,255,255,0.05)",
          whiteSpace: "pre-wrap" as const, fontSize: "13px", lineHeight: "1.6",
          color: "#e6edf3", fontFamily: "monospace"
        }}>
          {decision.rapport_synthetique}
        </div>

        {/* Avis analyste */}
        <div style={{
          marginTop: "16px", background: "rgba(31,111,235,0.06)",
          borderLeft: "4px solid #1f6feb", padding: "14px 18px",
          borderRadius: "8px"
        }}>
          <span style={{ fontSize: "12px", color: "#58a6ff", textTransform: "uppercase", display: "block", marginBottom: "6px", letterSpacing: "1px", fontWeight: 600 }}>
            Avis du Comité de Crédit (IA)
          </span>
          <p style={{ margin: 0, fontStyle: "italic", fontSize: "14px", lineHeight: "1.5", color: "#cfe8ff" }}>
            "{decision.avis_analyste}"
          </p>
        </div>

        {/* Conditions et vérifications */}
        <div style={{ marginTop: "16px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          {decision.conditions_suspensives && decision.conditions_suspensives.length > 0 && (
            <div style={{ background: "rgba(163,113,247,0.06)", padding: "12px 16px", borderRadius: "8px", borderLeft: "3px solid #a371f7" }}>
              <span style={{ fontSize: "11px", color: "#d2a8ff", textTransform: "uppercase", fontWeight: 600 }}>⚖️ Conditions Suspensives</span>
              <ul style={{ margin: "6px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "#e6edf3" }}>
                {decision.conditions_suspensives.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          )}
          {decision.points_a_verifier && decision.points_a_verifier.length > 0 && (
            <div style={{ background: "rgba(210,153,34,0.06)", padding: "12px 16px", borderRadius: "8px", borderLeft: "3px solid #d29922" }}>
              <span style={{ fontSize: "11px", color: "#d29922", textTransform: "uppercase", fontWeight: 600 }}>⚠️ Vérifications KYC Requises</span>
              <ul style={{ margin: "6px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "#ffe6b3" }}>
                {decision.points_a_verifier.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
          )}
        </div>

        {/* Hard Stops */}
        {decision.hard_stops && decision.hard_stops.length > 0 && (
          <div style={{
            marginTop: "14px", background: "rgba(255,77,79,0.08)",
            borderLeft: "4px solid #ff4d4f", padding: "12px 16px", borderRadius: "8px"
          }}>
            <span style={{ fontSize: "12px", color: "#ff4d4f", fontWeight: 600, textTransform: "uppercase" }}>
              🚫 Règles Bloquantes (Hard Stops)
            </span>
            <ul style={{ margin: "6px 0 0 0", paddingLeft: "16px", fontSize: "13px", color: "#ffb3b3" }}>
              {decision.hard_stops.map((h, i) => <li key={i} style={{ marginBottom: "2px" }}>{h}</li>)}
            </ul>
          </div>
        )}

        {/* Taux et conditions financières */}
        <div style={{ marginTop: "16px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <div style={{ background: "rgba(255,255,255,0.03)", padding: "14px", borderRadius: "10px" }}>
            <span style={{ fontSize: "11px", color: "#8b949e", textTransform: "uppercase", fontWeight: 600 }}>Taux Proposé</span>
            <div style={{ fontSize: "22px", fontWeight: 900, color: riskLevelColor, marginTop: "4px" }}>
              {decision.taux_propose?.toFixed(2)}%
            </div>
            <span style={{ fontSize: "11px", color: "#8b949e" }}>
              Base {((decision.taux_propose || 0) - (decision.majoration_taux || 0)).toFixed(2)}% 
              {decision.majoration_taux > 0 ? ` + ${decision.majoration_taux.toFixed(2)}% risque` : ` ${decision.majoration_taux.toFixed(2)}% bonification`}
            </span>
          </div>
          <div style={{ background: "rgba(255,255,255,0.03)", padding: "14px", borderRadius: "10px" }}>
            <span style={{ fontSize: "11px", color: "#8b949e", textTransform: "uppercase", fontWeight: 600 }}>Exigences Bancaires</span>
            <ul style={{ margin: "6px 0 0 0", paddingLeft: "16px", fontSize: "12px", color: "#e6edf3" }}>
              {(decision.exigences || []).map((e, i) => <li key={i}>{e}</li>)}
              {(decision.exigences || []).length === 0 && <li style={{ color: "#8b949e", fontStyle: "italic" }}>Aucune exigence spécifique</li>}
            </ul>
          </div>
        </div>
      </div>

      {/* ──────── FOOTER : Traçabilité ──────── */}
      <div style={{
        ...sectionStyle, border: "1px dashed rgba(255,255,255,0.1)",
        background: "rgba(0,0,0,0.3)"
      }}>
        <div style={{ fontSize: "12px", color: "#8b949e", lineHeight: "1.6" }}>
          <strong>🔍 Auditabilité & Traçabilité</strong><br />
          <strong>Sources :</strong> Validation KYC via BAN/ADEME. Valeur immobilière via DVF (Gouvernement). Scores de risque via Géorisques (BRGM) et IGN.<br />
          <strong>Calcul :</strong> Taux directeurs, primes de risque et décotes déterminés par le moteur actuariel Python (règles strictes).<br />
          <strong>IA :</strong> L'Agent Mistral est confiné à un rôle de synthèse avec validation stricte du schéma de données.
        </div>
      </div>

    </div>
  );
}
