"""
Routes for the zone-insurer workflow.

POST /zone/jobs       — (legacy) submit with address+radius
GET  /zone/jobs/{id}  — poll job status
POST /zone/assess     — NEW: assess zone by mode (single/multi) + points/polygon
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.db.database import get_session
from app.db.models import Job
from app.schemas.zone_insurer import (
    JobAccepted,
    JobStatusResponse,
    ZoneAssessRequest,
    ZoneJobRequest,
    ZoneReport,
)
from app.services.zone_assessor import assess_zone
from app.services.zone_job_runner import run_job

logger = get_logger(__name__)
router = APIRouter(prefix="/zone", tags=["zone-insurer"])


@router.post("/jobs", response_model=JobAccepted)
async def submit_zone_job(payload: ZoneJobRequest) -> JobAccepted:
    with get_session() as session:
        job = Job(address=payload.address, radius_m=payload.radius_m, status="processing", current_step="queued")
        session.add(job)
        session.flush()
        job_id = job.id

    asyncio.create_task(run_job(job_id, payload.address, payload.radius_m))

    logger.info("submit_zone_job -- job %s cree pour %r (rayon=%sm)", job_id, payload.address, payload.radius_m)
    return JobAccepted(job_id=job_id, status="processing")


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_zone_job(job_id: str) -> JobStatusResponse:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job introuvable")
        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            current_step=job.current_step,
            total_buildings=job.total_buildings,
            processed_buildings=job.processed_buildings,
            result=job.result,
            error=job.error,
        )


@router.post("/assess", response_model=ZoneReport)
async def assess_zone_route(payload: ZoneAssessRequest) -> ZoneReport:
    """
    Évalue les risques climatiques sur une zone définie par mode + points/polygone.

    - mode="single" : évalue un seul bâtiment (par adresse ou point cliqué)
    - mode="multi"  : évalue tous les bâtiments dans un polygone ou ensemble de points
    """
    logger.info(
        "POST /zone/assess -- mode=%s, points=%d, polygon=%d, address=%r",
        payload.mode,
        len(payload.points),
        len(payload.polygon),
        payload.address,
    )
    try:
        report = await assess_zone(
            mode=payload.mode,
            points=[p.model_dump() for p in payload.points],
            polygon=[p.model_dump() for p in payload.polygon],
            address=payload.address,
        )
        return ZoneReport(**report)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("POST /zone/assess -- echec")
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")
