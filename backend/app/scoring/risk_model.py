"""scoring_agent — calcul déterministe du score de risque par aléas.

Aucun LLM ici : chaque sous-score est une fonction pure d'un champ réel de
`building_data`, avec une justification texte.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

ZONE_NAMES = ["fondations", "murs_nord", "murs_sud", "murs_est", "murs_ouest", "toiture", "sous_sol"]


def _clamp(v: float, lo: float = 0, hi: float = 100) -> int:
    return int(round(max(lo, min(hi, v))))


def _niveau(risque: int) -> str:
    if risque < 30:
        return "faible"
    if risque < 60:
        return "modere"
    if risque < 80:
        return "eleve"
    return "critique"


def _data_list(georisques: dict[str, Any] | None, key: str) -> list:
    valeur = (georisques or {}).get(key)
    if isinstance(valeur, list):
        return valeur
    if isinstance(valeur, dict):
        data = valeur.get("data")
        if isinstance(data, list):
            return data
    return []


def _truthy_hazard_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, list):
            return len(data) > 0
        return bool(value)
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def _parse_zone_sismicite(zone: Any) -> int | None:
    if zone is None:
        return None
    if isinstance(zone, (int, float)):
        return int(zone)
    match = re.match(r"\s*(\d+)", str(zone))
    return int(match.group(1)) if match else None


def _count_catnat(georisques: dict[str, Any] | None, keyword: str) -> int:
    catnat = (georisques or {}).get("catnat") or {}
    data = catnat.get("data") if isinstance(catnat, dict) else None
    if not data:
        return 0
    return sum(1 for arrete in data if keyword in (arrete.get("libelle_risque_jo") or "").lower())


def _has_hazard(georisques: dict[str, Any] | None, keyword: str) -> bool:
    risques_commune = (georisques or {}).get("risques_commune") or {}
    data = risques_commune.get("data") if isinstance(risques_commune, dict) else None
    if not data:
        return False
    for entry in data:
        for detail in entry.get("risques_detail") or []:
            if keyword in (detail.get("libelle_risque_long") or "").lower():
                return True
    return False


def _source_en_erreur(georisques: dict[str, Any] | None, nom_source: str) -> bool:
    erreurs = (georisques or {}).get("erreurs") or []
    return any(nom_source in (e.get("source") or "") for e in erreurs)


# --- Sous-scores ---

_ALEA_ARGILE_SCORE = {"faible": 15, "moyen": 50, "fort": 82}


def _argile_subscore(bdnb: dict[str, Any] | None, georisques: dict[str, Any] | None, aggravation_2050: bool = False) -> tuple[int, str]:
    alea = None
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else None
    if isinstance(batiment, dict):
        alea = batiment.get("alea_argile")
    if alea is None and isinstance(bdnb, dict):
        alea = bdnb.get("alea_argile")

    if alea:
        base = _ALEA_ARGILE_SCORE.get(str(alea).strip().lower(), 40)
        source = f"aléa retrait-gonflement des argiles = « {alea} » (BDNB)"
    else:
        secheresses = _count_catnat(georisques, "sécheresse") or _count_catnat(georisques, "secheresse")
        base = min(20 + secheresses * 12, 65)
        source = f"aléa argile non fourni par la BDNB ; {secheresses} arrêté(s) CATNAT « sécheresse »"
    if aggravation_2050:
        base = min(base + 12, 100)
        source += " ; +12 pts pour horizon 2050"
    return _clamp(base), source


def _inondation_subscore(georisques: dict[str, Any] | None, precip_delta_pct: float = 0.0) -> tuple[int, str]:
    inondations = _count_catnat(georisques, "inondation")
    hazard_present = _has_hazard(georisques, "inondation")
    zones_inondables = _truthy_hazard_flag((georisques or {}).get("zones_inondables"))

    base = 15
    if inondations >= 6:
        base = 75
    elif inondations >= 3:
        base = 55
    elif inondations >= 1:
        base = 35
    if hazard_present:
        base += 8
    if zones_inondables:
        base += 12
    base += precip_delta_pct * 0.4

    source = f"{inondations} arrêté(s) CATNAT inondation recensé(s)"
    if hazard_present:
        source += " ; aléa inondation présent"
    if zones_inondables:
        source += " ; parcelle en zone inondable connue"
    return _clamp(base), source


def _mouvement_terrain_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    cavites = _data_list(georisques, "cavites")
    mvt = _data_list(georisques, "mouvements_de_terrain")
    n_cavites = len(cavites)
    n_mvt = len(mvt)
    base = 15 + min(n_cavites, 3) * 12 + min(n_mvt, 3) * 10
    source = f"{n_cavites} cavité(s), {n_mvt} mouvement(s) de terrain"
    return _clamp(base), source


def _sismique_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    zonage = _data_list(georisques, "zonage_sismique")
    zone = zonage[0].get("zone_sismicite") if zonage and isinstance(zonage[0], dict) else None
    mapping = {1: 15, 2: 30, 3: 50, 4: 70, 5: 88}
    zone_int = _parse_zone_sismicite(zone)
    if zone_int is not None and zone_int in mapping:
        return mapping[zone_int], f"zone de sismicité {zone_int}"
    return 20, "zone de sismicité non déterminée"


def _radon_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    radon = _data_list(georisques, "radon")
    potentiel = radon[0].get("classe_potentiel") if radon and isinstance(radon[0], dict) else None
    mapping = {1: 10, 2: 35, 3: 65}
    try:
        potentiel_int = int(potentiel) if potentiel is not None else None
    except (TypeError, ValueError):
        potentiel_int = None
    if potentiel_int in mapping:
        return mapping[potentiel_int], f"potentiel radon classe {potentiel_int}/3"
    return 15, "potentiel radon non déterminé"


def _feu_foret_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    present = _has_hazard(georisques, "feu de forêt") or _has_hazard(georisques, "feu de foret")
    if present:
        return 55, "aléa feu de forêt présent"
    return 10, "aucun aléa feu de forêt"


def _canicule_subscore(climat_block: dict[str, Any] | None) -> tuple[int, str]:
    jours = (climat_block or {}).get("jours_chaleur_extreme_par_an")
    if jours is None:
        return 30, "jours de chaleur extrême non disponibles"
    if jours < 3:
        base = 20
    elif jours < 6:
        base = 40
    elif jours < 10:
        base = 60
    else:
        base = 80
    return _clamp(base), f"{jours:.1f} jours de chaleur extrême/an"


def _roof_age_modifier(bdnb: dict[str, Any] | None) -> int:
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else (bdnb or {})
    annee = (batiment or {}).get("annee_construction") if isinstance(batiment, dict) else None
    if isinstance(annee, (int, float)) and annee < 1970:
        return 10
    return 0


def _precipitation_subscore(climat_block: dict[str, Any] | None) -> tuple[int, str]:
    mm = (climat_block or {}).get("precipitation_annuelle_moyenne_mm")
    if mm is None:
        return 30, "précipitations non disponibles"
    if mm < 600:
        base = 20
    elif mm < 800:
        base = 35
    elif mm < 1000:
        base = 50
    else:
        base = 65
    return _clamp(base), f"{mm:.0f} mm/an"


# --- Assemblage par zone ---

def _build_zone(risque: int, alea_principal: str, justifications: list[str]) -> dict[str, Any]:
    puces = []
    for texte in justifications:
        texte = (texte or "").strip()
        if not texte:
            continue
        texte = texte[0].upper() + texte[1:]
        if not texte.endswith((".", "!", "?")):
            texte += "."
        puces.append(texte)

    return {
        "risque": risque,
        "niveau": _niveau(risque),
        "alea_principal": alea_principal,
        "justification": "\n".join(f"• {p}" for p in puces),
        "recommandations": [],
    }


def _compute_zones_for_period(building_data: dict[str, Any], climat_block: dict[str, Any] | None, is_projection: bool) -> dict[str, dict[str, Any]]:
    georisques = building_data.get("georisques")
    bdnb = building_data.get("bdnb")

    ref_block = (building_data.get("climat_open_meteo") or {}).get("reference_2015_2024")
    precip_ref = (ref_block or {}).get("precipitation_annuelle_moyenne_mm")
    precip_now = (climat_block or {}).get("precipitation_annuelle_moyenne_mm")
    precip_delta_pct = 0.0
    if is_projection and precip_ref and precip_now:
        precip_delta_pct = max(0.0, (precip_now - precip_ref) / precip_ref * 100)

    argile_score, argile_src = _argile_subscore(bdnb, georisques, aggravation_2050=is_projection)
    inondation_score, inondation_src = _inondation_subscore(georisques, precip_delta_pct)
    mvt_score, mvt_src = _mouvement_terrain_subscore(georisques)
    sismique_score, sismique_src = _sismique_subscore(georisques)
    radon_score, radon_src = _radon_subscore(georisques)
    canicule_score, canicule_src = _canicule_subscore(climat_block)
    precip_score, precip_src = _precipitation_subscore(climat_block)
    feu_foret_score, feu_foret_src = _feu_foret_subscore(georisques)

    zones: dict[str, dict[str, Any]] = {}

    fondations_risque = _clamp(argile_score * 0.55 + mvt_score * 0.25 + sismique_score * 0.20)
    zones["fondations"] = _build_zone(
        fondations_risque,
        "Retrait-gonflement des argiles" if argile_score >= mvt_score else "Mouvement de terrain",
        [argile_src, mvt_src, sismique_src],
    )

    murs_risque = _clamp(precip_score * 0.5 + sismique_score * 0.3 + canicule_score * 0.2)
    murs_justifs = [precip_src, canicule_src, sismique_src]
    for zone_name in ["murs_nord", "murs_sud", "murs_est", "murs_ouest"]:
        zones[zone_name] = _build_zone(murs_risque, "Exposition climatique (façade)", murs_justifs)

    toiture_risque = _clamp(canicule_score * 0.45 + precip_score * 0.15 + feu_foret_score * 0.40)
    zones["toiture"] = _build_zone(
        toiture_risque,
        "Feu de forêt" if feu_foret_score >= canicule_score else "Canicule / stress thermique",
        [canicule_src, precip_src, feu_foret_src],
    )

    sous_sol_risque = _clamp(inondation_score * 0.7 + radon_score * 0.1 + argile_score * 0.2)
    zones["sous_sol"] = _build_zone(
        sous_sol_risque,
        "Inondation / remontée de nappe",
        [inondation_src, radon_src],
    )

    return zones


def _score_global(zones: dict[str, dict[str, Any]]) -> int:
    murs_moyenne = sum(zones[z]["risque"] for z in ("murs_nord", "murs_sud", "murs_est", "murs_ouest")) / 4
    total = (
        zones["fondations"]["risque"] * 0.25
        + zones["toiture"]["risque"] * 0.15
        + zones["sous_sol"]["risque"] * 0.20
        + murs_moyenne * 0.40
    )
    return _clamp(total)


def compute_risk_scores(building_data: dict[str, Any]) -> dict[str, Any]:
    """Point d'entrée du scoring_agent."""
    logger.info("scoring_agent -- calcul des scores")

    climat = building_data.get("climat_open_meteo") or {}
    reference = climat.get("reference_2015_2024")
    projection = climat.get("projection_2041_2050")

    zones_2025 = _compute_zones_for_period(building_data, reference, is_projection=False)
    score_2025 = _score_global(zones_2025)

    zones_2050 = _compute_zones_for_period(building_data, projection or reference, is_projection=True)
    score_2050 = _score_global(zones_2050)

    return {
        "score_global": score_2025,
        "zones": zones_2025,
        "projection_2050": {
            "score_global": score_2050,
            "zones": zones_2050,
        },
    }
