// =============================================================================
//   TYPHOON — /zone : client du pipeline de simulation (Sprint 2).
//   Dialogue avec le backend (POST /diagnostic/adresse/simulation/{aleas_code}
//   → job async → GET /jobs/{id} en polling → czml_url).
//   L'animation elle-meme est jouee par Cesium (CzmlDataSource + clock), pas
//   ici : ce module ne fait que lancer/controler le job cote API.
// =============================================================================

import { API } from '../zone/config';

/** Aleas disposant d'une simulation (miroir de SIMULABLE_ALEAS backend). */
export const SIMULABLE_ALEAS: Record<
  string,
  { libelle: string; icon: string; hint: string }
> = {
  inondation: {
    libelle: 'Inondation',
    icon: 'flood',
    hint: 'Montée d’eau contrainte par le relief réel (RGE ALTI IGN) — les zones basses s’inondent en premier',
  },
  feu_foret: {
    libelle: 'Feu de forêt',
    icon: 'local_fire_department',
    hint: 'Front de flammes — vents dominants d’ouest',
  },
  mouvement_terrain: {
    libelle: 'Mouvement de terrain',
    icon: 'landslide',
    hint: 'Glissement d’une masse de sol le long de la pente',
  },
  avalanche: {
    libelle: 'Avalanche',
    icon: 'terrain',
    hint: 'Coulée gravitaire depuis le versant amont',
  },
  vent_cyclonique: {
    libelle: 'Vent cyclonique',
    icon: 'cyclone',
    hint: 'Champ de vent stylisé en spirale',
  },
};

export type SimulationStatus = 'queued' | 'running' | 'ready' | 'error';

export interface SimulationJobStatus {
  job_id: string;
  status: SimulationStatus;
  aleas_code: string;
  czml_url?: string;
  error?: string;
}

export interface SimulationOpts {
  lat: number;
  lon: number;
  codeInsee?: string;
  niveau?: string | null;
  /** Source manuelle cliquée sur le globe (inondation) — le raster est
   *  recentré sur ce point et l'eau part de là (priority flood). */
  sourceLat?: number;
  sourceLon?: number;
  /** Intensité 0..1 de la source manuelle (prime sur la bande D03). */
  intensite?: number;
}

/** POST → enregistre le job (202) et renvoie son statut initial. */
export async function startSimulation(
  aleasCode: string,
  opts: SimulationOpts
): Promise<SimulationJobStatus> {
  const resp = await fetch(`${API}/diagnostic/adresse/simulation/${aleasCode}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      lat: opts.lat,
      lon: opts.lon,
      code_insee: opts.codeInsee ?? null,
      niveau: opts.niveau ?? null,
      source_lat: opts.sourceLat ?? null,
      source_lon: opts.sourceLon ?? null,
      intensite: opts.intensite ?? null,
    }),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: { detail?: string; error?: string } };
      detail = body.detail?.detail || body.detail?.error || detail;
    } catch {
      /* corps non JSON */
    }
    throw new Error(detail);
  }
  return (await resp.json()) as SimulationJobStatus;
}

/** GET → statut du job (polling). */
export async function fetchSimulationStatus(jobId: string): Promise<SimulationJobStatus> {
  const resp = await fetch(`${API}/diagnostic/adresse/simulation/jobs/${jobId}`);
  if (!resp.ok) throw new Error(`Statut de simulation HTTP ${resp.status}`);
  return (await resp.json()) as SimulationJobStatus;
}

/**
 * Lance une simulation et pole jusqu'au terme (ready / error).
 * Abandonnable via le signal — le frontend coupe le polling en quittant
 * l'onglet ou en lançant une autre simulation.
 */
export async function runSimulationToEnd(
  aleasCode: string,
  opts: SimulationOpts,
  signal?: AbortSignal,
  onProgress?: (status: SimulationStatus) => void
): Promise<SimulationJobStatus> {
  const job = await startSimulation(aleasCode, opts);
  onProgress?.(job.status);

  let status = job;
  const deadline = Date.now() + 30_000;
  while ((status.status === 'queued' || status.status === 'running') && Date.now() < deadline) {
    if (signal?.aborted) throw new DOMException('aborted', 'AbortError');
    await new Promise((r) => setTimeout(r, 500));
    if (signal?.aborted) throw new DOMException('aborted', 'AbortError');
    status = await fetchSimulationStatus(job.job_id);
    onProgress?.(status.status);
  }
  /* Deadline dépassé sans ready/error → ne jamais laisser l'UI coincée en
     « running » : on force un statut d'erreur explicite. */
  if (status.status === 'queued' || status.status === 'running') {
    return {
      ...status,
      status: 'error' as const,
      error: 'Délai de 30 s dépassé — simulation abandonnée par le client.',
    };
  }
  return status;
}
