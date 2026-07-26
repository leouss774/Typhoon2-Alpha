"""
scoring_agent — calcul deterministe du score de risque par aleas et par
partie du batiment (cf. README racine, section "scoring_agent" : "La
methode de calcul precise reste a specifier" — ce module est cette
specification, sous forme executable).

Aucun LLM ici : chaque sous-score est une fonction pure d'un champ reel de
`building_data` (sortie de collector_agent), avec une justification texte
qui cite explicitement la donnee utilisee — c'est ce qui permet de dire
"le score est explicable" plutot que "une IA a sorti un chiffre".

Sources utilisees (voir README "Sources de donnees du diagnostic") :
  - georisques.risques_commune / catnat / cavites / mouvements_de_terrain /
    zonage_sismique / radon  (aleas officiels + historique de sinistres)
  - bdnb.alea_argile (alea RGA precalcule au niveau du batiment, plus
    precis que l'alea communal de Georisques quand il est disponible)
  - climat_open_meteo.reference_2015_2024 / projection_2041_2050
    (canicule, precipitations)

Chaque zone du contrat (`fondations`, `murs_nord/sud/est/ouest`, `toiture`,
`sous_sol`) combine un sous-ensemble pertinent de ces signaux avec des
poids documentes ci-dessous. Les 4 murs partagent un socle commun
(sismique + precipitations + canicule) modulo un delta d'exposition par
orientation (nord/sud/est/ouest) : aucune donnee directionnelle n'existe
dans nos sources (ni Georisques ni la BDNB ne donnent de risque par
facade), ce delta est donc une heuristique d'exposition climatique
generale (ensoleillement sud, humidite nord, intemperies dominantes
d'ouest en France metropolitaine) — assumee et documentee comme telle,
pas presentee comme une mesure.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

ZONE_NAMES = ["fondations", "murs_nord", "murs_sud", "murs_est", "murs_ouest", "toiture", "sous_sol"]

# Delta d'exposition directionnelle appliquee au socle "murs" commun.
# Cf. docstring : heuristique d'exposition climatique generale (pas de
# donnee Georisques/BDNB par facade), calibree pour rester dans l'ordre
# ouest > nord > est > sud deja utilise dans le prototype front.
_EXPOSITION_MURS_DELTA = {"murs_nord": 6, "murs_sud": -6, "murs_est": -2, "murs_ouest": 10}


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


# ---------------------------------------------------------------------------
# Sous-scores individuels (0-100) + description de la donnee utilisee
# ---------------------------------------------------------------------------

_ALEA_ARGILE_SCORE = {"faible": 15, "moyen": 50, "fort": 82}


def _argile_subscore(bdnb: dict[str, Any] | None, georisques: dict[str, Any] | None, aggravation_2050: bool = False) -> tuple[int, str]:
    alea = None
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else None
    if isinstance(batiment, dict):
        alea = batiment.get("alea_argile")
    # Le payload BDNB brut (hors wrapper connecteur) peut aussi arriver a plat.
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
    zones_inondables = (georisques or {}).get("zones_inondables")

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
    base += precip_delta_pct * 0.4  # aggravation projetee des precipitations extremes

    source = f"{inondations} arrêté(s) CATNAT inondation recensé(s) sur la commune"
    if hazard_present:
        source += " ; aléa inondation présent dans le référentiel Géorisques communal"
    if zones_inondables:
        source += " ; parcelle en zone inondable connue (atlas Géorisques)"
    return _clamp(base), source


def _mouvement_terrain_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    cavites = (georisques or {}).get("cavites")
    mvt = (georisques or {}).get("mouvements_de_terrain")
    mvt_catnat = _count_catnat(georisques, "mouvement de terrain")

    n_cavites = len(cavites) if isinstance(cavites, list) else 0
    n_mvt = len(mvt) if isinstance(mvt, list) else 0

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
    zonage = (georisques or {}).get("zonage_sismique")
    if zone is None and isinstance(zonage, list) and zonage:
        zone = zonage[0].get("zone_sismicite") if isinstance(zonage[0], dict) else None

    mapping = {0: 5, 1: 15, 2: 30, 3: 50, 4: 70, 5: 88}
    try:
        zone_int = int(zone)
    except (TypeError, ValueError):
        zone_int = None

    if zone_int is not None and zone_int in mapping:
        return mapping[zone_int], f"zone de sismicité {zone_int} (Géorisques)"
    return 20, "zone de sismicité non déterminée pour cette commune (valeur de repli faible)"


def _radon_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    radon = (georisques or {}).get("radon")
    potentiel = None
    if isinstance(radon, list) and radon:
        potentiel = radon[0].get("classe_potentiel") if isinstance(radon[0], dict) else None
    mapping = {1: 10, 2: 35, 3: 65}
    try:
        potentiel_int = int(potentiel)
    except (TypeError, ValueError):
        potentiel_int = None
    if potentiel_int in mapping:
        return mapping[potentiel_int], f"potentiel radon classe {potentiel_int}/3 (Géorisques)"
    return 15, "potentiel radon non déterminé (valeur de repli faible)"


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


# ---------------------------------------------------------------------------
# Assemblage par zone
# ---------------------------------------------------------------------------

def _build_zone(risque: int, alea_principal: str, justification: str) -> dict[str, Any]:
    return {
        "risque": risque,
        "niveau": _niveau(risque),
        "alea_principal": alea_principal,
        "justification": justification,
        "recommandations": [],  # rag_agent non branche : voir README Roadmap
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
    roof_age_bonus = _roof_age_modifier(bdnb)

    zones: dict[str, dict[str, Any]] = {}

    fondations_risque = _clamp(argile_score * 0.55 + mvt_score * 0.25 + sismique_score * 0.20)
    zones["fondations"] = _build_zone(
        fondations_risque,
        "Retrait-gonflement des argiles" if argile_score >= mvt_score else "Mouvement de terrain",
        f"{argile_src}. {mvt_src}. {sismique_src}.",
    )

    murs_base = _clamp(precip_score * 0.5 + sismique_score * 0.3 + canicule_score * 0.2)
    murs_justif = f"{precip_src}. {canicule_src}. {sismique_src}."
    for zone_name, delta in _EXPOSITION_MURS_DELTA.items():
        risque = _clamp(murs_base + delta)
        alea = "Intempéries (exposition ouest dominante)" if zone_name == "murs_ouest" else (
            "Infiltration (exposition nord)" if zone_name == "murs_nord" else (
                "Stress thermique (exposition sud)" if zone_name == "murs_sud" else "Vent"
            )
        )
        zones[zone_name] = _build_zone(risque, alea, murs_justif + " Delta d'exposition directionnelle (heuristique, non mesurée par Géorisques).")

    toiture_risque = _clamp(canicule_score * 0.65 + precip_score * 0.20 + roof_age_bonus)
    zones["toiture"] = _build_zone(
        toiture_risque,
        "Canicule / stress thermique",
        f"{canicule_src}. {precip_src}." + (" Toiture antérieure à 1970 (majoration +10)." if roof_age_bonus else ""),
    )

    sous_sol_risque = _clamp(inondation_score * 0.7 + radon_score * 0.1 + argile_score * 0.2)
    zones["sous_sol"] = _build_zone(
        sous_sol_risque,
        "Inondation / remontée de nappe",
        f"{inondation_src}. {radon_src}.",
    )

    for zone_name in ZONE_NAMES:
        logger.info("  [%s] risque=%d (%s)", zone_name, zones[zone_name]["risque"], zones[zone_name]["niveau"])

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
    """Point d'entree du scoring_agent.

    Retourne {"score_global", "zones", "projection_2050": {"score_global", "zones"}}
    — exactement la forme attendue par le contrat digital_twin_agent.
    """
    logger.info("scoring_agent -- calcul des scores (aujourd'hui + projection 2050)")

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
