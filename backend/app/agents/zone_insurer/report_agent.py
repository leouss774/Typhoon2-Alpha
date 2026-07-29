"""
report_agent — assembles the final insurer-oriented report with aggregate
risk tier, per-hazard breakdown, flagged assets, and templated recommendations.
"""

from __future__ import annotations

import time

from app.agents.zone_insurer.state import ZoneState
from app.core.logging import get_logger

logger = get_logger(__name__)

_RECOMMENDATIONS_BY_TIER = {
    "critique": [
        "Prioriser une inspection individuelle sur site pour chaque actif flagge avant toute souscription.",
        "Envisager une exclusion ou surprime ciblee sur les alea(s) dominant(s) identifies.",
    ],
    "eleve": [
        "Demander une etude de sol / diagnostic structurel pour les actifs proches du seuil critique.",
        "Prevoir une clause de franchise renforcee sur l'alea dominant de la zone.",
    ],
    "modere": [
        "Suivi standard suffisant ; revisiter la zone lors du prochain renouvellement.",
    ],
    "faible": [
        "Aucune action specifique requise au-dela du suivi standard.",
    ],
}


def run(state: ZoneState) -> dict:
    aggregate = state["aggregate"]
    tier = aggregate["aggregate_tier"]
    t0 = state.get("started_at", time.perf_counter())

    report = {
        "address": state["address"],
        "radius_m": state["radius_m"],
        "nb_buildings": aggregate["nb_buildings"],
        "nb_ok": aggregate["nb_ok"],
        "nb_errors": aggregate["nb_errors"],
        "aggregate_score": aggregate["aggregate_score"],
        "aggregate_tier": tier,
        "hazard_breakdown": aggregate["hazard_breakdown"],
        "flagged_buildings": aggregate["flagged_buildings"],
        "all_buildings": aggregate["all_buildings"],
        "recommendations": _RECOMMENDATIONS_BY_TIER.get(tier, []),
        "enumeration_method": state["enumeration_method"],
        "duration_seconds": round(time.perf_counter() - t0, 2),
    }

    logger.info("report_agent -- rapport assemble (tier=%s, %.2fs)", tier, report["duration_seconds"])
    return {"report": report}
