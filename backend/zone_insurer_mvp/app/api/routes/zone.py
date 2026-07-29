from __future__ import annotations

import asyncio
import math
import time

import httpx
from fastapi import APIRouter, HTTPException

from app.connectors import bdnb_bulk, geocoding
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.zone import (
    BuildingHazardSummary,
    CatnatTotals,
    HazardBreakdown,
    HazardInfo,
    SourceStatus,
    ZoneAssessRequest,
    ZoneReport,
)
from app.services.mistral_report import generate as generate_mistral_report
from app.services.zone_collector import collect_point
from app.services.zone_aggregator import aggregate

logger = get_logger(__name__)
router = APIRouter(prefix="/zone", tags=["zone-insurer"])


def _polygon_centroid(polygon: list[dict]) -> tuple[float, float]:
    lat_sum = sum(p["lat"] for p in polygon)
    lon_sum = sum(p["lon"] for p in polygon)
    return lat_sum / len(polygon), lon_sum / len(polygon)


def _polygon_bbox(polygon: list[dict]) -> tuple[float, float, float, float]:
    lats = [p["lat"] for p in polygon]
    lons = [p["lon"] for p in polygon]
    return min(lons), min(lats), max(lons), max(lats)


def _bbox_diameter_km(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> float:
    center_lat = (lat_min + lat_max) / 2
    dlat_km = (lat_max - lat_min) * 111.32
    dlon_km = (lon_max - lon_min) * 111.32 * math.cos(math.radians(center_lat))
    return math.hypot(dlat_km, dlon_km)


def _compute_data_quality(r: dict) -> str:
    errors = r.get("errors") or []
    has_failure = any(not e["ok"] for e in errors)
    if not has_failure:
        return "ok"
    hazards = r.get("hazards") or []
    return "failed" if not hazards else "partial"


def _successful_sources(results: list[dict]) -> list[str]:
    src_counter: dict[str, int] = {}
    total_ok = 0
    for r in results:
        if r.get("source") != "live":
            continue
        total_ok += 1
        seen = set()
        for e in (r.get("errors") or []):
            if e.get("ok") and e["source"] not in seen:
                seen.add(e["source"])
                src_counter[e["source"]] = src_counter.get(e["source"], 0) + 1
    if total_ok == 0:
        return []
    threshold = total_ok * 0.5
    return sorted(s for s, c in src_counter.items() if c >= threshold)


@router.post("/assess", response_model=ZoneReport)
async def assess_zone(payload: ZoneAssessRequest) -> ZoneReport:
    t0 = time.perf_counter()
    candidates: list[dict] = []
    enumeration_method = "single_point"

    if payload.mode == "single":
        if payload.points:
            pt = payload.points[0]
            candidates.append({"address_label": payload.address or "", "lat": pt.lat, "lon": pt.lon})
            report_address = payload.address or f"{pt.lat:.5f}, {pt.lon:.5f}"
            enumeration_method = "single_building"
        elif payload.address:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                geo = await geocoding.geocode_address(client, payload.address)
            candidates.append({"address_label": geo.label, "lat": geo.lat, "lon": geo.lon})
            report_address = payload.address
            enumeration_method = "single_building"
        else:
            raise HTTPException(400, "Mode single necessite une adresse ou un point")
    elif payload.polygon and len(payload.polygon) >= 3:
        polygon_pts = [p.model_dump() for p in payload.polygon]
        centroid_lat, centroid_lon = _polygon_centroid(polygon_pts)
        lon_min, lat_min, lon_max, lat_max = _polygon_bbox(polygon_pts)
        diameter_km = _bbox_diameter_km(lon_min, lat_min, lon_max, lat_max)
        radius_m = max(100.0, diameter_km * 500)
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as bdnb_client:
                bulk = await bdnb_bulk.fetch_buildings_in_radius(
                    bdnb_client, centroid_lat, centroid_lon, radius_m, settings.zone_max_buildings_per_job,
                )
            if bulk:
                candidates = [{"address_label": c.address_label, "lat": c.lat, "lon": c.lon} for c in bulk]
                enumeration_method = "bdnb_bulk_polygon"
        except Exception as exc:
            logger.warning("BDNB bulk failed: %s", exc)
        if not candidates:
            enumeration_method = "grid_polygon"
            grid = bdnb_bulk.grid_fallback_points(centroid_lat, centroid_lon, radius_m)
            candidates = [{"address_label": None, "lat": g.lat, "lon": g.lon} for g in grid]
        report_address = f"Polygone ({len(payload.polygon)} sommets)"
    elif payload.points:
        candidates = [{"address_label": None, "lat": p.lat, "lon": p.lon} for p in payload.points]
        enumeration_method = f"manual_points_{len(payload.points)}"
        report_address = f"{len(payload.points)} point(s) selectionne(s)"
    else:
        raise HTTPException(400, "Mode multi necessite un polygone ou des points")

    semaphore = asyncio.Semaphore(settings.zone_max_concurrency)

    async def _process_one(candidate: dict) -> dict:
        label = candidate.get("address_label")
        lat, lon = candidate["lat"], candidate["lon"]
        async with semaphore:
            return await collect_point(lat, lon, label)

    tasks = [asyncio.create_task(_process_one(c)) for c in candidates]
    results = await asyncio.gather(*tasks)

    agg = aggregate(results)
    ai, narrative_source = await generate_mistral_report(agg)
    agg["narrative"] = ai["narrative"]
    agg["recommendations"] = ai["recommendations"]
    agg["narrative_source"] = narrative_source

    duration = round(time.perf_counter() - t0, 2)

    nb_failed = agg["nb_errors"]
    data_sources_ok = _successful_sources(results)

    buildings = []
    for r in agg["buildings"]:
        hazards = [HazardInfo(**h) for h in r.get("hazards", [])]
        dq = _compute_data_quality(r)
        buildings.append(BuildingHazardSummary(
            address_label=r.get("address_label"),
            lat=r["lat"],
            lon=r["lon"],
            hazards=hazards,
            catnat_total=r.get("catnat_total", 0),
            distance_cours_eau_m=r.get("distance_cours_eau_m"),
            distance_foret_m=r.get("distance_foret_m"),
            bdnb_cle_interop_adr=r.get("bdnb_cle_interop_adr"),
            bdnb_geom=r.get("bdnb_geom"),
            source=r.get("source", "live"),
            source_errors=[SourceStatus(**e) for e in (r.get("errors") or [])],
            data_quality=dq,
            score_global=r.get("score_global"),
        ))

    hazard_breakdown = []
    for h in agg["hazard_breakdown"]:
        hazard_breakdown.append(HazardBreakdown(
            hazard=h["hazard"],
            label=h["label"],
            present_count=h["present_count"],
            total_count=h["total_count"],
            pct_present=h["pct_present"],
            levels=h.get("levels", []),
            mean_score=h.get("mean_score"),
            max_score=h.get("max_score"),
        ))

    catnat = agg["catnat_totals"]

    from app.services.mistral_report_v2 import generate_v2
    export_v2_data = await generate_v2(agg)

    logger.info(
        "POST /zone/assess -- %s -> %d points, %d hazards, %.2fs",
        report_address, len(results), len(hazard_breakdown), duration,
    )

    return ZoneReport(
        address=report_address,
        nb_points=len(results),
        nb_ok=agg["nb_ok"],
        nb_errors=nb_failed,
        hazard_breakdown=hazard_breakdown,
        catnat_totals=CatnatTotals(**catnat),
        buildings=buildings,
        narrative=agg["narrative"],
        recommendations=agg["recommendations"],
        enumeration_method=enumeration_method,
        duration_seconds=duration,
        narrative_source=agg.get("narrative_source", "template"),
        data_sources_ok=data_sources_ok,
        aggregate_score=agg.get("aggregate_score"),
        aggregate_tier=agg.get("aggregate_tier"),
        export_v2=export_v2_data,
    )
