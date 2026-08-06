/* =========================================================================
   Client API du volet économique.

   Pipeline : POST /diagnostic/fast (collecte + scores rapides)
            → POST /diagnostic/recommandations (recommandations RAG sourcées)
            → POST /diagnostic/retour-investissement (contrat économique)

   Les routes /diagnostic/* sont proxifiées par next.config.ts vers le
   backend (localhost:8765), comme /api/* pour les artisans.

   Aucun repli de démonstration : si le backend est injoignable, l'erreur
   remonte à l'interface — aucun montant simulé ne peut être affiché.
   ========================================================================= */

import type {
  DiagnosticFastResponse,
  EconomieContract,
  ResultatEconomie,
  ResumeDiagnostic,
} from "./types";

const TIMEOUT_MS = 120_000;

async function postJson<T>(path: string, body: unknown, timeoutMs = TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store",
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    return (await resp.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/** Étape 1 : collecte + scoring rapide (sans RAG) → contrat + _resume. */
async function runDiagnosticFast(adresse: string): Promise<DiagnosticFastResponse> {
  return postJson<DiagnosticFastResponse>("/diagnostic/fast", {
    adresse,
    copernicus: false,
  });
}

/** Étape 2 : recommandations RAG sourcées (reutilise la collecte de l'étape 1).
 *  Optionnelle : si le RAG échoue (pas de clé Mistral, backend injoignable),
 *  on retourne null et le pipeline continue avec les risk_scores de l'étape 1. */
async function runRecommandations(
  resume: ResumeDiagnostic
): Promise<Record<string, unknown> | null> {
  try {
    return await postJson<Record<string, unknown>>("/diagnostic/recommandations", {
      building_data: resume.building_data,
      risk_scores: resume.risk_scores,
      formulaire: resume.formulaire ?? null,
    }, 300_000);
  } catch (err) {
    console.warn("[economie] Étape recommandations ignorée :", err);
    return null;
  }
}

/** Étape 3 : calcul économique pur (déterministe, sans LLM). */
async function runRetourInvestissement(
  buildingData: Record<string, unknown>,
  riskScores: Record<string, unknown>,
  surfaceM2?: number | null
): Promise<EconomieContract> {
  return postJson<EconomieContract>("/diagnostic/retour-investissement", {
    building_data: buildingData,
    risk_scores: riskScores,
    surface_m2: surfaceM2 ?? null,
  });
}

/** Surface au sol : géométrie du jumeau (emprise) sinon rectangle englobant. */
function surfaceDepuisContrat(dt: DiagnosticFastResponse): number | null {
  const g = dt.geometry;
  if (!g) return null;
  if (typeof g.surface_emprise_m2 === "number" && g.surface_emprise_m2 > 0) {
    return g.surface_emprise_m2;
  }
  if (typeof g.largeur_m === "number" && typeof g.longueur_m === "number") {
    return g.largeur_m * g.longueur_m;
  }
  return null;
}

/**
 * Mapping inverse : zones du contrat (après mapping.py) → zones originales.
 * Le backend a regroupé murs_nord/sud/est/ouest → "facade", il faut répartir.
 */
const RECO_TO_ZONES: Record<string, string[]> = {
  fondations: ["fondations"],
  toiture: ["toiture"],
  sous_sol: ["sous_sol"],
  facade: ["murs_nord", "murs_sud", "murs_est", "murs_ouest"],
};

/**
 * Fusionne les recommandations du contrat (étape 2) dans les risk_scores
 * de l'étape 1 (qui portent les composantes F/V internes `_f_score`/`_v_score`
 * nécessaires au niveau A).
 */
function enrichirRiskScores(
  resume: ResumeDiagnostic,
  contratRecos: Record<string, unknown>
): Record<string, unknown> {
  const zones = resume.risk_scores.zones || {};
  const zonesContrat = (contratRecos.zones as Record<string, any>) || {};
  const fusion: Record<string, any> = {};

  // Initialiser avec les zones originales
  for (const [name, zone] of Object.entries(zones)) {
    fusion[name] = { ...zone };
  }

  // Répartir les recommandations du contrat vers les zones originales
  for (const [recoZone, recoData] of Object.entries(zonesContrat)) {
    const zonesCibles = RECO_TO_ZONES[recoZone] || [recoZone];
    for (const zoneName of zonesCibles) {
      if (fusion[zoneName]) {
        fusion[zoneName].recommandations = recoData.recommandations ?? fusion[zoneName].recommandations ?? [];
      }
    }
  }

  return {
    ...resume.risk_scores,
    zones: fusion,
  };
}

/**
 * Lance le pipeline économique complet pour une adresse.
 * En cas d'échec (backend injoignable, adresse introuvable, erreur API)…
 * l'exception est remontée à l'interface : pas de chiffres de substitution.
 */
export async function runEconomiePipeline(
  adresse: string
): Promise<ResultatEconomie> {
  const fast = await runDiagnosticFast(adresse.trim());
  const resume = fast._resume;
  if (!resume) {
    throw new Error("Contrat rapide sans bloc _resume (pipeline API modifié ?)");
  }

  const contratRecos = await runRecommandations(resume);
  const riskScores = contratRecos
    ? enrichirRiskScores(resume, contratRecos)
    : resume.risk_scores;
  const surfaceM2 = surfaceDepuisContrat(fast);

  const contract = await runRetourInvestissement(
    resume.building_data,
    riskScores,
    surfaceM2
  );

  return {
    contract,
    adresse: fast.adresse || adresse.trim(),
    surface_m2: surfaceM2,
  };
}
