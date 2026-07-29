"""
zone_aggregator_agent — computes per-hazard statistics, ranks assets by
risk, surfaces CATNAT claims history and DVF/DRIAS insurer-relevant
context.

v2: replaces the phase-1 structural-zone approximation with the REAL named
per-hazard subscores that risk_model.py already computes internally
(risk_scores["perils"] — see risk_model.py's compute_risk_scores docstring
for what changed there). No more mapping fondations->RGA, sous_sol->flood;
this now reads the actual argile/inondation/mouvement_terrain/sismique/
radon/feu_foret subscores directly.
"""

from __future__ import annotations

import statistics
from typing import Any

from app.agents.zone_insurer.state import ZoneState
from app.core.logging import get_logger
from app.scoring.risk_model import catnat_summary

logger = get_logger(__name__)

_TIER_BY_SCORE = [
    (25, "faible"),
    (50, "modere"),
    (75, "eleve"),
    (101, "critique"),
]

# Perils exposed by risk_model.py's "perils" dict that are genuine natural
# hazards an insurer report should show. canicule/precipitation are climate
# *conditions* feeding other perils rather than named insurable hazards in
# their own right, so they're left out of the headline hazard_breakdown but
# still available in each building's raw risk_scores if needed later.
_REPORTED_HAZARDS = ["rga_argile", "inondation", "mouvement_terrain", "sismique", "radon", "feu_foret"]


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
        perils = r["risk_scores"].get("perils", {})
        worst_hazard = (
            max((h for h in _REPORTED_HAZARDS if h in perils), key=lambda h: perils[h]["score"])
            if perils else None
        )
        building_data = r.get("building_data") or {}
        building_summaries.append(
            {
                "address_label": r["address_label"],
                "lat": r["lat"],
                "lon": r["lon"],
                "score_global": score_global,
                "tier": _tier(score_global),
                "worst_peril": worst_hazard,
                "flagged_for_review": score_global >= 60,
                "source": r["source"],
                "catnat": catnat_summary(building_data.get("georisques")),
                "distance_cours_eau_m": (building_data.get("distances") or {}).get("distance_cours_eau_m"),
                "distance_foret_m": (building_data.get("distances") or {}).get("distance_foret_m"),
            }
        )

    building_summaries.sort(key=lambda b: b["score_global"], reverse=True)
    flagged = [b for b in building_summaries if b["flagged_for_review"]]

    aggregate_score = (
        statistics.fmean(b["score_global"] for b in building_summaries) if building_summaries else 0.0
    )

    hazard_breakdown: list[dict[str, Any]] = []
    for hazard in _REPORTED_HAZARDS:
        scores = [
            r["risk_scores"]["perils"][hazard]["score"]
            for r in ok_results
            if hazard in (r["risk_scores"].get("perils") or {})
        ]
        if not scores:
            continue
        hazard_breakdown.append(
            {
                "hazard": hazard,
                "min_score": min(scores),
                "max_score": max(scores),
                "mean_score": round(statistics.fmean(scores), 1),
                "pct_high_or_critical": round(100 * sum(1 for s in scores if s >= 50) / len(scores), 1),
            }
        )

    # CATNAT agrege sur la zone (historique de sinistres declares — signal
    # fort et independant du modele de scoring, utile tel quel a un
    # assureur). On dedoublonne par commune (address_label) faute d'un
    # identifiant commune direct dans building_summaries.
    catnat_totals = {"inondation": 0, "secheresse": 0, "mouvement_terrain": 0, "total": 0}
    for b in building_summaries:
        for k in catnat_totals:
            catnat_totals[k] += b["catnat"].get(k, 0)

    # Contexte financier/climatique DVF + DRIAS (premier batiment "ok" qui
    # en a — ces deux sources sont departementales/locales, pas
    # batiment-par-batiment, donc identiques pour toute la zone).
    financial_context = None
    climate_projection = None
    for r in ok_results:
        bd = r.get("building_data") or {}
        if financial_context is None and bd.get("dvf_local"):
            financial_context = {"dvf_transactions_recentes": bd["dvf_local"][:5]}
        if climate_projection is None and bd.get("drias_local"):
            climate_projection = bd["drias_local"]
        if financial_context and climate_projection:
            break

    logger.info(
        "aggregator_agent -- %d batiments ok, score agrege=%.1f, %d flagges, catnat_total=%d",
        len(building_summaries), aggregate_score, len(flagged), catnat_totals["total"],
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
            "catnat_totals": catnat_totals,
            "financial_context": financial_context,
            "climate_projection": climate_projection,
        }
    }
