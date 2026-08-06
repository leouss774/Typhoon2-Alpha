// =============================================================================
//   Déclarations TypeScript pour le moteur 3D porté (scene-engine.js).
//   Le fichier .js est porté tel quel depuis le front natif ; cette .d.ts
//   rend l'import typé sans passer par allowJs.
// =============================================================================

export function initScene(): void;
export function disposeScene(): void;

export interface MatchArtisansParams {
  apiBase: string;
  adresse: string;
  zoneName: string;
  /** Données de zone : { alea_principal?, recommandations[] } */
  data: Record<string, unknown>;
  container: HTMLElement | null;
  button?: HTMLElement | null;
  limite?: number;
}

/** Recherche d'artisans autonome (POST /artisans/match) — utilisé par la page
 *  /artisans qui n'a pas de moteur 3D monté. Rend les résultats dans
 *  `container` (groupes par métier + cartes entreprises + notes). */
export function matchArtisans(params: MatchArtisansParams): Promise<void>;
