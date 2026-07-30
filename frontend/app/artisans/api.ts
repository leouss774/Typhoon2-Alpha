import type { ArtisanMatchingResponse, DomaineInfo, RecommandationInput } from "./types";

/**
 * Lance une recherche intelligente d'artisans RGE et non-RGE.
 * Utilise l'endpoint /search qui géocode automatiquement l'adresse
 * pour un scoring par distance réelle (Haversine).
 *
 * Utilise le rewrite proxy de next.config.ts (/api/* → localhost:8001/api/*).
 */
export async function rechercherArtisans(
  adresse: string,
  recommandations: RecommandationInput[],
  limite = 10,
  codePostal?: string
): Promise<ArtisanMatchingResponse> {
  const body: Record<string, any> = {
    adresse,
    recommandations,
    limite_entreprises: limite,
  };
  // Envoyer le code postal si disponible (évite l'échec d'extraction côté backend)
  if (codePostal) {
    body.code_postal = codePostal;
  }

  const resp = await fetch("/api/v1/artisans/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status} — Vérifiez que le backend est lancé` }));
    throw new Error(err.detail || `Erreur ${resp.status}`);
  }

  return resp.json();
}

/**
 * Récupère la liste des domaines RGE et non-RGE disponibles.
 */
export async function getDomaines(): Promise<Record<string, DomaineInfo>> {
  const resp = await fetch("/api/v1/artisans/domaines");
  if (!resp.ok) return {};
  const data = await resp.json();
  return data.domaines as Record<string, DomaineInfo>;
}
