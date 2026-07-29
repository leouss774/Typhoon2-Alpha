"""
mvp_assessor — orchestrateur pour l'endpoint /mvp/assess.

Supporte mode single + multi avec le scoring simplifié (sans murs ni sous-sol).
Recommandations via Mistral RAG.
"""

from __future__ import annotations

import asyncio
import math
import statistics
import time
from typing import Any

import httpx

from app.agents.collector_agent import collect as _collect_building
from app.connectors import bdnb_bulk
from app.core.config import settings
from app.core.logging import get_logger
from app.recommandations.mapping import build_house_payload
from app.recommandations.service import generate_recommendations, get_index
from app.scoring.mvp_model import compute_risk_scores

logger = get_logger(__name__)

_TIER_BY_SCORE = [
    (25, "faible"),
    (50, "modere"),
    (75, "eleve"),
    (101, "critique"),
]


def _tier(score: float) -> str:
    for threshold, label in _TIER_BY_SCORE:
        if score < threshold:
            return label
    return "critique"


def _polygon_centroid(polygon: list[dict[str, float]]) -> tuple[float, float]:
    lat_sum = sum(p["lat"] for p in polygon)
    lon_sum = sum(p["lon"] for p in polygon)
    n = len(polygon)
    return lat_sum / n, lon_sum / n


def _polygon_bbox(polygon: list[dict[str, float]]) -> tuple[float, float, float, float]:
    lats = [p["lat"] for p in polygon]
    lons = [p["lon"] for p in polygon]
    return min(lons), min(lats), max(lons), max(lats)


def _bbox_diameter_km(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> float:
    center_lat = (lat_min + lat_max) / 2
    dlat_km = (lat_max - lat_min) * 111.32
    dlon_km = (lon_max - lon_min) * 111.32 * math.cos(math.radians(center_lat))
    return math.hypot(dlat_km, dlon_km)


def _hazard_breakdown_from_zones(zones: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    mapping = [
        ("rga_ground_movement", "fondations"),
        ("wildfire_wind", "toiture"),
        ("flood", "inondation"),
    ]
    result = []
    for hazard_label, zone_key in mapping:
        if zone_key in zones:
            s = zones[zone_key]["risque"]
            result.append({
                "hazard": hazard_label,
                "min_score": s,
                "max_score": s,
                "mean_score": round(float(s), 1),
                "pct_high_or_critical": round(100 * (1 if s >= 50 else 0), 1),
            })
    return result


def _agglomerate_hazard_breakdown(all_risk_scores: list[dict]) -> list[dict[str, Any]]:
    """Aggregate hazard breakdown across multiple buildings."""
    hazard_scores: dict[str, list[float]] = {}
    for rs in all_risk_scores:
        zones = rs.get("zones", {})
        for hazard_label, zone_key in [("rga_ground_movement", "fondations"), ("wildfire_wind", "toiture"), ("flood", "inondation")]:
            if zone_key in zones:
                hazard_scores.setdefault(hazard_label, []).append(float(zones[zone_key]["risque"]))

    result = []
    for hazard, scores in hazard_scores.items():
        if scores:
            result.append({
                "hazard": hazard,
                "min_score": min(scores),
                "max_score": max(scores),
                "mean_score": round(statistics.fmean(scores), 1),
                "pct_high_or_critical": round(100 * sum(1 for s in scores if s >= 50) / len(scores), 1),
            })
    return result


async def _generate_mistral_recos(building_data: dict, risk_scores: dict, tier: str) -> list[str]:
    try:
        house_payload = build_house_payload(building_data, risk_scores)
        if house_payload["zones"]:
            index = get_index()
            reco_result = await asyncio.to_thread(generate_recommendations, house_payload, index)
            recos = []
            for zone_entry in reco_result.get("zones", []):
                for rec in zone_entry.get("recommandations", []):
                    mesure = rec.get("mesure", "")
                    explication = rec.get("explication", "")
                    if mesure:
                        line = f"{mesure} : {explication}" if explication else mesure
                        if line not in recos:
                            recos.append(line)
            if recos:
                return recos
    except Exception as exc:
        logger.warning("mvp_assessor -- Mistral recos échouées: %s", exc)
    return _fallback_recommendations(tier)


def _fallback_recommendations(tier: str) -> list[str]:
    fb = {
        "critique": [
            "Risque critique — inspection structurelle par un bureau d'études fortement recommandée.",
            "Contacter un expert en sinistres pour évaluer les désordres existants.",
        ],
        "eleve": [
            "Planifier un diagnostic approfondi avec un professionnel du bâtiment.",
            "Envisager des travaux de renforcement selon l'aléa dominant.",
        ],
        "modere": [
            "Surveillance de routine recommandée. Réévaluer dans 12 à 24 mois.",
        ],
        "faible": [
            "Aucune action spécifique requise. Niveau de risque acceptable.",
        ],
    }
    return fb.get(tier, fb["modere"])


async def assess(mode: str, address: str | None = None, points: list[dict[str, float]] | None = None, polygon: list[dict[str, float]] | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()

    if mode == "single":
        if points and len(points) > 0:
            query = f"{points[0]['lat']},{points[0]['lon']}"
            logger.info("mvp_assessor -- single: using lat/lon -> %s", query)
        else:
            query = address or ""
        if not query:
            raise ValueError("Mode 'single' requires an address or at least one point")

        logger.info("mvp_assessor -- single: collecte pour %r", query)
        building_data = await _collect_building(query)
        risk_scores = compute_risk_scores(building_data)

        resolved_label = (building_data.get("adresse") or {}).get("label") or query
        lat = (building_data.get("adresse") or {}).get("lat", 0)
        lon = (building_data.get("adresse") or {}).get("lon", 0)
        score_global = risk_scores["score_global"]
        zones = risk_scores["zones"]
        tier = _tier(score_global)
        worst = max(zones, key=lambda z: zones[z]["risque"]) if zones else None

        building_summary = {
            "address_label": resolved_label, "lat": lat, "lon": lon,
            "score_global": float(score_global), "tier": tier, "worst_peril": worst,
        }

        hazard_breakdown = _hazard_breakdown_from_zones(zones)
        recommendations = await _generate_mistral_recos(building_data, risk_scores, tier)

        report = {
            "address": resolved_label,
            "score_global": float(score_global),
            "tier": tier,
            "hazard_breakdown": hazard_breakdown,
            "all_buildings": [building_summary],
            "flagged_buildings": [building_summary] if score_global >= 60 else [],
            "nb_buildings": 1,
            "nb_ok": 1,
            "nb_errors": 0,
            "recommendations": recommendations,
            "enumeration_method": "single_building_mvp",
            "duration_seconds": round(time.perf_counter() - t0, 2),
        }

        logger.info("mvp_assessor -- %s -> score=%d (%s), %.2fs", resolved_label, score_global, tier, report["duration_seconds"])
        return report

    else:
        # Multi mode
        polygon_pts = polygon or points or []
        if len(polygon_pts) < 3:
            raise ValueError("Mode 'multi' requires a polygon with at least 3 points")

        centroid_lat, centroid_lon = _polygon_centroid(polygon_pts)
        lon_min, lat_min, lon_max, lat_max = _polygon_bbox(polygon_pts)
        diameter_km = _bbox_diameter_km(lon_min, lat_min, lon_max, lat_max)
        radius_m = max(100.0, diameter_km * 500)

        candidates: list[dict[str, Any]] = []
        enumeration_method = "bdnb_bulk_polygon"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                bulk = await bdnb_bulk.fetch_buildings_in_radius(
                    client, centroid_lat, centroid_lon, radius_m, settings.zone_max_buildings_per_job,
                )
                if bulk:
                    candidates = [{"address_label": c.address_label, "lat": c.lat, "lon": c.lon} for c in bulk]
        except Exception as exc:
            logger.warning("BDNB bulk failed: %s", exc)

        if not candidates:
            enumeration_method = "grid_polygon"
            grid = bdnb_bulk.grid_fallback_points(
                centroid_lat, centroid_lon, radius_m,
                spacing_m=max(50.0, radius_m / 6),
                max_points=settings.zone_max_buildings_per_job,
            )
            candidates = [{"address_label": None, "lat": g.lat, "lon": g.lon} for g in grid]

        semaphore = asyncio.Semaphore(settings.zone_max_concurrency)

        async def _process_one_mvp(candidate: dict) -> dict[str, Any]:
            label = candidate.get("address_label")
            lat, lon = candidate["lat"], candidate["lon"]
            query = label if label else f"{lat},{lon}"
            async with semaphore:
                try:
                    building_data = await _collect_building(query)
                    risk_scores = compute_risk_scores(building_data)
                    resolved = (building_data.get("adresse") or {}).get("label") or label
                    return {
                        "address_label": resolved, "lat": lat, "lon": lon,
                        "building_data": building_data, "risk_scores": risk_scores,
                        "source": "live", "error": None,
                    }
                except Exception as exc:
                    logger.warning("mvp echec %r: %s", query, exc)
                    return {"address_label": label, "lat": lat, "lon": lon, "building_data": None, "risk_scores": None, "source": "live", "error": str(exc)}

        tasks = [asyncio.create_task(_process_one_mvp(c)) for c in candidates]
        building_results = await asyncio.gather(*tasks)

        ok_results = [r for r in building_results if r["error"] is None and r["risk_scores"]]
        all_risk_scores = [r["risk_scores"] for r in ok_results]

        building_summaries = []
        for r in ok_results:
            rs = r["risk_scores"]
            sg = rs["score_global"]
            zones = rs["zones"]
            tier_b = _tier(sg)
            worst = max(zones, key=lambda z: zones[z]["risque"]) if zones else None
            building_summaries.append({
                "address_label": r["address_label"], "lat": r["lat"], "lon": r["lon"],
                "score_global": float(sg), "tier": tier_b, "worst_peril": worst,
            })

        building_summaries.sort(key=lambda b: b["score_global"], reverse=True)
        flagged = [b for b in building_summaries if b["score_global"] >= 60]

        aggregate_score = float(statistics.fmean(b["score_global"] for b in building_summaries)) if building_summaries else 0.0
        aggregate_tier = _tier(aggregate_score)

        hazard_breakdown = _agglomerate_hazard_breakdown(all_risk_scores)

        report_address = f"Polygone ({len(polygon_pts)} sommets)"

        recommendations = _fallback_recommendations(aggregate_tier)

        return {
            "address": report_address,
            "score_global": round(aggregate_score, 1),
            "tier": aggregate_tier,
            "hazard_breakdown": hazard_breakdown,
            "all_buildings": building_summaries,
            "flagged_buildings": flagged,
            "nb_buildings": len(building_results),
            "nb_ok": len(ok_results),
            "nb_errors": len(building_results) - len(ok_results),
            "recommendations": recommendations,
            "enumeration_method": enumeration_method,
            "duration_seconds": round(time.perf_counter() - t0, 2),
        }
