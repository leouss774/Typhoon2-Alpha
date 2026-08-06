"use client";

import { useState } from "react";
import styles from "./UserProfileExplainer.module.css";

export type UserProfile = "proprietaire" | "banquier" | "assureur" | "promoteur";

interface ProfileConfig {
  id: UserProfile;
  label: string;
  shortLabel: string;
  description: string;
}

const PROFILES: ProfileConfig[] = [
  {
    id: "proprietaire",
    label: "Particulier",
    shortLabel: "Particulier",
    description: "Explications simples et pratiques",
  },
  {
    id: "banquier",
    label: "Banquier / Crédit",
    shortLabel: "Banquier",
    description: "Indicateurs financiers et risque crédit",
  },
  {
    id: "assureur",
    label: "Assureur",
    shortLabel: "Assureur",
    description: "Données techniques pour évaluation des sinistres",
  },
  {
    id: "promoteur",
    label: "Promoteur immobilier",
    shortLabel: "Promoteur",
    description: "Analyse ROI et valorisation",
  },
];

interface IndicatorExplanation {
  simple: string;
  detail: string;
  profiles: Record<UserProfile, { label: string; explanation: string }>;
}

const INDICATORS: Record<string, IndicatorExplanation> = {
  cout_net: {
    simple: "Coût des travaux après déduction des aides",
    detail:
      "Coût total des travaux diminué de la subvention FPRNM (80%, plafond 36 000€).",
    profiles: {
      proprietaire: {
        label: "Votre effort financier",
        explanation:
          "Montant à votre charge après aides. Exemple : 50 000€ de travaux → 10 000€ à payer (subvention 80%).",
      },
      banquier: {
        label: "Investissement à financer",
        explanation:
          "Montant net à financer. Détermine la capacité d'emprunt et le ratio dette/valeur du bien.",
      },
      assureur: {
        label: "Investissement prévention",
        explanation:
          "Montant investi dans la prévention. Peut influencer la modulation de surprime future (cadre réglementaire 2024).",
      },
      promoteur: {
        label: "Coût de mise en conformité",
        explanation:
          "Investissement pour valoriser le bien. Impact sur le prix de revient et la marge. Vérifier l'éligibilité aux aides.",
      },
    },
  },
  benefice_annuel: {
    simple: "Économies annuelles générées par les travaux",
    detail:
      "Somme des économies d'assurance (sinistres évités) et des dommages moyens annuels évités (AAL).",
    profiles: {
      proprietaire: {
        label: "Votre économie annuelle",
        explanation:
          "Économies réalisées grâce à la réduction du risque. Exemple : 5% de sinistre à 16 500€ = 825€/an d'économies en moyenne.",
      },
      banquier: {
        label: "Flux de trésorerie additionnel",
        explanation:
          "Économies annuelles qui améliorent la capacité de remboursement. À intégrer dans le calcul du DSCR.",
      },
      assureur: {
        label: "Sinistres évités",
        explanation:
          "Montant des sinistres évités grâce aux travaux. Basé sur la fréquence CATNAT et le coût moyen (CCR/Cour des Comptes).",
      },
      promoteur: {
        label: "Valeur ajoutée annuelle",
        explanation:
          "Économies annuelles qui améliorent la rentabilité. À intégrer dans le business plan et le calcul du NPV.",
      },
    },
  },
  temps_retour: {
    simple: "Durée pour rentabiliser l'investissement",
    detail:
      "Temps nécessaire pour que les économies cumulées égalent le coût net. Formule : Coût net / Bénéfice annuel total.",
    profiles: {
      proprietaire: {
        label: "Délai de rentabilité",
        explanation:
          "Après combien d'années l'investissement est-il remboursé ? Exemple : 10 000€ / 1 000€ par an = 10 ans. C'est un placement sûr et durable.",
      },
      banquier: {
        label: "Indicateur de risque crédit",
        explanation:
          "Durée de remboursement naturel. Un TR court (< 10 ans) est un signal positif. Au-delà de 20 ans, le risque augmente.",
      },
      assureur: {
        label: "Horizon de sinistralité",
        explanation:
          "Période de compensation de l'investissement par les économies. Un TR court indique une prévention efficace.",
      },
      promoteur: {
        label: "ROI du projet",
        explanation:
          "Durée de retour sur investissement. Un TR < 15 ans est généralement attractif pour un promoteur immobilier.",
      },
    },
  },
  score_risque: {
    simple: "Note d'exposition aux risques (0-100)",
    detail:
      "Score composite basé sur l'exposition aux inondations, RGA et autres aléas. Le delta montre l'amélioration après travaux.",
    profiles: {
      proprietaire: {
        label: "Cote de danger",
        explanation:
          "Note sur 100 de l'exposition de votre bien. Plus c'est bas, mieux c'est. Les travaux réduisent cette note. Exemple : 75 → 55 = 20 points gagnés.",
      },
      banquier: {
        label: "Notation risque crédit",
        explanation:
          "Score de risque physique. Impact sur la valeur du collatéral. Un score > 70 peut nécessiter une assurance spécifique.",
      },
      assureur: {
        label: "Exposition au risque",
        explanation:
          "Score calculé par le modèle (F × V)^0.5. Permet d'évaluer la probabilité de sinistre et de calibrer la surprime.",
      },
      promoteur: {
        label: "Impact sur la valorisation",
        explanation:
          "Score qui influence la valeur et la commercialisation. Une réduction de risque est un argument de vente et peut justifier un prix premium.",
      },
    },
  },
  confiance: {
    simple: "Fiabilité des calculs (0-100)",
    detail:
      "Score basé sur la disponibilité des données et l'absence d'hypothèses. Plus il est élevé, plus les chiffres sont fiables.",
    profiles: {
      proprietaire: {
        label: "Fiabilité des résultats",
        explanation:
          "Confiance dans les calculs. > 70 : résultats fiables pour vos projets. < 40 : estimations moins précises (données manquantes).",
      },
      banquier: {
        label: "Qualité de l'analyse",
        explanation:
          "Robustesse des données. > 70 : utilisable pour l'instruction du dossier. En dessous : vérifications complémentaires nécessaires.",
      },
      assureur: {
        label: "Solidité méthodologique",
        explanation:
          "Confiance basée sur la disponibilité des données DVF, CATNAT et la qualité des sources. Score élevé = analyse complète et traçable.",
      },
      promoteur: {
        label: "Fiabilité pour la décision",
        explanation:
          "Qualité des données disponibles. > 60 : décisions d'investissement éclairées possibles. En dessous : études complémentaires à prévoir.",
      },
    },
  },
};

interface UserProfileExplainerProps {
  currentProfile: UserProfile;
  onProfileChange: (profile: UserProfile) => void;
}

export default function UserProfileExplainer({
  currentProfile,
  onProfileChange,
}: UserProfileExplainerProps) {
  const [selectedIndicator, setSelectedIndicator] = useState<string | null>(null);

  return (
    <div className={styles.container}>
        <div className={styles.profileSelector}>
          <div className={styles.profileLabel}>
            <span className={styles.profileText}>Votre profil :</span>
          </div>
          <div className={styles.profileButtons}>
            {PROFILES.map((profile) => (
              <button
                key={profile.id}
                className={`${styles.profileButton} ${
                  currentProfile === profile.id ? styles.profileButtonActive : ""
                }`}
                onClick={() => onProfileChange(profile.id)}
                title={profile.description}
              >
                <span className={styles.profileButtonLabel}>{profile.shortLabel}</span>
              </button>
            ))}
          </div>
        </div>

      <div className={styles.explanationPanel}>
        <h3 className={styles.explanationTitle}>
          {PROFILES.find((p) => p.id === currentProfile)?.label}
        </h3>
        <p className={styles.explanationText}>
          {PROFILES.find((p) => p.id === currentProfile)?.description}
        </p>
      </div>

      <div className={styles.indicatorsGrid}>
        {Object.entries(INDICATORS).map(([key, indicator]) => (
          <div
            key={key}
            className={`${styles.indicatorCard} ${
              selectedIndicator === key ? styles.indicatorCardActive : ""
            }`}
            onClick={() =>
              setSelectedIndicator(selectedIndicator === key ? null : key)
            }
          >
            <div className={styles.indicatorHeader}>
              <h4 className={styles.indicatorTitle}>
                {indicator.profiles[currentProfile].label}
              </h4>
              <span className={styles.indicatorBadge}>?</span>
            </div>
            <p className={styles.indicatorSimple}>{indicator.simple}</p>
            {selectedIndicator === key && (
              <div className={styles.indicatorDetail}>
                <p className={styles.indicatorExplanation}>
                  {indicator.profiles[currentProfile].explanation}
                </p>
                <div className={styles.indicatorTechnical}>
                  <p>{indicator.detail}</p>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}