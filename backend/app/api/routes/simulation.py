"""
Routes de simulation d'aleas — pipeline CZML (Sprint 2 du plan Cesium).

  POST /diagnostic/adresse/simulation/{aleas_code}   → 202 {job_id, status}
  GET  /diagnostic/adresse/simulation/jobs/{job_id}  → statut (+ czml_url si prete)
  GET  /diagnostic/adresse/simulation/jobs/{job_id}/czml → document CZML (JSON)

Flux (jamais bloquant, cf. §11 du plan) :
  POST enregistre un job et lance le calcul en arriere-plan, repond 202.
  Le client pole le GET /jobs/{job_id} ; quand status == "ready", il charge
  Cesium.CzmlDataSource.load(czml_url) — les controles natifs de Cesium
  (play/pause/vitesse/timeline) animent la simulation.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.services.simulation.engine import SIMULABLE_ALEAS
from app.services.simulation.jobs import get_job, submit_simulation

logger = get_logger(__name__)
router = APIRouter()


class SimulationRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude WGS84 du bien")
    lon: float = Field(..., ge=-180, le=180, description="Longitude WGS84 du bien")
    code_insee: str | None = Field(
        default=None, description="Code INSEE de la commune (trace seulement)"
    )
    niveau: str | None = Field(
        default=None,
        description="Bande D03 de l'alea (tres_faible..critique) — echelle la simulation",
    )
    source_lat: float | None = Field(
        default=None, ge=-90, le=90,
        description="Source manuelle (inondation) : latitude du point clique sur le globe",
    )
    source_lon: float | None = Field(
        default=None, ge=-180, le=180,
        description="Source manuelle (inondation) : longitude du point clique sur le globe",
    )
    intensite: float | None = Field(
        default=None, ge=0, le=1,
        description="Intensite 0..1 de la source manuelle (prime sur la bande D03)",
    )


def _job_payload(job_id: str, status: str, aleas_code: str) -> dict:
    return {
        "job_id": job_id,
        "status": status,
        "aleas_code": aleas_code,
        "poll_url": f"/diagnostic/adresse/simulation/jobs/{job_id}",
    }


@router.post("/diagnostic/adresse/simulation/{aleas_code}", status_code=202)
async def start_simulation(aleas_code: str, payload: SimulationRequest) -> dict:
    """Lance (ou met en file) une simulation pour un alea, repond 202 + job_id.

    Le calcul tourne en arriere-plan ; le client poll GET /jobs/{job_id}.
    """
    if aleas_code not in SIMULABLE_ALEAS:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "alea_non_simulable",
                "detail": (
                    f"«{aleas_code}» n'a pas de simulation — simulables : "
                    f"{', '.join(sorted(SIMULABLE_ALEAS))}"
                ),
            },
        )

    if (payload.source_lat is None) != (payload.source_lon is None):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "source_incomplete",
                "detail": "source_lat et source_lon doivent être fournis ensemble.",
            },
        )

    job = submit_simulation(
        aleas_code,
        payload.lat,
        payload.lon,
        payload.niveau,
        source_lat=payload.source_lat,
        source_lon=payload.source_lon,
        intensite=payload.intensite,
    )
    logger.info(
        "POST simulation %s job=%s (lat=%.4f lon=%.4f niveau=%s)",
        aleas_code, job.id, payload.lat, payload.lon, payload.niveau,
    )
    return _job_payload(job.id, job.status, aleas_code)


@router.get("/diagnostic/adresse/simulation/jobs/{job_id}")
async def simulation_status(job_id: str) -> dict:
    """Statut du job. Quand ready, fournit czml_url (chargeable par
    Cesium.CzmlDataSource). L'erreur est renvoyee inline (pas de 500)."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_inconnu", "detail": f"Aucun job de simulation «{job_id}»."},
        )

    body = _job_payload(job.id, job.status, job.aleas_code)
    if job.status == "ready":
        body["czml_url"] = f"/diagnostic/adresse/simulation/jobs/{job_id}/czml"
    if job.status == "error":
        body["error"] = job.error
    return body


@router.get("/diagnostic/adresse/simulation/jobs/{job_id}/czml")
async def simulation_czml(job_id: str) -> dict:
    """Le document CZML termine (JSON brut, tel quel pour CzmlDataSource)."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "job_inconnu", "detail": str(job_id)})
    if job.status != "ready" or job.czml is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_pas_pret",
                "detail": f"Simulation {job_id} en statut {job.status} — attendez que le polling passe à ready.",
            },
        )
    return job.czml
