// =============================================================================
//   TYPHOON — /zone : cache des diagnostics (façon « historique ChatGPT »).
//   Chaque diagnostic réussi (rapport Géorisques complet + rapport narratif
//   Mistral) est stocké en localStorage, indexé par adresse normalisée. Un
//   re-diagnostic de la même adresse (via « Récent » ou le champ) est servi
//   instantanément depuis le cache — aucun appel réseau. Un TTL garde les
//   données fraîches (arrêtés CatNat, zonages évoluent).
// =============================================================================

import type { RisqueReport, RapportNarratif } from './config';

export interface CachedDiagnostic {
  /** Adresse normalisée (clé de recherche, minuscules). */
  key: string;
  report: RisqueReport;
  /** Rapport narratif Mistral si déjà généré (coûteux → on le conserve). */
  rapport: RapportNarratif | null;
  createdAt: number;
  rapportAt: number | null;
}

const STORAGE_KEY = 'typhoon.zone.cache';
/** Durée de validité d'un diagnostic en cache (ms) — 7 jours. */
const TTL_MS = 7 * 24 * 60 * 60 * 1000;
/** Nombre maximum d'entrées conservées (localStorage ≈ 5 Mo). */
const MAX_ENTRIES = 30;

function normKey(address: string): string {
  return address
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

export function loadCache(): CachedDiagnostic[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (c): c is CachedDiagnostic =>
        !!c &&
        typeof c.key === 'string' &&
        !!c.report &&
        typeof c.report.adresse_normalisee === 'string'
    );
  } catch {
    return [];
  }
}

function saveCache(entries: CachedDiagnostic[]): void {
  try {
    // Trie par fraîcheur, garde les MAX_ENTRIES plus récentes.
    const sorted = [...entries].sort((a, b) => b.createdAt - a.createdAt).slice(0, MAX_ENTRIES);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sorted));
  } catch {
    /* quota plein → on retente avec la moitié des entrées */
    try {
      const half = [...entries]
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, Math.max(1, Math.floor(MAX_ENTRIES / 2)));
      localStorage.setItem(STORAGE_KEY, JSON.stringify(half));
    } catch {
      /* stockage indisponible — ignorer */
    }
  }
}

/** Retourne le diagnostic caché s'il est encore frais (TTL), sinon null. */
export function getCachedDiagnostic(address: string): CachedDiagnostic | null {
  const key = normKey(address);
  if (!key) return null;
  const entry = loadCache().find((c) => c.key === key);
  if (!entry) return null;
  if (Date.now() - entry.createdAt > TTL_MS) return null; // expiré → refetch
  return entry;
}

/** Stocke (ou met à jour) un diagnostic complet. */
export function putCachedDiagnostic(
  report: RisqueReport,
  rapport: RapportNarratif | null = null
): void {
  const key = normKey(report.adresse_normalisee || report.adresse_saisie);
  if (!key) return;
  const entries = loadCache();
  const without = entries.filter((c) => c.key !== key);
  const existing = entries.find((c) => c.key === key);
  saveCache([
    {
      key,
      report,
      rapport: rapport ?? existing?.rapport ?? null,
      createdAt: Date.now(),
      rapportAt: rapport ? Date.now() : (existing?.rapportAt ?? null),
    },
    ...without,
  ]);
}

/** Rattache un rapport narratif Mistral à un diagnostic déjà caché. */
export function putCachedRapport(report: RisqueReport, rapport: RapportNarratif): void {
  const key = normKey(report.adresse_normalisee || report.adresse_saisie);
  if (!key) return;
  const entries = loadCache();
  const idx = entries.findIndex((c) => c.key === key);
  if (idx === -1) {
    putCachedDiagnostic(report, rapport);
    return;
  }
  const next = [...entries];
  next[idx] = { ...next[idx], rapport, rapportAt: Date.now(), createdAt: Date.now() };
  saveCache(next);
}

/** Supprime l'entrée correspondant à une adresse (suppression de l'historique). */
export function removeCachedDiagnostic(address: string): void {
  const key = normKey(address);
  if (!key) return;
  saveCache(loadCache().filter((c) => c.key !== key));
}
