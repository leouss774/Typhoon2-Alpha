"""Climate risk scoring for mortgage analysis."""

from __future__ import annotations

import unicodedata
from typing import Any

from app.schemas.typhoon_bank import BankDataBundle, ClimateRiskResult


class ClimateRiskAgent:
    def run(self, data: BankDataBundle) -> ClimateRiskResult:
        building_data = data.building_data
        georisques = (data.climate_data.get("georisques") or {}) if data.climate_data else {}
        bdnb = building_data.get("bdnb") or {}
        batiment = bdnb.get("batiment") or {}

        flood = _score_flood(georisques)
        drought = max(_score_drought_from_bdnb(batiment), _score_drought_from_climate(data.climate_data))
        heat = _score_heat(data.climate_data)
        fire = _score_fire(georisques)

        climate_score = (0.4 * flood) + (0.25 * drought) + (0.2 * heat) + (0.15 * fire)
        risks = {
            "flood": flood,
            "drought": drought,
            "heat": heat,
            "fire": fire,
        }
        main_risks = [name for name, score in sorted(risks.items(), key=lambda item: item[1], reverse=True) if score >= 50]

        return ClimateRiskResult(
            flood_risk=round(flood, 2),
            drought_risk=round(drought, 2),
            heat_risk=round(heat, 2),
            fire_risk=round(fire, 2),
            climate_score=round(climate_score, 2),
            main_risks=main_risks[:3],
        )


def _score_flood(georisques: dict[str, Any]) -> float:
    score = 15.0
    if _payload_contains(georisques.get("risques_commune"), ("inond", "submersion", "crue")):
        score += 45
    if georisques.get("zones_inondables"):
        score += 25
    catnat_count = _count_items(georisques.get("catnat"))
    score += min(catnat_count * 2.5, 20)
    return _clamp(score)


def _score_drought_from_bdnb(batiment: dict[str, Any]) -> float:
    label = _normalize_text(batiment.get("alea_argile") or batiment.get("alea_retrait_gonflement_argile") or "")
    if "fort" in label:
        return 85.0
    if "moyen" in label or "modere" in label:
        return 60.0
    if "faible" in label:
        return 30.0
    return 20.0


def _score_drought_from_climate(climate_data: dict[str, Any]) -> float:
    copernicus = climate_data.get("copernicus") or {}
    drought_values = [float(value) for key, value in copernicus.items() if "drought" in key and _is_number(value)]
    if not drought_values:
        return 20.0
    return _clamp(25 + max(drought_values) * 8)


def _score_heat(climate_data: dict[str, Any]) -> float:
    open_meteo = climate_data.get("open_meteo") or {}
    projection = open_meteo.get("projection_2041_2050") or {}
    reference = open_meteo.get("reference_2015_2024") or {}
    projected_days = _first_number(projection, ("jours_chaleur_extreme_par_an", "jours_tres_chauds_par_an"))
    reference_days = _first_number(reference, ("jours_chaleur_extreme_par_an", "jours_tres_chauds_par_an")) or 0
    if projected_days is None:
        return 35.0
    return _clamp(20 + projected_days * 3 + max(0, projected_days - reference_days) * 2)


def _score_fire(georisques: dict[str, Any]) -> float:
    score = 15.0
    if _payload_contains(georisques.get("risques_commune"), ("feu de foret", "incendie", "forestier")):
        score += 55
    if _payload_contains(georisques.get("catnat"), ("secheresse", "feu", "incendie")):
        score += 15
    return _clamp(score)


def _payload_contains(payload: Any, needles: tuple[str, ...]) -> bool:
    text = _normalize_text(payload)
    return any(_normalize_text(needle) in text for needle in needles)


def _normalize_text(value: Any) -> str:
    text = str(value).lower()
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def _count_items(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("data", "features", "results"):
            if isinstance(payload.get(key), list):
                return len(payload[key])
    if isinstance(payload, list):
        return len(payload)
    return 0


def _first_number(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = row.get(name)
        if _is_number(value):
            return float(value)
    return None


def _is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))
