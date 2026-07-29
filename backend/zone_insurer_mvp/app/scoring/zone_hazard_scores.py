"""
Deterministic 0–100 scores per hazard for the zone risk map MVP.

See docs/SCORING.md for the business-readable summary.
"""

from __future__ import annotations

import re
from typing import Any

_HAZARD_BASE_PRESENT = 45


def _clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def score_to_tier(score: float) -> str:
    if score < 30:
        return "faible"
    if score < 60:
        return "modere"
    if score < 80:
        return "eleve"
    return "critique"


def _level_to_base(level: str | None) -> float:
    if not level:
        return 0.0
    raw = level.strip().lower()
    if raw in ("present", "présent"):
        return float(_HAZARD_BASE_PRESENT)
    if raw in ("faible", "1"):
        return 25.0
    if raw in ("moyen", "modere", "modéré", "2"):
        return 55.0
    if raw in ("eleve", "élevé", "fort", "3"):
        return 80.0
    if "faible" in raw:
        return 25.0
    if "moyen" in raw or "modere" in raw or "modéré" in raw:
        return 55.0
    if "eleve" in raw or "élevé" in raw or "fort" in raw:
        return 80.0
    return float(_HAZARD_BASE_PRESENT)


def _sismique_base(level: str | None) -> float:
    if not level:
        return 0.0
    match = re.match(r"\s*(\d+)", str(level))
    if match:
        zone = int(match.group(1))
        return {1: 10, 2: 25, 3: 45, 4: 65, 5: 85}.get(zone, 40.0)
    return _level_to_base(level)


def _proximity_bonus(distance_m: float | None, close: float, mid: float, bonus_close: float, bonus_mid: float) -> float:
    if distance_m is None:
        return 0.0
    if distance_m < close:
        return bonus_close
    if distance_m < mid:
        return bonus_mid
    return 0.0


def score_hazard(
    hazard_id: str,
    level: str | None,
    *,
    distance_cours_eau_m: float | None = None,
    distance_foret_m: float | None = None,
) -> float:
    if not level:
        return 0.0
    if hazard_id == "sismique":
        base = _sismique_base(level)
    else:
        base = _level_to_base(level)

    if hazard_id == "inondation":
        base += _proximity_bonus(distance_cours_eau_m, 100, 500, 15, 8)
    elif hazard_id == "feu_foret":
        base += _proximity_bonus(distance_foret_m, 200, 1000, 12, 6)

    return _clamp(base)


def building_score_global(hazards: list[dict[str, Any]]) -> float:
    scores = [h["score"] for h in hazards if h.get("score") is not None and h["score"] > 0]
    if not scores:
        return 0.0
    top = max(scores)
    mean = sum(scores) / len(scores)
    return round(_clamp(top * 0.7 + mean * 0.3), 1)


def apply_hazard_scores(point: dict[str, Any]) -> dict[str, Any]:
    """Mutates hazards in place with score; sets score_global on point."""
    dist_eau = point.get("distance_cours_eau_m")
    dist_foret = point.get("distance_foret_m")
    for h in point.get("hazards") or []:
        h["score"] = round(
            score_hazard(
                h["hazard"],
                h.get("level"),
                distance_cours_eau_m=dist_eau,
                distance_foret_m=dist_foret,
            ),
            1,
        )
    point["score_global"] = building_score_global(point.get("hazards") or [])
    return point
