"""
File de jobs de simulation (Sprint 2) — le endpoint POST /simulation/
{aleas_code} ne bloque jamais : il enregistre un job et le calcule en
arriere-plan (asyncio task + asyncio.to_thread pour le calcul CPU-borne),
le client interroge ensuite GET /simulation/jobs/{job_id} (polling).

Stockage en memoire uniquement (dict) : suffisant pour un usage de demo —
les jobs vivent ~30 min puis sont purges (TTL + borne haute). Pas de verrou :
toutes les operations sont synchrones sur la boucle asyncio unique du
processus (pas de threads partageant le dict), et un lock asyncio
module-level serait au contraire un piege si deux boucles coexistaient
(il se lierait a la premiere).
A noter dans la feuille de route : passer a Redis/une base si le volume
augmente ou si plusieurs workers tournent (les CZML sont des JSON purs,
donc trivialement serialisables).

Exigence §11 du plan : « le endpoint doit être asynchrone dès le départ
(job + polling), pas un appel synchrone bloquant » — c'est exactement ce
que fait ce module.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.services.simulation.dem import fetch_dem_for_bbox
from app.services.simulation.engine import build_czml_for_alea

logger = get_logger(__name__)

# Aleas dont la simulation consomme le relief reel (MNT RGE ALTI).
DEM_DRIVEN_ALEAS = {"inondation"}

MAX_JOBS = 12          # borne haute du store en memoire
TTL_SECONDS = 30 * 60  # 30 min — un job expire apres ce delai


@dataclass
class SimulationJob:
    id: str
    aleas_code: str
    status: str            # "queued" | "running" | "ready" | "error"
    created_at: float
    lat: float = 0.0
    lon: float = 0.0
    niveau: str | None = None
    source_lat: float | None = None   # source manuelle cliquée sur le globe
    source_lon: float | None = None
    intensite: float | None = None    # 0..1 (prime sur la bande D03)
    czml: dict | None = None
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


_JOBS: dict[str, SimulationJob] = {}


async def _run_job(job_id: str) -> None:
    """Calcule le CZML et met a jour le job.

    Le MNT RGE ALTI est recupere en async (appel reseau IGN, mis en cache
    par adresse — cf. dem.py) avant le calcul CPU-borne en thread ; en cas
    d'echec du MNT, le moteur retombe sur son modele procedural (fail-soft,
    jamais de job en erreur pour cette raison).
    """
    job = _JOBS[job_id]
    job.status = "running"
    try:
        # Le MNT est récupéré sur l'emprise de la SIMULATION : centré sur la
        # source manuelle si présente, sinon sur l'adresse (baignoire).
        dem_lat = job.source_lat if job.source_lat is not None else job.lat
        dem_lon = job.source_lon if job.source_lon is not None else job.lon
        dem = None
        if job.aleas_code in DEM_DRIVEN_ALEAS:
            dem = await fetch_dem_for_bbox(dem_lat, dem_lon)
            if dem is None:
                logger.warning(
                    "simulation %s (%s) — MNT RGE ALTI indisponible, repli procedural",
                    job_id, job.aleas_code,
                )
        czml = await asyncio.to_thread(
            build_czml_for_alea, job.aleas_code, job.lat, job.lon, job.niveau, dem,
            source_lat=job.source_lat, source_lon=job.source_lon,
            intensite=job.intensite,
        )
        job.czml = czml
        job.status = "ready"
        source_note = (
            f"source=({job.source_lat:.4f}, {job.source_lon:.4f})"
            if job.source_lat is not None
            else "source=adresse"
        )
        logger.info(
            "simulation %s (%s) prete — %d cellules CZML (MNT=%s, %s)",
            job_id, job.aleas_code, len(czml.get("packet", [])),
            "RGE ALTI" if dem is not None else "procedural",
            source_note,
        )
    except Exception as exc:  # noqa: BLE001 — le job capte toutes les erreurs
        job.status = "error"
        job.error = f"{type(exc).__name__}: {exc}"
        logger.warning("simulation %s (%s) en echec : %s", job_id, job.aleas_code, exc)


def submit_simulation(
    aleas_code: str,
    lat: float,
    lon: float,
    niveau: str | None,
    *,
    source_lat: float | None = None,
    source_lon: float | None = None,
    intensite: float | None = None,
) -> SimulationJob:
    """Enregistre un job et lance son calcul en arriere-plan. Retourne le
    job (status "queued") — a poller via get_job()."""
    job = SimulationJob(
        id=uuid.uuid4().hex[:12],
        aleas_code=aleas_code,
        status="queued",
        created_at=time.time(),
        lat=lat,
        lon=lon,
        niveau=niveau,
        source_lat=source_lat,
        source_lon=source_lon,
        intensite=intensite,
    )
    _JOBS[job.id] = job
    _prune_jobs()
    job.task = asyncio.create_task(_run_job(job.id))
    return job


def get_job(job_id: str) -> SimulationJob | None:
    job = _JOBS.get(job_id)
    if job is None:
        return None
    if job.status in ("ready", "error") and time.time() - job.created_at > TTL_SECONDS:
        _JOBS.pop(job_id, None)
        return None
    return job


def _prune_jobs() -> None:
    """Purge : jobs termines trop vieux, puis excedent de la borne haute
    (on garde les plus recents, jamais un job encore en cours)."""
    now = time.time()
    done_expired = [
        jid
        for jid, job in _JOBS.items()
        if job.status in ("ready", "error") and now - job.created_at > TTL_SECONDS
    ]
    for jid in done_expired:
        _JOBS.pop(jid, None)

    running = [jid for jid, job in _JOBS.items() if job.status not in ("ready", "error")]
    excess = len(_JOBS) - MAX_JOBS
    if excess > 0:
        for jid in sorted(_JOBS, key=lambda j: _JOBS[j].created_at):
            if excess <= 0:
                break
            if _JOBS[jid].status in ("ready", "error"):
                _JOBS.pop(jid, None)
                excess -= 1
