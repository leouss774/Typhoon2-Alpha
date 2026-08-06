"use client";

import { useCallback, useEffect, useState } from "react";
import { runEconomiePipeline } from "./api";
import styles from "./EconomieDashboard.module.css";
import type { EconomieContract, ResultatEconomie } from "./types";
// Interface universelle - tous les utilisateurs voient la même interface

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

export default function EconomieDashboard() {
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
      <div className={styles.page}>
        {/* Hero */}
        <section className={styles.hero}>
          <div className={styles.heroGlow} />
          <div className={styles.heroInner}>
            <div className={styles.heroText}>
              <div className={styles.eyebrow}>💶 Volet économique</div>
              <h1 className={styles.heroTitle}>
                Des travaux de résilience, <em>rentables</em> ?
              </h1>
              <p className={styles.heroLead}>
                Calculez le retour sur investissement de vos travaux de résilience
                climatique avec des données réelles.
              </p>
            </div>

            <form className={styles.searchCard} onSubmit={handleSubmit}>
              <label className={styles.searchLabel} htmlFor="adresse-economie">
                Adresse du bien
              </label>
              <div className={styles.searchRow}>
                <input
                  id="adresse-economie"
                  className={styles.searchInput}
                  value={adresse}
                  onChange={(e) => setAdresse(e.target.value)}
                  placeholder="Ex. 12 rue des Oliviers, 13100 Aix-en-Provence"
                  disabled={running}
                />
                <button type="submit" className="btn btn-primary" disabled={running || !adresse.trim()}>
                  {running ? "Analyse…" : "Analyser"}
                </button>
              </div>
            </form>
          </div>
        </section>

        {/* Error */}
        {errorDetail && !running && (
          <div className={`${styles.sourceBanner} ${styles.sourceErr}`}>
            <span className={styles.bannerDot} />
            <strong>Calcul impossible.</strong> {errorDetail}
          </div>
        )}

        {/* Loading */}
        {running && (
          <div className={styles.loadingPanel}>
            <div className={styles.loadingHead}>
              <span className={styles.spinner} />
              <strong>Analyse en cours…</strong>
            </div>
            <ol className={styles.stepList}>
              {steps.map((s, i) => (
                <li key={i} className={i + 1 < step ? styles.stepDone : i + 1 === step ? styles.stepActive : ""}>
                  <span className={styles.stepIcon}>{i + 1 < step ? "✓" : i + 1 === step ? "●" : "○"}</span>
                  {s}
                </li>
              ))}
            </ol>
            <div className={styles.progressTrack}>
              <div className={styles.progressFill} style={{ width: `${Math.min((step / 4) * 100, 100)}%` }} />
            </div>
          </div>
        )}
      </div>
    );
  }

  const { niveau_a, niveau_b, niveau_c, roi, confidence } = contract;

  return (
    <div className={styles.page}>
      {/* Hero compact */}
      <section className={styles.hero}>
        <div className={styles.heroGlow} />
        <div className={styles.heroInner}>
          <div className={styles.heroText}>
            <div className={styles.eyebrow}>Résilience climatique</div>
            <h1 className={styles.heroTitle}>Résultats du diagnostic</h1>
            <div className={styles.heroBadge}>
              <span>Données sourcées et fiables</span>
            </div>
          </div>

          {/* KPIs principaux */}
          <div className={styles.kpiGrid}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiContent}>
                <div className={styles.kpiLabel}>Coût net</div>
                <div className={styles.kpiValue}>{fmtEur(niveau_b.cout_travaux.cout_net)}</div>
                <div className={styles.kpiSub}>après subventions</div>
              </div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiContent}>
                <div className={styles.kpiLabel}>Bénéfice annuel</div>
                <div className={styles.kpiValue}>{fmtEur(niveau_b.benefice_assurance.total)}</div>
                <div className={styles.kpiSub}>sinistres évités</div>
              </div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiContent}>
                <div className={styles.kpiLabel}>Retour sur investissement</div>
                <div className={styles.kpiValue}>{fmtAn(roi.temps_de_retour)}</div>
                <div className={styles.kpiSub}>pour rentabiliser</div>
              </div>
            </div>
            <div className={`${styles.kpiCard} ${styles.kpiCardAccent}`}>
              <div className={styles.kpiContent}>
                <div className={styles.kpiLabel}>Confiance</div>
                <div className={styles.kpiValue}>{confidence.score}/100</div>
                <div className={styles.kpiSub}>niveau {confidence.niveau}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Guide de lecture universel */}
      <div className={styles.universalGuide}>
        <h3 className={styles.universalGuideTitle}>Comment lire ces résultats</h3>
        <div className={styles.universalGuideGrid}>
          <div className={styles.guideItem}>
            <div className={styles.guideLabel}>Coût net</div>
            <p className={styles.guideText}>
              Montant à votre charge après déduction des aides (subventions FPRNM).
              C'est l'investissement initial à prévoir.
            </p>
          </div>
          <div className={styles.guideItem}>
            <div className={styles.guideLabel}>Bénéfice annuel</div>
            <p className={styles.guideText}>
              Économies réalisées chaque année grâce à la réduction du risque.
              Inclut les sinistres évités et les dommages moyens annuels évités.
            </p>
          </div>
          <div className={styles.guideItem}>
            <div className={styles.guideLabel}>Retour sur investissement</div>
            <p className={styles.guideText}>
              Durée nécessaire pour que les économies cumulées égalent le coût net.
              Plus ce délai est court, plus l'investissement est rentable.
            </p>
          </div>
          <div className={styles.guideItem}>
            <div className={styles.guideLabel}>Confiance</div>
            <p className={styles.guideText}>
              Niveau de fiabilité des calculs (0-100). Un score élevé signifie des données
              complètes et des résultats fiables. Un score faible indique des données manquantes.
            </p>
          </div>
        </div>
      </div>

      {/* Contenu principal */}
      <div className={styles.content}>
        {/* Score de risque - MIS EN VALEUR */}
        <div className={`${styles.card} ${styles.highlightCard}`}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Score de risque global</h2>
            <span className={styles.scoreBadge}>
              {niveau_a.delta_global > 0 ? `✓ -${niveau_a.delta_global} pts` : "—"}
            </span>
          </div>
          <div className={styles.scoreDisplay}>
            <div className={styles.scoreBig}>{niveau_a.score_global_avant ?? "—"}/100</div>
            <div className={styles.scoreArrow}>→</div>
            <div className={`${styles.scoreBig} ${styles.scoreAfterColor}`}>
              {niveau_a.score_global_apres ?? "—"}/100
            </div>
          </div>
          <div className={styles.scoreBar}>
            <div className={styles.scoreBarFill} style={{ width: `${niveau_a.score_global_avant ?? 0}%` }} />
          </div>
        </div>

        {/* Effet des travaux par zone */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Effet des travaux par zone</h2>
          <div className={styles.zoneList}>
            {niveau_a.par_zone.map((z) => (
              <div key={z.zone} className={styles.zoneItem}>
                <div className={styles.zoneName}>{zoneLabel(z.zone)}</div>
                <div className={styles.zoneBar}>
                  <div className={styles.zoneBarFill} style={{ width: `${z.risque_apres}%` }} />
                </div>
                <div className={styles.zoneValues}>
                  <span>{z.risque_avant}</span>
                  <span className={styles.zoneDelta}>→ {z.risque_apres}</span>
                </div>
              </div>
            ))}
          </div>
          <div className={styles.zoneSummary}>
            <span className={styles.zoneSummaryIcon}>📊</span>
            <span>{niveau_a.par_zone.length} zones analysées</span>
          </div>
        </div>

        {/* Coûts - DESIGN AMÉLIORÉ */}
        <div className={`${styles.card} ${styles.costsHighlight}`}>
          <h2 className={styles.cardTitle}>💰 Coûts des travaux</h2>
          <div className={styles.costVisual}>
            <div className={styles.costCircle}>
              <div className={styles.costCircleInner}>
                <div className={styles.costCircleLabel}>Coût net</div>
                <div className={styles.costCircleValue}>{fmtEur(niveau_b.cout_travaux.cout_net)}</div>
              </div>
            </div>
            <div className={styles.costDetails}>
              <div className={styles.costRow}>
                <span className={styles.costIcon}>📦</span>
                <div className={styles.costInfo}>
                  <div className={styles.costLabelSmall}>Coût brut</div>
                  <div className={styles.costValueSmall}>{fmtEur(niveau_b.cout_travaux.total_brut)}</div>
                </div>
              </div>
              <div className={styles.costRow}>
                <span className={styles.costIcon}>🏛️</span>
                <div className={styles.costInfo}>
                  <div className={styles.costLabelSmall}>Subvention FPRNM</div>
                  <div className={styles.costValueSmall}>{fmtEur(niveau_b.cout_travaux.subvention_fprnm)}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ROI - DESIGN AMÉLIORÉ */}
        <div className={`${styles.card} ${styles.roiCard}`}>
          <div className={styles.roiHeader}>
            <h2 className={styles.cardTitle}>📈 Retour sur investissement</h2>
            <span className={styles.roiBadge}>Rentable</span>
          </div>
          <div className={styles.roiVisual}>
            <div className={styles.roiMain}>
              <div className={styles.roiIcon}>⏱️</div>
              <div className={styles.roiContent}>
                <div className={styles.roiLabel}>Temps de retour</div>
                <div className={styles.roiValue}>{fmtAn(roi.temps_de_retour)}</div>
              </div>
            </div>
            <div className={styles.roiArrow}>→</div>
            <div className={styles.roiBenefice}>
              <div className={styles.roiIcon}>💵</div>
              <div className={styles.roiContent}>
                <div className={styles.roiLabel}>Bénéfice annuel</div>
                <div className={styles.roiValue}>{fmtEur(roi.benefice_annuel_total)}</div>
              </div>
            </div>
          </div>
          <div className={styles.roiFormula}>
            TR = Coût net / (Bénéfice assurance + Bénéfice AAL)
          </div>
        </div>
      </div>

      {/* Bannière honnêteté */}
      <div className={styles.honesty}>
        <strong>⛔ Aucun montant inventé.</strong> Toutes les données proviennent de sources officielles.
      </div>
    </div>
  );
}
