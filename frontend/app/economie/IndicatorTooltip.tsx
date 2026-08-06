"use client";

import { useState } from "react";
import styles from "./IndicatorTooltip.module.css";

export type UserProfile = "proprietaire" | "banquier" | "assureur" | "promoteur";

interface ProfileConfig {
  id: UserProfile;
  label: string;
  description: string;
}

const PROFILES: ProfileConfig[] = [
  {
    id: "proprietaire",
    label: "Particulier",
    description: "Explications simples et pratiques",
  },
  {
    id: "banquier",
    label: "Banquier / Crédit",
    description: "Indicateurs financiers et risque crédit",
  },
  {
    id: "assureur",
    label: "Assureur",
    description: "Données techniques pour évaluation des sinistres",
  },
  {
    id: "promoteur",
    label: "Promoteur immobilier",
    description: "Analyse ROI et valorisation",
  },
];

interface IndicatorTooltipProps {
  title: string;
  simple: string;
  profiles: Record<UserProfile, { label: string; explanation: string }>;
  currentProfile: UserProfile;
  children?: React.ReactNode;
}

export default function IndicatorTooltip({
  title,
  simple,
  profiles,
  currentProfile,
  children,
}: IndicatorTooltipProps) {
  const [isOpen, setIsOpen] = useState(false);

  const profileData = profiles[currentProfile];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h4 className={styles.title}>{title}</h4>
        <button
          className={styles.helpButton}
          onMouseEnter={() => setIsOpen(true)}
          onMouseLeave={() => setIsOpen(false)}
          onClick={() => setIsOpen(!isOpen)}
          aria-label="Plus d'informations"
        >
          <span className={styles.helpIcon}>?</span>
        </button>
      </div>
      <p className={styles.simple}>{simple}</p>

      {isOpen && (
        <div className={styles.tooltip}>
          <div className={styles.tooltipHeader}>
            <strong>{profileData.label}</strong>
          </div>
          <p className={styles.tooltipText}>{profileData.explanation}</p>
        </div>
      )}

      {children}
    </div>
  );
}

interface ProfileSelectorProps {
  currentProfile: UserProfile;
  onProfileChange: (profile: UserProfile) => void;
}

export function ProfileSelector({
  currentProfile,
  onProfileChange,
}: ProfileSelectorProps) {
  return (
    <div className={styles.profileSelector}>
      <label className={styles.profileLabel}>Affichage :</label>
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
            {profile.label}
          </button>
        ))}
      </div>
    </div>
  );
}