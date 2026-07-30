import type { DomaineInfo, RecommandationInput } from "./types";

/**
 * Parse les lignes de recommandations saisies par l'utilisateur
 * en entrées structurées pour l'API.
 */
export function parserRecommandations(
  lignes: string[],
  domaines: Record<string, DomaineInfo> | null
): RecommandationInput[] {
  return lignes
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      const isKnownKey = domaines && domaines[line];
      if (isKnownKey) {
        return { cle: line };
      }
      return { mesure: line, zone: "", risques: [] };
    });
}

/**
 * Construit le texte d'affichage du contact d'une entreprise.
 */
export function formatContact(
  telephone?: string | null,
  email?: string | null
): { text: string; href?: string; isEmail?: boolean } {
  if (telephone && email) {
    return { text: `${telephone} · ${email}`, href: `mailto:${email}`, isEmail: true };
  }
  if (telephone) {
    return { text: telephone };
  }
  if (email) {
    return { text: email, href: `mailto:${email}`, isEmail: true };
  }
  return { text: "Contact non disponible" };
}

