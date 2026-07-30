import { useMemo, useState } from "react";
import PriceChart from "./PriceChart";
import MarketComparison from "./MarketComparison";
import RiskRadar from "./RiskRadar";
import RiskTimeline from "./RiskTimeline";
import LoanSimulator from "./LoanSimulator";
import KPIStrip from "./KPIStrip";
import TrustIndicator from "./TrustIndicator";
import ChatInterface from "../Chat/ChatInterface";

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
  score_risque_bancaire: number;
  score_climatique: number;
  niveau_risque_global: string;
  impact_esg: string;
  risques_identifies: RiskIdentifie[];
  valeur_marche: number;
  valeur_ajustee: number;
  decote_pct: number;
  source_valorisation: string;
  garanties_assurance: GarantieAssurance[];
  recommandation_garantie: string;
  prevention_recommandations: PreventionRecommandation[];
  cout_total_prevention: string;
  projection_risque: ProjectionRisque | null;
  niveau_risque_bancaire: string;
  indice_confiance: number;
  avis_analyste: string;
  rapport_synthetique: string;
  synthese_points_cles: string[];
  analyse_complete_url: string;
  taux_propose: number;
  majoration_taux: number;
  exigences: string[];
  points_a_verifier: string[];
  points_forts: string[];
  points_faibles: string[];
  hard_stops: string[];
  conditions_suspensives: string[];
  source_taux?: string;
  date_taux?: string;
  confiance_taux?: number;
}

interface BankDecisionProps {
  decision: BankDecision;
  adresse?: string;
  typeBien?: string;
  surface?: number;
  sessionId?: string;
}

// ─── Types d'onglets ───
type TabKey = "synthese" | "risques" | "finance" | "rapport";

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "synthese", label: "Synthèse", icon: "S" },
  { key: "risques", label: "Risques", icon: "R" },
  { key: "finance", label: "Finance", icon: "F" },
  { key: "rapport", label: "Rapport", icon: "P" },
];

/** Couleur selon le niveau de risque */
function riskColor(score: number): string {
  if (score >= 60) return "#ef4444";
  if (score >= 35) return "#eab308";
  return "#22c55e";
}

function niveauColor(niveau: string): string {
  if (niveau === "critique" || niveau === "eleve" || niveau === "Élevé") return "#ef4444";
  if (niveau === "modere" || niveau === "Modéré") return "#eab308";
  return "#22c55e";
}

function niveauLabel(niveau: string): string {
  if (niveau === "Faible" || niveau === "faible") return "Faible";
  if (niveau === "Modéré" || niveau === "modere") return "Modéré";
  return "Élevé";
}

/** Interprétation textuelle du score */
function scoreInterpretation(score: number): string {
  if (score >= 60) return "Expertise humaine approfondie nécessaire";
  if (score >= 35) return "Vigilance renforcée — documents supplémentaires requis";
  return "Profil standard — vérifications de routine";
}

/** Badge source de données */
function SourceBadge({ source }: { source: string }) {
  const isRealData = source && !source.includes("Fallback") && !source.includes("Moyenne Nationale");
  return (
    <span
      title={isRealData ? "Données issues d'API gouvernementales en temps réel" : "Valeur estimée par défaut — API indisponible"}
      className="bank-source-badge"
      data-real={isRealData}
    >
      {isRealData ? "Donnees reelles" : "Estimation"}
    </span>
  );
}

export default function BankDecisionPanel({ decision, adresse, typeBien, surface, sessionId }: BankDecisionProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("synthese");

  if (!decision || Object.keys(decision).length === 0) return null;

  const formatEur = (val: number) =>
    new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(val);

  const niveau = decision.niveau_risque_global;
  const scoreColor = riskColor(decision.score_risque_bancaire);
  const climColor = riskColor(decision.score_climatique);
  const isRealEval = decision.source_valorisation && !decision.source_valorisation.includes("Fallback") && !decision.source_valorisation.includes("Moyenne");

  // Regroupement des recommandations par zone
  const recosByZone = useMemo(() => {
    const map: Record<string, PreventionRecommandation[]> = {};
    for (const r of decision.prevention_recommandations || []) {
      if (!map[r.zone]) map[r.zone] = [];
      map[r.zone].push(r);
    }
    return map;
  }, [decision.prevention_recommandations]);

  const handleDownloadPdf = async () => {
    try {
      const resp = await fetch("/api/bank/report/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: `session-${Date.now()}`,
          adresse: adresse || "",
          decision_bancaire: decision,
        }),
      });
      if (!resp.ok) {
        const errText = await resp.text().catch(() => "");
        throw new Error(`HTTP ${resp.status}: ${errText}`);
      }
      const blob = await resp.blob();
      if (blob.size === 0) throw new Error("PDF vide");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `rapport-credit-${Date.now()}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Erreur téléchargement PDF:", err);
      alert("Erreur lors du téléchargement du PDF. Veuillez réessayer.");
    }
  };

  return (
    <div className="bank-panel">
      {/* ──────── HEADER ──────── */}
      <div className="bank-header">
        <div className="bank-header-left">
          <span className="bank-header-icon">              <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 12l2 2 4-4m-3-7a8 8 0 1 0 0 16 8 8 0 0 0 0-16z"/>            </svg>
          </span>
          <div>
            <h2 className="bank-header-title">Analyse de Risque Crédit</h2>
            <p className="bank-header-sub">
              Outil d'aide à la décision — Sans décision automatique
            </p>
          </div>
        </div>
        <div className="bank-header-right">
          <button className="bank-btn-pdf" onClick={handleDownloadPdf}>
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
            Rapport (PDF)
          </button>
          <span className="bank-confiance-badge" data-level={decision.indice_confiance >= 80 ? "high" : decision.indice_confiance >= 50 ? "mid" : "low"}>
            Confiance {decision.indice_confiance}%
          </span>
        </div>
      </div>

      {/* ─── KPI STRIP ─── */}
      <KPIStrip
        valeur_marche={decision.valeur_marche}
        valeur_ajustee={decision.valeur_ajustee}
        score={decision.score_risque_bancaire}
        taux={decision.taux_propose}
        confiance={decision.indice_confiance}
        decote={decision.decote_pct}
      />

      {/* ─── NAVIGATION PAR ONGLETS ─── */}
      <nav className="bank-tabs-nav">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`bank-tab-btn ${activeTab === tab.key ? "active" : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            <span className="bank-tab-icon">{tab.icon}</span>
            <span className="bank-tab-label">{tab.label}</span>
            {activeTab === tab.key && <span className="bank-tab-indicator" />}
          </button>
        ))}
      </nav>

      {/* ─── CONTENU DES ONGLETS ─── */}

      {/* ════════ TAB 1 : SYNTHÈSE ════════ */}
      {activeTab === "synthese" && (
        <div className="bank-tab-content">
          {/* Score de Risque */}
          <div className="bank-section">
            <h3 className="bank-section-title" style={{ color: "var(--color-primary)" }}>
            Score de Risque du Bien
            </h3>
            <div className="bank-score-grid">
              <div className="bank-score-box" style={{ border: `2px solid ${scoreColor}4D` }}>
                <div className="bank-score-label">
                  Score Bancaire
                  <span className="bank-tooltip-icon" title="Formule : (score climatique × 70%) + (méfiance données × 30%)">ⓘ</span>
                </div>
                <div className="bank-score-value" style={{ color: scoreColor }}>
                  {decision.score_risque_bancaire}<span className="bank-score-unit">/100</span>
                </div>
                <div className="bank-score-sub" style={{ color: scoreColor }}>{niveauLabel(niveau)} {niveau}</div>
                <div className="bank-score-interp">{scoreInterpretation(decision.score_risque_bancaire)}</div>
              </div>
              <div className="bank-score-box">
                <div className="bank-score-label">
                  Score Climatique
                  <span className="bank-tooltip-icon" title="Basé sur les données Géorisques (BRGM) : RGA, inondation, canicule, tempête">ⓘ</span>
                </div>
                <div className="bank-score-value" style={{ color: climColor }}>
                  {decision.score_climatique}<span className="bank-score-unit">/100</span>
                </div>
                <div className="bank-score-sub" style={{ color: climColor }}>Georisques</div>
                <div className="bank-score-interp">Risques naturels (BRGM)</div>
              </div>
              <div className="bank-score-box">
                <div className="bank-score-label">
                  Impact ESG
                  <span className="bank-tooltip-icon" title="Critères Environnementaux, Sociaux et de Gouvernance — impact sur le financement">ⓘ</span>
                </div>
                <div className="bank-esg-value" style={{ color: decision.impact_esg === "Éligible au Prêt Vert" ? "var(--color-risk-faible)" : "var(--color-text)" }}>
                  {decision.impact_esg}
                </div>
                <div className="bank-score-interp">
                  {decision.impact_esg === "Éligible au Prêt Vert"
                    ? "Eligible au financement vert (taux bonifie)"
                    : "Bilan climatique standard"}
                </div>
              </div>
            </div>

            {/* Barre d'interprétation */}
            <div className="bank-echange-bar-container">
              <div className="bank-echange-label">Échelle d'interprétation</div>
              <div className="bank-echange-bar">
                <div className="bank-echange-segment faible" title="0-34 : Faible — Profil standard">
                  <span>Faible</span>
                </div>
                <div className="bank-echange-segment modere" title="35-59 : Modéré — Vigilance">
                  <span>Modéré</span>
                </div>
                <div className="bank-echange-segment eleve" title="60-100 : Élevé — Expertise">
                  <span>Élevé</span>
                </div>
              </div>
              <div className="bank-echange-ticks">
                <span>0</span><span>35</span><span>60</span><span>100</span>
              </div>
              <div className="bank-echange-marker" style={{ left: `${decision.score_risque_bancaire}%` }}>
                ▲
              </div>
            </div>
          </div>

          {/* Points forts / Points faibles */}
          <div className="bank-synthese-flash">
            {decision.points_forts && decision.points_forts.length > 0 && (
              <div className="bank-synthese-card fort">
                <div className="bank-synthese-card-header">Points Forts</div>
                <ul className="bank-synthese-list">
                  {decision.points_forts.map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              </div>
            )}
            {decision.points_faibles && decision.points_faibles.length > 0 && (
              <div className="bank-synthese-card faible">
                <div className="bank-synthese-card-header">Points Faibles</div>
                <ul className="bank-synthese-list">
                  {decision.points_faibles.map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              </div>
            )}
          </div>

          {/* Valeur + Simulateur rapide */}
          <div className="bank-section">
            <h3 className="bank-section-title" style={{ color: "var(--color-primary)" }}>
              Valeur du Bien & Simulation
              <SourceBadge source={decision.source_valorisation} />
            </h3>
            <div className="bank-score-grid">
              <div className="bank-score-box">
                <div className="bank-score-label">Valeur Marché (DVF)</div>
                <div className="bank-score-value" style={{ fontSize: "1.5rem", color: "var(--color-text)" }}>
                  {formatEur(decision.valeur_marche)}
                </div>
                <div className="bank-score-source" data-real={isRealEval}>
                  {isRealEval ? "" : ""}Source : {decision.source_valorisation || "OpenData"}
                </div>
                {!isRealEval && <div className="bank-score-fallback">API DVF momentanément indisponible</div>}
              </div>
              <div className="bank-score-box">
                <div className="bank-score-label" style={{ color: "#b91c1c" }}>Décote Risque Climatique</div>
                <div className="bank-score-value" style={{ fontSize: "1.5rem", color: "#b91c1c" }}>-{decision.decote_pct}%</div>
                <div className="bank-score-interp">
                  {decision.decote_pct === 0 ? "Aucune décote" : decision.decote_pct <= 5 ? "Décote légère" : "Décote significative"}
                </div>
              </div>
              <div className="bank-score-box highlight">
                <div className="bank-score-label" style={{ color: "var(--color-primary)", fontWeight: 700 }}>Valeur de Garantie Finale</div>
                <div className="bank-score-value" style={{ fontSize: "1.5rem", color: "var(--color-primary)" }}>
                  {formatEur(decision.valeur_ajustee)}
                </div>
                <div className="bank-score-interp">Montant retenu pour le prêt</div>
              </div>
            </div>
            <div className="bank-calc-box">
              <strong>Calcul :</strong> {formatEur(decision.valeur_marche)} x (1 - {decision.decote_pct}%) = {formatEur(decision.valeur_ajustee)}
            </div>
          </div>

          {/* Hard Stops en alerte */}
          {decision.hard_stops && decision.hard_stops.length > 0 && (
            <div className="bank-hardstop-box">
              <span className="bank-hardstop-title">Regles Bloquantes (Hard Stops)</span>
              <ul className="bank-hardstop-list">
                {decision.hard_stops.map((h, i) => <li key={i}>{h}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ════════ TAB 2 : RISQUES ════════ */}
      {activeTab === "risques" && (
        <div className="bank-tab-content">
          {/* Risques identifiés + Radar */}
          <div className="bank-section">
            <h3 className="bank-section-title" style={{ color: "var(--color-risk-critique)" }}>
              Principaux Risques Identifies
              <span className="bank-section-subtitle">— Radar multicritère</span>
            </h3>
            <div className="bank-risk-layout">
              {decision.risques_identifies && decision.risques_identifies.length > 0 ? (
                <div className="bank-risk-list">
                  {decision.risques_identifies.map((risk, idx) => {
                    const barColor = niveauColor(risk.niveau);
                    return (
                      <div key={idx} className="bank-risk-item">
                        <div className="bank-risk-header">
                          <span className="bank-risk-name">{risk.nom}</span>
                          <span className="bank-risk-score-label" style={{ color: barColor }}>
                            {risk.score}/100 — {risk.niveau}
                          </span>
                        </div>
                        <div className="bank-risk-bar-bg">
                          <div className="bank-risk-bar-fill" style={{ width: `${risk.score}%`, background: `linear-gradient(90deg, ${barColor}88, ${barColor})` }} />
                        </div>
                        <div className="bank-risk-desc">
                          Zone : <strong>{risk.zone_impactee}</strong>
                          {risk.description && ` — ${risk.description.slice(0, 100)}`}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="bank-empty-text">Aucun risque majeur identifié.</p>
              )}
              {decision.risques_identifies && decision.risques_identifies.length > 0 && (
                <div className="bank-radar-wrapper">
                  <RiskRadar risques={decision.risques_identifies} />
                </div>
              )}
            </div>
          </div>

          {/* Timeline Projection */}
          {decision.projection_risque ? (
            <RiskTimeline projection={decision.projection_risque} />
          ) : (
            <div className="bank-section">
              <h3 className="bank-section-title" style={{ color: "var(--color-risk-eleve)" }}>
                Projection de l'Evolution du Risque
              </h3>
              <p className="bank-empty-text">Données de projection climatique non disponibles pour ce bien.</p>
            </div>
          )}

          {/* Recommandations de prévention */}
          <div className="bank-section">
            <h3 className="bank-section-title" style={{ color: "var(--color-primary)" }}>
              Recommandations de Prevention
            </h3>
            {decision.prevention_recommandations && decision.prevention_recommandations.length > 0 ? (
              <>
                <div className="bank-prevention-tags">
                  {Object.entries(recosByZone).map(([zone, recos]) => (
                    <span key={zone} className="bank-prevention-tag">
                      {zone} ({recos.length})
                    </span>
                  ))}
                  <span className="bank-prevention-total">
                    Total : {decision.cout_total_prevention}
                  </span>
                </div>
                <div className="bank-prevention-list">
                  {decision.prevention_recommandations.map((r, idx) => (
                    <div key={idx} className="bank-prevention-item">
                      <span className="bank-prevention-prio" style={{
                        background: r.priorite <= 3 ? "#ef4444" : r.priorite <= 6 ? "#eab308" : "#22c55e"
                      }}>
                        {r.priorite}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div className="bank-prevention-text">{r.travaux}</div>
                        <div className="bank-prevention-meta">
                          Zone : {r.zone} — Coût : {r.cout_estime} — Gain résilience : +{r.gain_resilience}%
                          {r.aide_financiere && ` — Aide : ${r.aide_financiere}`}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="bank-empty-text">Aucune recommandation de prévention spécifique pour ce bien.</p>
            )}
          </div>
        </div>
      )}

      {/* ════════ TAB 3 : FINANCE ════════ */}
      {activeTab === "finance" && (
        <div className="bank-tab-content">
          {/* Simulateur de prêt */}            <LoanSimulator
            valeur_ajustee={decision.valeur_ajustee}
            taux_propose={decision.taux_propose}
            majoration_taux={decision.majoration_taux}
            source_taux={decision.source_taux}
            date_taux={decision.date_taux}
            confiance_taux={decision.confiance_taux}
          />

          {/* Comparaison Marché */}
          <MarketComparison
            adresse={adresse || ""}
            type_bien={typeBien || "Maison"}
            surface={surface || 100}
          />

          {/* Graphique évolution des prix DVF */}
          <PriceChart
            adresse={adresse || ""}
            type_bien={typeBien || "Maison"}
            surface={surface || 100}
          />

          {/* Taux et conditions */}
          <div className="bank-section">
            <h3 className="bank-section-title" style={{ color: "var(--color-primary)" }}>
              Conditions de Financement
            </h3>
            <div className="bank-taux-grid">
              <div className="bank-taux-box">
                <div className="bank-taux-label">Taux Proposé</div>
                <div className="bank-taux-value" style={{ color: scoreColor }}>
                  {decision.taux_propose?.toFixed(2)}%
                </div>
                <div className="bank-taux-sub">
                  Base {((decision.taux_propose || 0) - (decision.majoration_taux || 0)).toFixed(2)}% 
                  {decision.majoration_taux > 0 ? ` + ${decision.majoration_taux.toFixed(2)}% risque` : ` ${decision.majoration_taux.toFixed(2)}% bonification`}
                </div>
              </div>
              <div className="bank-taux-box">
                <div className="bank-taux-label">Exigences Bancaires</div>
                <ul className="bank-taux-list">
                  {(decision.exigences || []).map((e, i) => <li key={i}>{e}</li>)}
                  {(decision.exigences || []).length === 0 && <li className="bank-empty-text">Aucune</li>}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ════════ TAB 4 : RAPPORT ════════ */}
      {activeTab === "rapport" && (
        <div className="bank-tab-content">
          {/* Rapport synthétique */}
          <div className="bank-section">
            <h3 className="bank-section-title" style={{ color: "var(--color-primary)" }}>
              Rapport d'Analyse Synthetique
            </h3>

            {decision.synthese_points_cles && decision.synthese_points_cles.length > 0 && (
              <div className="bank-points-cles">
                {decision.synthese_points_cles.map((pt, idx) => (
                  <span key={idx} className="bank-point-chip">{pt}</span>
                ))}
              </div>
            )}

            <div className="bank-rapport-box">{decision.rapport_synthetique}</div>

            <div className="bank-avis-box">
              <span className="bank-avis-title">Avis du Comité de Crédit (IA)</span>
              <p className="bank-avis-text">«&nbsp;{decision.avis_analyste}&nbsp;»</p>
            </div>
          </div>

          {/* Garanties Assurance */}
          <div className="bank-section">
            <h3 className="bank-section-title" style={{ color: "var(--color-primary)" }}>
              Garanties d'Assurance Recommandees
            </h3>
            {decision.garanties_assurance && decision.garanties_assurance.length > 0 ? (
              <div className="bank-garantie-grid">
                {decision.garanties_assurance.map((g, idx) => (
                  <div key={idx} className={`bank-garantie-item ${g.obligatoire ? "obligatoire" : ""}`}>
                    <span className="bank-garantie-icon">{g.obligatoire ? "🔴" : "🟡"}</span>
                    <div style={{ flex: 1 }}>
                      <div className="bank-garantie-header">
                        <span className="bank-garantie-type">{g.type}</span>
                        <span className="bank-garantie-badge" data-obligatoire={g.obligatoire}>
                          {g.obligatoire ? "Obligatoire" : "Recommandée"}
                        </span>
                      </div>
                      <p className="bank-garantie-detail">{g.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="bank-empty-text">Aucune garantie d'assurance trouvée.</p>
            )}
            {decision.recommandation_garantie && (
              <div className="bank-montage-box">
                Montage juridique recommande : <strong>{decision.recommandation_garantie}</strong>
              </div>
            )}
          </div>

          {/* Conditions et vérifications */}
          <div className="bank-section">
            <h3 className="bank-section-title" style={{ color: "var(--color-primary)" }}>
              Conditions & Verifications
            </h3>
            <div className="bank-verif-grid">
              {decision.conditions_suspensives && decision.conditions_suspensives.length > 0 && (
                <div className="bank-verif-box conditions">
                  <span className="bank-verif-title">Conditions Suspensives</span>
                  <ul className="bank-verif-list">
                    {decision.conditions_suspensives.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </div>
              )}
              {decision.points_a_verifier && decision.points_a_verifier.length > 0 && (
                <div className="bank-verif-box kyc">
                  <span className="bank-verif-title">Verifications KYC Requises</span>
                  <ul className="bank-verif-list">
                    {decision.points_a_verifier.map((p, i) => <li key={i}>{p}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Trust Indicator */}
          <TrustIndicator
            items={[
              {
                label: "Valeur Marché (DVF)",
                value: formatEur(decision.valeur_marche),
                trust: decision.indice_confiance,
                source: "DGFiP — Demandes de Valeurs Foncieres",
                detail: `Source : ${decision.source_valorisation || "Base DVF locale (DGFiP)"}. ${decision.indice_confiance >= 80 ? "Donnees recentes et en quantite suffisante." : "Donnees limitees ou anciennes."}`,
                isExpired: decision.indice_confiance < 30,
              },
              {
                label: "Score Climatique",
                value: `${decision.score_climatique}/100`,
                trust: decision.score_climatique > 0 ? 85 : 0,
                source: "Georisques (BRGM) — Donnees publiques officielles",
                detail: "Base sur les donnees BRGM/IGN. Source fiable a 85%.",
              },
              {
                label: "Donnees Declaratives",
                value: `${decision.indice_confiance}% de confiance`,
                trust: decision.indice_confiance,
                source: "Validation croisee BAN + ADEME + Coherence structurelle",
                detail: `${decision.indice_confiance >= 80 ? "Coherence verifiee avec les bases officielles" : "Incoherences detectees — documents justificatifs requis"}`,
              },
              {
                label: "Taux Directeurs",
                value: `${decision.taux_propose?.toFixed(2) || "N/A"}%`,
                trust: decision.confiance_taux ?? 90,
                source: `${decision.source_taux || "Banque de France"}`, 
                detail: `Source : ${decision.source_taux || "Banque de France"} (${decision.date_taux || "N/A"}). Base ${((decision.taux_propose || 0) - (decision.majoration_taux || 0)).toFixed(2)}% + majoration ${(decision.majoration_taux || 0).toFixed(2)}% pour risque climatique.`, 
              },
              {
                label: "Projection 2050",
                value: decision.projection_risque ? `${decision.projection_risque.score_projete}/100` : "N/A",
                trust: decision.projection_risque ? 70 : 0,
                source: "Scenario CMIP6 — GIEC",
                detail: "Projection a horizon 2050 basee sur les scenarios climatiques CMIP6. Incertitude inherente aux projections long terme.",
              },
            ]}
          />

          {/* Footer traçabilité */}
          <div className="bank-footer">
            <div className="bank-footer-text">
              <strong>Auditabilite & Traçabilite</strong><br />
              <strong>Sources :</strong> Validation KYC via BAN/ADEME. Valeur immobilière via DVF (DGFiP — Gouvernement). Scores de risque via Géorisques (BRGM) et IGN.<br />
              <strong>Calcul :</strong> Taux directeurs, primes de risque et décotes déterminés par le moteur actuariel Python (règles strictes).<br />
              <strong>IA :</strong> L'Agent Mistral est confiné à un rôle de synthèse avec validation stricte du schéma de données.<br />
              <strong>Derniere mise a jour des taux :</strong> {decision.date_taux || "N/A"} — {decision.source_taux || "Banque de France"} (confiance {decision.confiance_taux ?? 90}%)
            </div>
          </div>

          {/* 💬 Conseil IA — ChatInterface intégré */}
          {sessionId && (
            <div className="bank-section">
              <h3 className="bank-section-title" style={{ color: "var(--color-primary)" }}>
                💬 Conseil Typhoon — Posez vos questions
              </h3>
              <ChatInterface sessionId={sessionId} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}