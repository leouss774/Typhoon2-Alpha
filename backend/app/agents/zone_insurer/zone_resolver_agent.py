"""
zone_resolver_agent — first node of the zone StateGraph.

Turns {address, radius_m} into a list of candidate points to assess.
Tries BDNB bulk bbox query first; falls back to grid sampling.
"""

from __future__ import annotations

import httpx

from app.agents.zone_insurer.state import ZoneState
from app.connectors import bdnb_bulk
from app.connectors.geocoding import geocode_address
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def run(state: ZoneState) -> dict:
    address = state["address"]
    radius_m = state["radius_m"]

    async with httpx.AsyncClient(timeout=15.0) as client:
        geocode = await geocode_address(client, address)
        center_lat, center_lon = geocode.lat, geocode.lon

        candidates: list[dict] = []
        enumeration_method = "bdnb_bulk"
        try:
            bulk = await bdnb_bulk.fetch_buildings_in_radius(
                client, center_lat, center_lon, radius_m,
                settings.zone_max_buildings_per_job
            )
            if bulk:
                candidates = [
                    {"address_label": c.address_label, "lat": c.lat, "lon": c.lon}
                    for c in bulk
                ]
        except Exception as exc:
            logger.warning("BDNB bulk enumeration failed (%s), falling back to grid sampling", exc)

        if not candidates:
            enumeration_method = "grid_fallback"
            grid = bdnb_bulk.grid_fallback_points(
                center_lat, center_lon, radius_m,
                spacing_m=max(50.0, radius_m / 6),
                max_points=settings.zone_max_buildings_per_job,
            )
            candidates = [
                {"address_label": None, "lat": g.lat, "lon": g.lon} for g in grid
            ]

    logger.info(
        "zone_resolver_agent -- %d candidate(s) via %s (center=%.5f,%.5f radius=%sm)",
        len(candidates), enumeration_method, center_lat, center_lon, radius_m,
    )

    return {
        "center_lat": center_lat,
        "center_lon": center_lon,
        "candidates": candidates,
        "enumeration_method": enumeration_method,
    }
