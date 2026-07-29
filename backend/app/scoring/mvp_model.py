"""
mvp_model — scoring simplifié pour le MVP zone-insurer.

Sans murs_nord/sud/est/ouest ni sous_sol :
Zones gardées : fondations, toiture, inondation
Score global : fondations*0.40 + toiture*0.35 + inondation*0.25
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

ZONE_NAMES = ["fondations", "toiture", "inondation"]


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
    keyword = keyword.lower()
    return sum(1 for arrete in data if keyword in (arrete.get("libelle_risque_jo") or "").lower())


def _has_hazard(georisques: dict[str, Any] | None, keyword: str) -> bool:
    risques_commune = (georisques or {}).get("risques_commune") or {}
    data = risques_commune.get("data") if isinstance(risques_commune, dict) else None
    if not data:
        return False
    keyword = keyword.lower()
    for entry in data:
        for detail in entry.get("risques_detail") or []:
            if keyword in (detail.get("libelle_risque_long") or "").lower():
                return True
    return False


def _source_en_erreur(georisques: dict[str, Any] | None, nom_source: str) -> bool:
    erreurs = (georisques or {}).get("erreurs") or []
    return any(nom_source in (e.get("source") or "") for e in erreurs)


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
        source = f"aléa retrait-gonflement des argiles = « {alea} » (BDNB, au niveau du bâtiment)"
    else:
        secheresses = _count_catnat(georisques, "sécheresse") or _count_catnat(georisques, "secheresse")
        base = min(20 + secheresses * 12, 65)
        source = (
            f"aléa argile non fourni par la BDNB pour ce bâtiment ; "
            f"{secheresses} arrêté(s) CATNAT « sécheresse » recensé(s) sur la commune (indicateur de repli)"
        )
    if aggravation_2050:
        base = min(base + 12, 100)
        source += " ; +12 pts pour horizon 2050 (sécheresses plus fréquentes, cf. littérature BRGM/CCR)"
    return _clamp(base), source


def _inondation_subscore(georisques: dict[str, Any] | None, precip_delta_pct: float = 0.0) -> tuple[int, str]:
    inondations = _count_catnat(georisques, "inondation")
    hazard_present = _has_hazard(georisques, "inondation")
    zones_inondables = _truthy_hazard_flag((georisques or {}).get("zones_inondables"))
    zones_inondables_en_erreur = _source_en_erreur(georisques, "zones_inondables")

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

    source = f"{inondations} arrêté(s) CATNAT inondation recensé(s) sur la commune"
    if hazard_present:
        source += " ; aléa inondation présent dans le référentiel Géorisques communal"
    if zones_inondables:
        source += " ; parcelle en zone inondable connue (atlas Géorisques)"
    elif zones_inondables_en_erreur:
        source += " ; atlas des zones inondables (Géorisques) indisponible pour cette commune (erreur API), non pris en compte dans le score"
    return _clamp(base), source


def _mouvement_terrain_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    cavites = _data_list(georisques, "cavites")
    mvt = _data_list(georisques, "mouvements_de_terrain")
    mvt_catnat = _count_catnat(georisques, "mouvement de terrain")

    n_cavites = len(cavites)
    n_mvt = len(mvt)

    base = 15 + min(n_cavites, 3) * 12 + min(n_mvt, 3) * 10 + min(mvt_catnat, 3) * 8
    source = f"{n_cavites} cavité(s) souterraine(s) recensée(s), {n_mvt} mouvement(s) de terrain référencé(s) à proximité, {mvt_catnat} arrêté(s) CATNAT correspondant(s)"
    return _clamp(base), source


def _sismique_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    risques_commune = (georisques or {}).get("risques_commune") or {}
    data = risques_commune.get("data") if isinstance(risques_commune, dict) else None
    zone = None
    if data:
        for entry in data:
            for detail in entry.get("risques_detail") or []:
                if detail.get("zone_sismicite") is not None:
                    zone = detail["zone_sismicite"]
    if zone is None:
        zonage = _data_list(georisques, "zonage_sismique")
        if zonage:
            zone = zonage[0].get("zone_sismicite") if isinstance(zonage[0], dict) else None

    mapping = {0: 5, 1: 15, 2: 30, 3: 50, 4: 70, 5: 88}
    zone_int = _parse_zone_sismicite(zone)

    if zone_int is not None and zone_int in mapping:
        return mapping[zone_int], f"zone de sismicité {zone_int} (Géorisques)"
    return 20, "zone de sismicité non déterminée pour cette commune (valeur de repli faible)"


def _radon_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    radon = _data_list(georisques, "radon")
    potentiel = radon[0].get("classe_potentiel") if radon and isinstance(radon[0], dict) else None
    mapping = {1: 10, 2: 35, 3: 65}
    try:
        potentiel_int = int(potentiel)
    except (TypeError, ValueError):
        potentiel_int = None
    if potentiel_int in mapping:
        return mapping[potentiel_int], f"potentiel radon classe {potentiel_int}/3 (Géorisques)"
    return 15, "potentiel radon non déterminé (valeur de repli faible)"


def _feu_foret_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    present = _has_hazard(georisques, "feu de forêt") or _has_hazard(georisques, "feu de foret")
    if present:
        return 55, "aléa feu de forêt présent dans le référentiel Géorisques communal"
    return 10, "aucun aléa feu de forêt recensé par Géorisques pour cette commune"


def _canicule_subscore(climat_block: dict[str, Any] | None) -> tuple[int, str]:
    jours = (climat_block or {}).get("jours_chaleur_extreme_par_an")
    if jours is None:
        return 30, "jours de chaleur extrême non disponibles (Open-Meteo)"
    if jours < 3:
        base = 20
    elif jours < 6:
        base = 40
    elif jours < 10:
        base = 60
    else:
        base = 80
    return _clamp(base), f"{jours:.1f} jours de chaleur extrême/an projetés (Open-Meteo)"


def _precipitation_subscore(climat_block: dict[str, Any] | None) -> tuple[int, str]:
    mm = (climat_block or {}).get("precipitation_annuelle_moyenne_mm")
    if mm is None:
        return 30, "précipitations annuelles non disponibles (Open-Meteo)"
    if mm < 600:
        base = 20
    elif mm < 800:
        base = 35
    elif mm < 1000:
        base = 50
    else:
        base = 65
    return _clamp(base), f"{mm:.0f} mm/an de précipitations moyennes projetées (Open-Meteo)"


def _roof_age_modifier(bdnb: dict[str, Any] | None) -> int:
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else (bdnb or {})
    annee = (batiment or {}).get("annee_construction") if isinstance(batiment, dict) else None
    if isinstance(annee, (int, float)) and annee < 1970:
        return 10
    return 0


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
    roof_age_bonus = _roof_age_modifier(bdnb)

    zones: dict[str, dict[str, Any]] = {}

    fondations_risque = _clamp(argile_score * 0.55 + mvt_score * 0.25 + sismique_score * 0.20)
    zones["fondations"] = _build_zone(
        fondations_risque,
        "Retrait-gonflement des argiles" if argile_score >= mvt_score else "Mouvement de terrain",
        [argile_src, mvt_src, sismique_src],
    )

    toiture_risque = _clamp(canicule_score * 0.45 + precip_score * 0.15 + feu_foret_score * 0.40 + roof_age_bonus)
    toiture_justifs = [canicule_src, precip_src, feu_foret_src]
    if roof_age_bonus:
        toiture_justifs.append("toiture antérieure à 1970 : majoration de +10 points")
    zones["toiture"] = _build_zone(
        toiture_risque,
        "Feu de forêt" if feu_foret_score >= canicule_score else "Canicule / stress thermique",
        toiture_justifs,
    )

    inondation_risque = _clamp(inondation_score * 0.70 + radon_score * 0.15 + argile_score * 0.15)
    zones["inondation"] = _build_zone(
        inondation_risque,
        "Inondation / remontée de nappe",
        [inondation_src, radon_src],
    )

    for zone_name in ZONE_NAMES:
        logger.info("  [%s] risque=%d (%s)", zone_name, zones[zone_name]["risque"], zones[zone_name]["niveau"])

    return zones


def _score_global(zones: dict[str, dict[str, Any]]) -> int:
    total = (
        zones["fondations"]["risque"] * 0.40
        + zones["toiture"]["risque"] * 0.35
        + zones["inondation"]["risque"] * 0.25
    )
    return _clamp(total)


def compute_risk_scores(building_data: dict[str, Any]) -> dict[str, Any]:
    logger.info("mvp_model -- calcul des scores simplifiés (aujourd'hui + projection 2050)")

    climat = building_data.get("climat_open_meteo") or {}
    reference = climat.get("reference_2015_2024")
    projection = climat.get("projection_2041_2050")

    logger.info("periode reference (2025) :")
    zones_2025 = _compute_zones_for_period(building_data, reference, is_projection=False)
    score_2025 = _score_global(zones_2025)
    logger.info("  -> score_global = %d", score_2025)

    logger.info("periode projection (2050) :")
    zones_2050 = _compute_zones_for_period(building_data, projection or reference, is_projection=True)
    score_2050 = _score_global(zones_2050)
    logger.info("  -> score_global = %d", score_2050)

    return {
        "score_global": score_2025,
        "zones": zones_2025,
        "projection_2050": {
            "score_global": score_2050,
            "zones": zones_2050,
        },
    }
