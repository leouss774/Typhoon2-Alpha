// =============================================================================
//   TYPHOON — /usine : catalogue des recommandations d'adaptation (partagé)
//   Utilisé par l'étape 5 « Recommandations » (plan d'adaptation) et par la
//   synthèse économique du rapport (enveloppe travaux, gain de résilience
//   estimé). Montants indicatifs en euros (hors études détaillées) — ordres
//   de grandeur issus du risk engine : type de zone × niveau de risque.
// =============================================================================

export type Recommendation = {
  travaux: string;
  cout_estime: string;
  gain_resilience: number;
  priorite: 'urgent' | 'recommande' | 'anticipation';
};

export const CATALOGUE: Record<string, Record<string, Recommendation[]>> = {
  production: {
    eleve: [
      { travaux: 'Confinement et sécurisation des lignes critiques (bornes de coupure, réarmement automatique)', cout_estime: '25 000 – 60 000 €', gain_resilience: 28, priorite: 'urgent' },
      { travaux: 'Redondance des équipements vitaux (groupe froid, compresseur) et contrats de maintenance préventive', cout_estime: '40 000 – 120 000 €', gain_resilience: 24, priorite: 'recommande' },
      { travaux: 'Système de surveillance et d\'alerte (capteurs température, vibrations, fuite)', cout_estime: '8 000 – 20 000 €', gain_resilience: 18, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Révision et fiabilisation des automates et commandes électriques', cout_estime: '12 000 – 35 000 €', gain_resilience: 16, priorite: 'recommande' },
      { travaux: 'Plan de continuité d\'activité (PCA) avec procédures de repli des lignes critiques', cout_estime: '3 000 – 10 000 €', gain_resilience: 12, priorite: 'anticipation' },
    ],
    faible: [
      { travaux: 'Suivi annuel des équipements et mise à jour des consignes', cout_estime: '2 000 – 6 000 €', gain_resilience: 6, priorite: 'anticipation' },
    ],
  },
  stockage: {
    eleve: [
      { travaux: 'Renforcement du rackage et des allées de manutention (protège-poteaux, fixations antisismiques)', cout_estime: '15 000 – 45 000 €', gain_resilience: 22, priorite: 'urgent' },
      { travaux: 'Murs et portes coupe-feu entre zones de stockage et ateliers', cout_estime: '20 000 – 70 000 €', gain_resilience: 20, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Surélévation des stocks hors sol et séparation des matières incompatibles', cout_estime: '5 000 – 18 000 €', gain_resilience: 14, priorite: 'recommande' },
    ],
    faible: [
      { travaux: 'Inventaire et optimisation des flux de stockage', cout_estime: '1 000 – 4 000 €', gain_resilience: 5, priorite: 'anticipation' },
    ],
  },
  cuves: {
    eleve: [
      { travaux: 'Mise en place de cuvettes de rétention et de vannes de sécurité automatiques', cout_estime: '30 000 – 90 000 €', gain_resilience: 30, priorite: 'urgent' },
      { travaux: 'Capteurs de niveau, pression et détection de fuite avec télésurveillance', cout_estime: '10 000 – 25 000 €', gain_resilience: 22, priorite: 'urgent' },
      { travaux: 'Ancrage et renforcement des supports de cuves et réservoirs', cout_estime: '12 000 – 40 000 €', gain_resilience: 16, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Plan d\'intervention d\'urgence avec exercices réguliers', cout_estime: '2 000 – 8 000 €', gain_resilience: 12, priorite: 'recommande' },
    ],
    faible: [
      { travaux: 'Inspection et maintenance périodique des cuves', cout_estime: '1 500 – 5 000 €', gain_resilience: 6, priorite: 'anticipation' },
    ],
  },
  bureaux: {
    eleve: [
      { travaux: 'Protection des serveurs et données (onduleurs, sauvegardes hors site)', cout_estime: '6 000 – 20 000 €', gain_resilience: 18, priorite: 'urgent' },
      { travaux: 'Étanchéité de la toiture et protection contre les infiltrations', cout_estime: '8 000 – 30 000 €', gain_resilience: 12, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Éclairage de secours et locaux de repli', cout_estime: '2 000 – 6 000 €', gain_resilience: 8, priorite: 'recommande' },
    ],
    faible: [
      { travaux: 'Mise à jour du plan de sécurité', cout_estime: '500 – 2 000 €', gain_resilience: 4, priorite: 'anticipation' },
    ],
  },
  expedition: {
    eleve: [
      { travaux: 'Surélévation des quais et protection des convoyeurs contre les intempéries', cout_estime: '18 000 – 50 000 €', gain_resilience: 20, priorite: 'urgent' },
      { travaux: 'Système de gestion des expéditions déporté (repli informatique)', cout_estime: '5 000 – 15 000 €', gain_resilience: 12, priorite: 'recommande' },
    ],
    modere: [
      { travaux: 'Procédures de manutention renforcées et formation', cout_estime: '2 000 – 6 000 €', gain_resilience: 8, priorite: 'recommande' },
    ],
    faible: [
      { travaux: 'Organisation des flux d\'expédition', cout_estime: '1 000 – 3 000 €', gain_resilience: 4, priorite: 'anticipation' },
    ],
  },
};

export const GLOBAL_ACTIONS: Recommendation[] = [
  { travaux: 'Diagnostic détaillé du site par un bureau d\'ingénierie (structure, process, sécurité incendie)', cout_estime: '5 000 – 15 000 €', gain_resilience: 20, priorite: 'recommande' },
  { travaux: 'Mise à niveau de la conformité ICPE / réglementation environnementale', cout_estime: '10 000 – 40 000 €', gain_resilience: 15, priorite: 'recommande' },
  { travaux: 'Souscription d\'une couverture d\'assurance adaptée aux risques identifiés', cout_estime: 'variable', gain_resilience: 10, priorite: 'anticipation' },
];

/** Parse « 25 000 – 60 000 € » → [25000, 60000] (ou [valeur, valeur]). */
export function parseCostRange(cost: string): [number, number] {
  const nums = (cost || '').match(/[\d\s]+/g);
  if (!nums) return [0, 0];
  const vals = nums.map((n) => Number(n.replace(/\s/g, '')) || 0);
  return vals.length === 1 ? [vals[0], vals[0]] : [vals[0], vals[1] || vals[0]];
}
