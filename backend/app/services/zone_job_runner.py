"""
zone_job_runner — in-process asyncio task runner backing the zone jobs table.

Caveat: this only works for a single backend process. If you run multiple
uvicorn workers, in-process tasks won't be visible across processes.
"""

from __future__ import annotations

import time

from app.agents.zone_insurer.graph import get_graph
from app.core.logging import get_logger
from app.db.database import get_session
from app.db.models import Job

logger = get_logger(__name__)


def _update_job(job_id: str, **fields) -> None:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            logger.warning("zone_job_runner -- job %s introuvable pour mise a jour", job_id)
            return
        for key, value in fields.items():
            setattr(job, key, value)


async def run_job(job_id: str, address: str, radius_m: float) -> None:
    t0 = time.perf_counter()
    _update_job(job_id, current_step="resolving_zone")

    def on_progress(processed: int, total: int) -> None:
        _update_job(job_id, current_step="collecting_buildings", processed_buildings=processed, total_buildings=total)

    try:
        graph = get_graph()
        final_state = await graph.ainvoke({
            "address": address,
            "radius_m": radius_m,
            "job_id": job_id,
            "started_at": t0,
            "on_progress": on_progress,
        })
        _update_job(
            job_id,
            status="done",
            current_step="done",
            result=final_state["report"],
            processed_buildings=final_state["report"]["nb_buildings"],
            total_buildings=final_state["report"]["nb_buildings"],
        )
        logger.info("zone_job_runner -- job %s termine en %.2fs", job_id, time.perf_counter() - t0)
    except Exception as exc:
        logger.exception("zone_job_runner -- job %s a echoue", job_id)
        _update_job(job_id, status="error", current_step="error", error=str(exc))
