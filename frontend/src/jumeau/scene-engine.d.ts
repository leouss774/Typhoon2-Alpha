// =============================================================================
//   Déclarations TypeScript pour le moteur 3D porté (scene-engine.js).
//   Le fichier .js est porté tel quel depuis le front natif ; cette .d.ts
//   rend l'import typé sans passer par allowJs.
// =============================================================================

export function initScene(): void;
export function disposeScene(): void;
export function loadFromAddress(adresse: string): Promise<unknown>;

export interface MatchArtisansInput {
  apiBase: string;
  adresse: string;
  zoneName: string;
  data: {
    alea_principal?: string;
    recommandations?: Array<{ mesure?: string; travaux?: string }>;
  };
  container?: HTMLDivElement | null;
  button?: HTMLButtonElement | null;
  limite?: number;
}

export function matchArtisans(input: MatchArtisansInput): Promise<void>;
