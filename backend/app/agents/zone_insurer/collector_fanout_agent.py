"""
collector_fanout_agent — runs the per-building collector + scorer for every
candidate in the zone, in parallel, checked against the de-dup cache first.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.agents.collector_agent import collect as _collect_building
from app.agents.zone_insurer.state import ZoneState
from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import get_session
from app.db.models import BuildingCache
from app.scoring.risk_model import compute_risk_scores

logger = get_logger(__name__)


def _cache_ttl_hours() -> int:
    return settings.zone_cache_ttl_hours


def _max_concurrency() -> int:
    return settings.zone_max_concurrency


def cache_lookup(address_label: str | None) -> dict | None:
    if not address_label:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_cache_ttl_hours())
    with get_session() as session:
        row = session.execute(
            select(BuildingCache).where(BuildingCache.address_label == address_label)
        ).scalar_one_or_none()
        if row is None or row.fetched_at < cutoff:
            return None
        return {
            "address_label": row.address_label,
            "lat": row.lat,
            "lon": row.lon,
            "building_data": row.building_data,
            "risk_scores": row.risk_scores,
        }


def cache_store(address_label: str | None, lat: float, lon: float, building_data: dict, risk_scores: dict) -> None:
    if not address_label:
        return
    with get_session() as session:
        row = session.get(BuildingCache, address_label)
        if row is None:
            row = BuildingCache(address_label=address_label, lat=lat, lon=lon)
            session.add(row)
        row.lat, row.lon = lat, lon
        row.building_data = building_data
        row.risk_scores = risk_scores
        row.fetched_at = datetime.now(timezone.utc)


async def process_one(candidate: dict, semaphore: asyncio.Semaphore) -> dict[str, Any]:
    address_label = candidate.get("address_label")
    lat, lon = candidate["lat"], candidate["lon"]

    cached = cache_lookup(address_label)
    if cached is not None:
        return {
            "address_label": cached["address_label"],
            "lat": cached["lat"],
            "lon": cached["lon"],
            "building_data": cached["building_data"],
            "risk_scores": cached["risk_scores"],
            "source": "cache",
            "error": None,
        }

    query = address_label if address_label else f"{lat},{lon}"
    async with semaphore:
        try:
            # Le rapport assurance veut le maximum de signal disponible :
            # on force ces sources a True ici (independamment des reglages
            # globaux par defaut utilises par le diagnostic mono-batiment),
            # chaque source restant individuellement tolerante a l'echec
            # (jeton/fichier manquant -> None + erreur consignee, jamais de
            # plantage - voir collector_agent.py).
            building_data = await _collect_building(
                query,
                enable_dvf=True,
                enable_georisques_v2=True,
                enable_wfs=True,
                enable_drias=True,
            )
            risk_scores = compute_risk_scores(building_data)
            resolved_label = (building_data.get("adresse") or {}).get("label") or address_label
            cache_store(resolved_label, lat, lon, building_data, risk_scores)
            return {
                "address_label": resolved_label,
                "lat": lat,
                "lon": lon,
                "building_data": building_data,
                "risk_scores": risk_scores,
                "source": "live",
                "error": None,
            }
        except Exception as exc:
            logger.warning("collector_fanout_agent -- echec pour %r: %s", query, exc)
            return {
                "address_label": address_label,
                "lat": lat,
                "lon": lon,
                "building_data": None,
                "risk_scores": None,
                "source": "live",
                "error": str(exc),
            }


async def run(state: ZoneState) -> dict:
    candidates = state["candidates"]
    semaphore = asyncio.Semaphore(_max_concurrency())
    on_progress = state.get("on_progress")

    results: list[dict] = []
    tasks = [asyncio.create_task(process_one(c, semaphore)) for c in candidates]
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        if on_progress:
            on_progress(len(results), len(candidates))

    logger.info(
        "collector_fanout_agent -- %d/%d batiments traites (%d erreurs)",
        len(results), len(candidates), sum(1 for r in results if r["error"]),
    )
    return {"building_results": results}
