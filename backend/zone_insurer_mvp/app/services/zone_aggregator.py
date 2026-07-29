from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.scoring.zone_hazard_scores import score_to_tier

logger = get_logger(__name__)

_HAZARD_ORDER = ["rga_argile", "inondation", "mouvement_terrain", "sismique", "radon", "feu_foret"]
_HAZARD_LABELS = {
    "rga_argile": "Retrait-gonflement argiles",
    "inondation": "Inondation",
    "mouvement_terrain": "Mouvement de terrain",
    "sismique": "Séisme",
    "radon": "Radon",
    "feu_foret": "Feu de forêt",
}

_FALLBACK_RECOMMENDATIONS: dict[str, list[str]] = {
    "critique": [
        "Zone a risque critique : revue de souscription obligatoire sur les actifs les plus exposes.",
        "Envisager exclusion ou surprime sur l'alea dominant.",
    ],
    "eleve": [
        "Risque eleve : inspection individuelle recommandee avant engagement.",
        "Clause de franchise renforcee sur l'alea principal.",
    ],
    "modere": [
        "Risques presents mais maitrisables : suivi standard au renouvellement.",
    ],
    "faible": [
        "Profil de risque faible : aucune action specifique au-dela du suivi standard.",
    ],
}


def _catnat_totals(results: list[dict]) -> dict[str, int]:
    total_inondation = 0
    total_secheresse = 0
    total_mvt = 0
    for r in results:
        by_type = r.get("catnat_by_type") or {}
        total_inondation += by_type.get("inondation", 0)
        total_secheresse += by_type.get("secheresse", 0)
        total_mvt += by_type.get("mouvement_terrain", 0)
    return {
        "inondation": total_inondation,
        "secheresse": total_secheresse,
        "mouvement_terrain": total_mvt,
        "total": total_inondation + total_secheresse + total_mvt,
    }


def _build_narrative(
    hazard_breakdown: list[dict],
    nb_ok: int,
    catnat: dict,
    aggregate_score: float | None,
    aggregate_tier: str | None,
) -> str:
    present = [h for h in hazard_breakdown if h["present_count"] > 0]
    parts = [f"Zone etudiee : {nb_ok} point(s) analyse(s)."]
    if aggregate_score is not None and aggregate_tier:
        parts.append(f"Score agrégé {aggregate_score}/100 (niveau {aggregate_tier}).")
    if present:
        names = ", ".join(h["label"] for h in present)
        parts.append(f"Aleas presents : {names}.")
    if catnat["total"] > 0:
        parts.append(
            f"Historique CATNAT : {catnat['total']} arrete(s) recense(s) "
            f"(inondation {catnat['inondation']}, secheresse {catnat['secheresse']}, "
            f"mouvement {catnat['mouvement_terrain']})."
        )
    else:
        parts.append("Aucun arrete CATNAT classe recense pour les points de la zone.")
    return " ".join(parts)


def _build_recommendations(aggregate_tier: str | None, hazard_breakdown: list[dict]) -> list[str]:
    if aggregate_tier and aggregate_tier in _FALLBACK_RECOMMENDATIONS:
        return _FALLBACK_RECOMMENDATIONS[aggregate_tier]
    present_count = sum(1 for h in hazard_breakdown if h["present_count"] > 0)
    if present_count >= 3:
        return _FALLBACK_RECOMMENDATIONS["eleve"]
    if present_count >= 1:
        return _FALLBACK_RECOMMENDATIONS["modere"]
    return _FALLBACK_RECOMMENDATIONS["faible"]


def _count_quality_failed(results: list[dict]) -> int:
    failed = 0
    for r in results:
        errors = r.get("errors") or []
        has_failure = any(not e.get("ok") for e in errors)
        hazards = r.get("hazards") or []
        if has_failure and not hazards:
            failed += 1
    return failed


def aggregate(results: list[dict]) -> dict[str, Any]:
    ok = [r for r in results if r.get("source") == "live"]
    nb_ok = len(ok)
    nb_errors = _count_quality_failed(results)

    hazard_breakdown: list[dict] = []
    for hazard_id in _HAZARD_ORDER:
        present = [r for r in ok if any(h["hazard"] == hazard_id and h["level"] for h in (r.get("hazards") or []))]
        levels = list(
            {
                h["level"]
                for r in ok
                for h in (r.get("hazards") or [])
                if h["hazard"] == hazard_id and h["level"]
            }
        )
        scores = [
            h["score"]
            for r in ok
            for h in (r.get("hazards") or [])
            if h["hazard"] == hazard_id and h.get("score") is not None and h["level"]
        ]
        if not present:
            continue
        hazard_breakdown.append({
            "hazard": hazard_id,
            "label": _HAZARD_LABELS.get(hazard_id, hazard_id),
            "present_count": len(present),
            "total_count": len(ok),
            "pct_present": round(100 * len(present) / max(len(ok), 1), 1),
            "levels": levels,
            "mean_score": round(sum(scores) / len(scores), 1) if scores else None,
            "max_score": round(max(scores), 1) if scores else None,
        })

    catnat = _catnat_totals(ok)
    building_scores = [r.get("score_global") or 0 for r in ok if (r.get("score_global") or 0) > 0]
    aggregate_score = round(sum(building_scores) / len(building_scores), 1) if building_scores else None
    aggregate_tier = score_to_tier(aggregate_score) if aggregate_score is not None else None

    narrative = _build_narrative(hazard_breakdown, nb_ok, catnat, aggregate_score, aggregate_tier)
    recommendations = _build_recommendations(aggregate_tier, hazard_breakdown)

    return {
        "nb_ok": nb_ok,
        "nb_errors": nb_errors,
        "hazard_breakdown": hazard_breakdown,
        "catnat_totals": catnat,
        "buildings": ok,
        "narrative": narrative,
        "recommendations": recommendations,
        "aggregate_score": aggregate_score,
        "aggregate_tier": aggregate_tier,
        "narrative_source": "template",
    }
