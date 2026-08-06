import { useCallback, useEffect, useState } from "react";
import { runEconomiePipeline } from "./economie/api";
import type { EconomieContract, ResultatEconomie } from "./economie/types";
import "./economie/economie.css";

/* ─────────────────────────── Formatage ─────────────────────────── */

const nfEur = new Intl.NumberFormat("fr-FR", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});
const nfAn = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

const fmtEur = (bloc: any) => {
  if (!bloc || bloc.statut === "null") return "Non calculé";
  const val = bloc.valeur ?? (bloc.min + bloc.max) / 2;
  return val == null ? "Non calculé" : nfEur.format(val);
};
const fmtAn = (bloc: any) => {
  if (!bloc || bloc.statut === "null") return "Non calculé";
  const val = bloc.valeur ?? (bloc.min + bloc.max) / 2;
  return val == null ? "Non calculé" : `${nfAn.format(val)} ans`;
};

const ZONE_LABELS: Record<string, string> = {
  fondations: "Fondations",
  murs_nord: "Mur nord",
  murs_sud: "Mur sud",
  murs_est: "Mur est",
  murs_ouest: "Mur ouest",
  toiture: "Toiture",
  sous_sol: "Sous-sol",
};

const zoneLabel = (z: string) => ZONE_LABELS[z] ?? z;

/* ═══════════════════════ COMPOSANT PRINCIPAL ═══════════════════════ */

export default function Economie() {
  const [adresse, setAdresse] = useState("");
  const [running, setRunning] = useState(false);
  const [step, setStep] = useState(0);
  const [resultat, setResultat] = useState<ResultatEconomie | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const contract = resultat?.contract ?? null;

  /* Animation des étapes pendant le pipeline réel. */
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(() => {
      setStep((s) => {
        if (s >= 4) {
          clearInterval(interval);
          return s;
        }
        return s + 1;
      });
    }, 420);
    return () => clearInterval(interval);
  }, [running]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!adresse.trim() || running) return;
      setRunning(true);
      setStep(1);
      setErrorDetail(null);
      setResultat(null);
      try {
        const res = await runEconomiePipeline(adresse);
        setResultat(res);
      } catch (err) {
        setErrorDetail(
          err instanceof Error ? err.message : "Erreur inconnue du backend"
        );
      } finally {
        setRunning(false);
      }
    },
    [adresse, running]
  );

  const steps = [
    "Collecte des données",
    "Scoring de risque",
    "Calcul ROI",
    "Contrat prêt",
  ];

  if (!contract) {
    return (
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "0 24px 56px" }}>
        {/* Hero */}
        <section className="economie-hero">
          <div className="economie-heroGlow" />
          <div className="economie-heroInner">
            <div className="economie-heroText">
              <div className="economie-eyebrow">💶 Volet économique</div>
              <h1 className="economie-heroTitle">
                Des travaux de résilience, <em>rentables</em> ?
              </h1>
              <p className="economie-heroLead">
                Calculez le retour sur investissement de vos travaux de résilience
                climatique avec des données réelles.
              </p>
            </div>

            <form className="economie-searchCard" onSubmit={handleSubmit}>
              <label className="economie-searchLabel" htmlFor="adresse-economie">
                Adresse du bien
              </label>
              <div className="economie-searchRow">
                <input
                  id="adresse-economie"
                  className="economie-searchInput"
                  value={adresse}
                  onChange={(e) => setAdresse(e.target.value)}
                  placeholder="Ex. 12 rue des Oliviers, 13100 Aix-en-Provence"
                  disabled={running}
                />
                <button type="submit" className="economie-btn economie-btn-primary" disabled={running || !adresse.trim()}>
                  {running ? "Analyse…" : "Analyser"}
                </button>
              </div>
            </form>
          </div>
        </section>

        {/* Error */}
        {errorDetail && !running && (
          <div className="economie-sourceBanner economie-sourceErr">
            <span className="economie-bannerDot" />
            <strong>Calcul impossible.</strong> {errorDetail}
          </div>
        )}

        {/* Loading */}
        {running && (
          <div className="economie-loadingPanel">
            <div className="economie-loadingHead">
              <span className="economie-spinner" />
              <strong>Analyse en cours…</strong>
            </div>
            <ol className="economie-stepList">
              {steps.map((s, i) => (
                <li key={i} className={i + 1 < step ? "economie-stepDone" : i + 1 === step ? "economie-stepActive" : ""}>
                  <span className="economie-stepIcon">{i + 1 < step ? "✓" : i + 1 === step ? "●" : "○"}</span>
                  {s}
                </li>
              ))}
            </ol>
            <div className="economie-progressTrack">
              <div className="economie-progressFill" style={{ width: `${Math.min((step / 4) * 100, 100)}%` }} />
            </div>
          </div>
        )}
      </div>
    );
  }

  const { niveau_a, niveau_b, niveau_c, roi, confidence } = contract;

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "0 24px 56px" }}>
      {/* Hero compact */}
      <section className="economie-hero">
        <div className="economie-heroGlow" />
        <div className="economie-heroInner">
          <div className="economie-heroText">
            <div className="economie-eyebrow">Résilience climatique</div>
            <h1 className="economie-heroTitle">Résultats du diagnostic</h1>
            <div className="economie-heroBadge">
              <span>Données sourcées et fiables</span>
            </div>
          </div>

          {/* KPIs principaux */}
          <div className="economie-kpiGrid">
            <div className="economie-kpiCard">
              <div className="economie-kpiContent">
                <div className="economie-kpiLabel">Coût net</div>
                <div className="economie-kpiValue">{fmtEur(niveau_b.cout_travaux.cout_net)}</div>
                <div className="economie-kpiSub">après subventions</div>
              </div>
            </div>
            <div className="economie-kpiCard">
              <div className="economie-kpiContent">
                <div className="economie-kpiLabel">Bénéfice annuel</div>
                <div className="economie-kpiValue">{fmtEur(niveau_b.benefice_assurance.total)}</div>
                <div className="economie-kpiSub">sinistres évités</div>
              </div>
            </div>
            <div className="economie-kpiCard">
              <div className="economie-kpiContent">
                <div className="economie-kpiLabel">Retour sur investissement</div>
                <div className="economie-kpiValue">{fmtAn(roi.temps_de_retour)}</div>
                <div className="economie-kpiSub">pour rentabiliser</div>
              </div>
            </div>
            <div className="economie-kpiCard economie-kpiCardAccent">
              <div className="economie-kpiContent">
                <div className="economie-kpiLabel">Confiance</div>
                <div className="economie-kpiValue">{confidence.score}/100</div>
                <div className="economie-kpiSub">niveau {confidence.niveau}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Guide de lecture universel */}
      <div className="economie-universalGuide">
        <h3 className="economie-universalGuideTitle">Comment lire ces résultats</h3>
        <div className="economie-universalGuideGrid">
          <div className="economie-guideItem">
            <div className="economie-guideLabel">Coût net</div>
            <p className="economie-guideText">
              Montant à votre charge après déduction des aides (subventions FPRNM).
              C'est l'investissement initial à prévoir.
            </p>
          </div>
          <div className="economie-guideItem">
            <div className="economie-guideLabel">Bénéfice annuel</div>
            <p className="economie-guideText">
              Économies réalisées chaque année grâce à la réduction du risque.
              Inclut les sinistres évités et les dommages moyens annuels évités.
            </p>
          </div>
          <div className="economie-guideItem">
            <div className="economie-guideLabel">Retour sur investissement</div>
            <p className="economie-guideText">
              Durée nécessaire pour que les économies cumulées égalent le coût net.
              Plus ce délai est court, plus l'investissement est rentable.
            </p>
          </div>
          <div className="economie-guideItem">
            <div className="economie-guideLabel">Confiance</div>
            <p className="economie-guideText">
              Niveau de fiabilité des calculs (0-100). Un score élevé signifie des données
              complètes et des résultats fiables. Un score faible indique des données manquantes.
            </p>
          </div>
        </div>
      </div>

      {/* Contenu principal */}
      <div className="economie-content">
        {/* Score de risque - MIS EN VALEUR */}
        <div className="economie-card economie-highlightCard">
          <div className="economie-cardHeader">
            <h2 className="economie-cardTitle">Score de risque global</h2>
            <span className="economie-scoreBadge">
              {niveau_a.delta_global > 0 ? `✓ -${niveau_a.delta_global} pts` : "—"}
            </span>
          </div>
          <div className="economie-scoreDisplay">
            <div className="economie-scoreBig">{niveau_a.score_global_avant ?? "—"}/100</div>
            <div className="economie-scoreArrow">→</div>
            <div className="economie-scoreBig economie-scoreAfterColor">
              {niveau_a.score_global_apres ?? "—"}/100
            </div>
          </div>
          <div className="economie-scoreBar">
            <div className="economie-scoreBarFill" style={{ width: `${niveau_a.score_global_avant ?? 0}%` }} />
          </div>
        </div>

        {/* Effet des travaux par zone */}
        <div className="economie-card">
          <h2 className="economie-cardTitle">Effet des travaux par zone</h2>
          <div className="economie-zoneList">
            {niveau_a.par_zone.map((z) => (
              <div key={z.zone} className="economie-zoneItem">
                <div className="economie-zoneName">{zoneLabel(z.zone)}</div>
                <div className="economie-zoneBar">
                  <div className="economie-zoneBarFill" style={{ width: `${z.risque_apres}%` }} />
                </div>
                <div className="economie-zoneValues">
                  <span>{z.risque_avant}</span>
                  <span className="economie-zoneDelta">→ {z.risque_apres}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="economie-zoneSummary">
            <span className="economie-zoneSummaryIcon">📊</span>
            <span>{niveau_a.par_zone.length} zones analysées</span>
          </div>
        </div>

        {/* Coûts - DESIGN AMÉLIORÉ */}
        <div className="economie-card economie-costsHighlight">
          <h2 className="economie-cardTitle">💰 Coûts des travaux</h2>
          <div className="economie-costVisual">
            <div className="economie-costCircle">
              <div className="economie-costCircleInner">
                <div className="economie-costCircleLabel">Coût net</div>
                <div className="economie-costCircleValue">{fmtEur(niveau_b.cout_travaux.cout_net)}</div>
              </div>
            </div>
            <div className="economie-costDetails">
              <div className="economie-costRow">
                <span className="economie-costIcon">📦</span>
                <div className="economie-costInfo">
                  <div className="economie-costLabelSmall">Coût brut</div>
                  <div className="economie-costValueSmall">{fmtEur(niveau_b.cout_travaux.total_brut)}</div>
                </div>
              </div>
              <div className="economie-costRow">
                <span className="economie-costIcon">🏛️</span>
                <div className="economie-costInfo">
                  <div className="economie-costLabelSmall">Subvention FPRNM</div>
                  <div className="economie-costValueSmall">{fmtEur(niveau_b.cout_travaux.subvention_fprnm)}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ROI - DESIGN AMÉLIORÉ */}
        <div className="economie-card economie-roiCard">
          <div className="economie-roiHeader">
            <h2 className="economie-cardTitle">📈 Retour sur investissement</h2>
            <span className="economie-roiBadge">Rentable</span>
          </div>
          <div className="economie-roiVisual">
            <div className="economie-roiMain">
              <div className="economie-roiIcon">⏱️</div>
              <div className="economie-roiContent">
                <div className="economie-roiLabel">Temps de retour</div>
                <div className="economie-roiValue">{fmtAn(roi.temps_de_retour)}</div>
              </div>
            </div>
            <div className="economie-roiArrow">→</div>
            <div className="economie-roiBenefice">
              <div className="economie-roiIcon">💵</div>
              <div className="economie-roiContent">
                <div className="economie-roiLabel">Bénéfice annuel</div>
                <div className="economie-roiValue">{fmtEur(roi.benefice_annuel_total)}</div>
              </div>
            </div>
          </div>
          <div className="economie-roiFormula">
            TR = Coût net / (Bénéfice assurance + Bénéfice AAL)
          </div>
        </div>
      </div>

      {/* Bannière honnêteté */}
      <div className="economie-honesty">
        <strong>⛔ Aucun montant inventé.</strong> Toutes les données proviennent de sources officielles.
      </div>
    </div>
  );
}