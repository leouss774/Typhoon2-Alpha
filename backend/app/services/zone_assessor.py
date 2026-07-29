"""
zone_assessor — handles the new POST /zone/assess endpoint.

Takes a mode ("single" or "multi") plus either a single lat/lng point or a
polygon (array of vertices). Enumerates buildings in the area, runs the
collector_fanout -> aggregator -> report pipeline, and returns the ZoneReport.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

import httpx

from app.agents.collector_agent import collect as _collect_building
from app.agents.zone_insurer.aggregator_agent import run as run_aggregator
from app.agents.zone_insurer.collector_fanout_agent import process_one
from app.agents.zone_insurer.report_agent import run as run_report
from app.connectors import bdnb_bulk
from app.core.config import settings
from app.core.logging import get_logger
from app.scoring.risk_model import compute_risk_scores

logger = get_logger(__name__)


def _polygon_centroid(polygon: list[dict[str, float]]) -> tuple[float, float]:
    """Compute the centroid of a polygon from its vertex list."""
    lat_sum = sum(p["lat"] for p in polygon)
    lon_sum = sum(p["lon"] for p in polygon)
    n = len(polygon)
    return lat_sum / n, lon_sum / n


def _polygon_bbox(polygon: list[dict[str, float]]) -> tuple[float, float, float, float]:
    """Return (lon_min, lat_min, lon_max, lat_max) for a polygon's bounding box."""
    lats = [p["lat"] for p in polygon]
    lons = [p["lon"] for p in polygon]
    return min(lons), min(lats), max(lons), max(lats)


def _bbox_diameter_km(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> float:
    """Approximate diameter of a bbox in km."""
    center_lat = (lat_min + lat_max) / 2
    dlat_km = (lat_max - lat_min) * 111.32
    dlon_km = (lon_max - lon_min) * 111.32 * math.cos(math.radians(center_lat))
    return math.hypot(dlat_km, dlon_km)


async def assess_zone(
    mode: str,
    points: list[dict[str, float]] | None = None,
    polygon: list[dict[str, float]] | None = None,
    address: str | None = None,
) -> dict[str, Any]:
    """
    Assess risk for a zone defined by mode + points/polygon/address.

    Returns the same ZoneReport structure produced by the existing pipeline.
    """
    t0 = time.perf_counter()
    candidates: list[dict[str, Any]] = []
    enumeration_method = "single_point"

    if mode == "single":
        # Single building: either from address or from first point
        if address:
            query = address
        elif points and len(points) > 0:
            query = f"{points[0]['lat']},{points[0]['lon']}"
        else:
            raise ValueError("Mode 'single' requires either an address or at least one point")

        # Collect and score one building
        building_data = await _collect_building(query)
        risk_scores = compute_risk_scores(building_data)
        resolved_label = (building_data.get("adresse") or {}).get("label") or query
        lat = (building_data.get("adresse") or {}).get("lat", points[0]["lat"] if points else 0)
        lon = (building_data.get("adresse") or {}).get("lon", points[0]["lon"] if points else 0)

        building_results = [{
            "address_label": resolved_label,
            "lat": lat,
            "lon": lon,
            "building_data": building_data,
            "risk_scores": risk_scores,
            "source": "live",
            "error": None,
        }]

        report_address = address or resolved_label
        enumeration_method = "single_building"

    elif mode == "multi":
        # Multi: use polygon or points to enumerate buildings
        if polygon and len(polygon) >= 3:
            # Polygon mode: compute center and radius, try BDNB bulk
            centroid_lat, centroid_lon = _polygon_centroid(polygon)
            lon_min, lat_min, lon_max, lat_max = _polygon_bbox(polygon)
            diameter_km = _bbox_diameter_km(lon_min, lat_min, lon_max, lat_max)
            radius_m = max(100.0, diameter_km * 500)  # convert km to radius in m

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    bulk = await bdnb_bulk.fetch_buildings_in_radius(
                        client, centroid_lat, centroid_lon, radius_m,
                        settings.zone_max_buildings_per_job,
                    )
                    if bulk:
                        candidates = [
                            {"address_label": c.address_label, "lat": c.lat, "lon": c.lon}
                            for c in bulk
                        ]
                        enumeration_method = "bdnb_bulk_polygon"
            except Exception as exc:
                logger.warning("BDNB bulk failed for polygon: %s", exc)

            if not candidates:
                enumeration_method = "grid_polygon"
                grid = bdnb_bulk.grid_fallback_points(
                    centroid_lat, centroid_lon, radius_m,
                    spacing_m=max(50.0, radius_m / 6),
                    max_points=settings.zone_max_buildings_per_job,
                )
                candidates = [
                    {"address_label": None, "lat": g.lat, "lon": g.lon} for g in grid
                ]

            report_address = f"Polygone ({len(polygon)} sommets)"

        elif points and len(points) >= 1:
            # Points mode: treat each point as a candidate
            candidates = [
                {"address_label": None, "lat": p["lat"], "lon": p["lon"]}
                for p in points
            ]
            enumeration_method = f"manual_points_{len(points)}"
            report_address = f"{len(points)} point(s) sélectionné(s)"
        else:
            raise ValueError("Mode 'multi' requires either a polygon (≥3 points) or at least one point")

        # Run the collector fan-out on all candidates
        semaphore = asyncio.Semaphore(settings.zone_max_concurrency)
        tasks = [asyncio.create_task(process_one(c, semaphore)) for c in candidates]
        building_results = await asyncio.gather(*tasks)

    else:
        raise ValueError(f"Mode invalide: {mode!r}")

    # Run aggregator + report on the results (same as existing pipeline)
    fake_state = {
        "address": report_address,
        "radius_m": 0,
        "building_results": building_results,
        "enumeration_method": enumeration_method,
        "started_at": t0,
        "candidates": candidates if mode == "multi" else [],
        "center_lat": 0,
        "center_lon": 0,
    }

    agg_result = run_aggregator(fake_state)  # type: ignore
    fake_state["aggregate"] = agg_result["aggregate"]
    report_result = run_report(fake_state)  # type: ignore

    report = report_result["report"]
    report["address"] = report_address
    report["radius_m"] = 0
    report["duration_seconds"] = round(time.perf_counter() - t0, 2)

    logger.info(
        "zone_assessor -- %s %s -> %d batiments, score=%.1f, %.2fs",
        mode, report_address, report["nb_buildings"], report["aggregate_score"], report["duration_seconds"],
    )
    return report
