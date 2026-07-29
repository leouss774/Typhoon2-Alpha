"""
report_agent — assembles the final insurer-oriented report: aggregate risk
tier, real per-hazard breakdown, flagged assets, CATNAT claims history,
DVF/DRIAS context, and an AI-generated narrative + recommendations (with a
deterministic fallback — see mistral_report.py).
"""

from __future__ import annotations

import time

from app.agents.zone_insurer import mistral_report
from app.agents.zone_insurer.state import ZoneState
from app.core.logging import get_logger

logger = get_logger(__name__)


async def run(state: ZoneState) -> dict:
    aggregate = state["aggregate"]
    tier = aggregate["aggregate_tier"]
    t0 = state.get("started_at", time.perf_counter())

    ai = await mistral_report.generate(aggregate)

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
        "catnat_totals": aggregate["catnat_totals"],
        "financial_context": aggregate["financial_context"],
        "climate_projection": aggregate["climate_projection"],
        "narrative": ai["narrative"],
        "recommendations": ai["recommendations"],
        "enumeration_method": state["enumeration_method"],
        "duration_seconds": round(time.perf_counter() - t0, 2),
    }

    logger.info("report_agent -- rapport assemble (tier=%s, %.2fs)", tier, report["duration_seconds"])
    return {"report": report}
