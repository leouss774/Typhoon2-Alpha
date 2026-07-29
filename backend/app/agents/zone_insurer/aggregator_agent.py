"""
zone_aggregator_agent — computes per-hazard statistics, ranks assets by risk.

NOTE: Phase 1 maps structural zones (fondations/sous_sol/toiture) to named
hazards as an approximation. A proper per-hazard breakdown requires reading
georisques' raw per-peril fields directly — worth doing before shipping to
an actual insurer.
"""

from __future__ import annotations

import statistics
from typing import Any

from app.agents.zone_insurer.state import ZoneState
from app.core.logging import get_logger

logger = get_logger(__name__)

_HAZARD_TO_ZONE = {
    "rga_ground_movement": "fondations",
    "flood": "sous_sol",
    "wildfire_wind": "toiture",
}

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


def run(state: ZoneState) -> dict:
    results = state["building_results"]
    ok_results = [r for r in results if r["error"] is None and r["risk_scores"]]

    building_summaries: list[dict[str, Any]] = []
    for r in results:
        if r["error"] is not None or not r["risk_scores"]:
            continue
        score_global = r["risk_scores"]["score_global"]
        zones = r["risk_scores"]["zones"]
        worst_zone_name = max(zones, key=lambda z: zones[z]["risque"]) if zones else None
        building_summaries.append({
            "address_label": r["address_label"],
            "lat": r["lat"],
            "lon": r["lon"],
            "score_global": score_global,
            "tier": _tier(score_global),
            "worst_peril": worst_zone_name,
            "flagged_for_review": score_global >= 60,
            "source": r["source"],
        })

    building_summaries.sort(key=lambda b: b["score_global"], reverse=True)
    flagged = [b for b in building_summaries if b["flagged_for_review"]]

    aggregate_score = (
        statistics.fmean(b["score_global"] for b in building_summaries) if building_summaries else 0.0
    )

    hazard_breakdown: list[dict[str, Any]] = []
    for hazard_label, zone_key in _HAZARD_TO_ZONE.items():
        scores = [
            r["risk_scores"]["zones"][zone_key]["risque"]
            for r in ok_results
            if zone_key in r["risk_scores"]["zones"]
        ]
        if not scores:
            continue
        hazard_breakdown.append({
            "hazard": hazard_label,
            "min_score": min(scores),
            "max_score": max(scores),
            "mean_score": round(statistics.fmean(scores), 1),
            "pct_high_or_critical": round(100 * sum(1 for s in scores if s >= 50) / len(scores), 1),
        })

    logger.info(
        "aggregator_agent -- %d batiments ok, score agrege=%.1f, %d flagges",
        len(building_summaries), aggregate_score, len(flagged),
    )

    return {
        "aggregate": {
            "nb_buildings": len(results),
            "nb_ok": len(ok_results),
            "nb_errors": len(results) - len(ok_results),
            "aggregate_score": round(aggregate_score, 1),
            "aggregate_tier": _tier(aggregate_score),
            "hazard_breakdown": hazard_breakdown,
            "flagged_buildings": flagged,
            "all_buildings": building_summaries,
        }
    }
