"""scoring_agent — calcul déterministe du score de risque par aléas.

Aucun LLM ici : chaque sous-score est une fonction pure d'un champ réel de
`building_data`, avec une justification texte.

v2 — Corrections :
1. INTÈGRE LE FORMULAIRE CLIENT : fissures, infiltrations, etat_toiture, isolation
   sont utilisés comme pénalités/malus sur les scores.
2. DEFAULTS AMÉLIORÉS : quand les données API sont absentes, les valeurs
   par défaut sont plus conservatrices (hypothèse de risque modéré).

Les recommandations sont générées par `backend/api/recommandations_generator.py`
et intégrées par `backend/app/digital_twin/contract.py`.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

ZONE_NAMES = ["fondations", "murs_nord", "murs_sud", "murs_est", "murs_ouest", "toiture", "sous_sol"]


# ── Helpers ──────────────────────────────────────────────────────────

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


# ── Pénalités du formulaire client ──────────────────────────────────────

def _form_penalties(formulaire: dict[str, Any] | None) -> dict[str, int]:
    """Calcule des pénalités de score à partir du formulaire client.

    Retourne un dict {zone: penalite} qui peut atteindre +40 points cumulés.
    """
    if not formulaire:
        return {}

    penalties: dict[str, int] = {}
    form = formulaire

    def _safe_lower(val: Any) -> str:
        return str(val).lower() if not isinstance(val, str) else val.lower()

    # Fissures → impact fondations/structure
    fissures = _safe_lower(form.get("fissures") or "")
    if fissures in ("importantes", "majeures"):
        penalties["fondations"] = penalties.get("fondations", 0) + 20
        penalties["murs_nord"] = penalties.get("murs_nord", 0) + 10
        penalties["murs_sud"] = penalties.get("murs_sud", 0) + 10
        penalties["murs_est"] = penalties.get("murs_est", 0) + 10
        penalties["murs_ouest"] = penalties.get("murs_ouest", 0) + 10
    elif fissures in ("moyennes", "présentes"):
        penalties["fondations"] = penalties.get("fondations", 0) + 12
        penalties["murs_nord"] = penalties.get("murs_nord", 0) + 5
        penalties["murs_sud"] = penalties.get("murs_sud", 0) + 5
        penalties["murs_est"] = penalties.get("murs_est", 0) + 5
        penalties["murs_ouest"] = penalties.get("murs_ouest", 0) + 5

    # Infiltrations → impact sous-sol et murs
    infiltrations = _safe_lower(form.get("infiltrations") or "")
    if infiltrations in ("oui", "majeures"):
        penalties["sous_sol"] = penalties.get("sous_sol", 0) + 20
        penalties["murs_nord"] = penalties.get("murs_nord", 0) + 10
        penalties["murs_sud"] = penalties.get("murs_sud", 0) + 10
    elif infiltrations in ("légères", "ponctuelles"):
        penalties["sous_sol"] = penalties.get("sous_sol", 0) + 10
        penalties["murs_nord"] = penalties.get("murs_nord", 0) + 3

    # Affaissement → impact fondations massif
    affaissement = _safe_lower(form.get("affaissement") or "")
    if affaissement in ("oui", "avéré"):
        penalties["fondations"] = penalties.get("fondations", 0) + 25
    elif affaissement in ("léger", "localisé"):
        penalties["fondations"] = penalties.get("fondations", 0) + 10

    # État toiture → impact toiture
    etat_toit = _safe_lower(form.get("etat_toiture") or "")
    if etat_toit in ("mauvais", "dégradé"):
        penalties["toiture"] = penalties.get("toiture", 0) + 20
    elif etat_toit in ("moyen", "vétuste"):
        penalties["toiture"] = penalties.get("toiture", 0) + 10

    # Isolation toiture → impact toiture (confort thermique)
    isolation = _safe_lower(form.get("isolation_toiture") or "")
    if isolation in ("faible", "inexistante", "absente"):
        penalties["toiture"] = penalties.get("toiture", 0) + 10

    # État structurel général → impact fondations + murs
    etat_struct = _safe_lower(form.get("etat_structure") or "")
    if etat_struct == "mauvais":
        penalties["fondations"] = penalties.get("fondations", 0) + 10
        for z in ["murs_nord", "murs_sud", "murs_est", "murs_ouest"]:
            penalties[z] = penalties.get(z, 0) + 8

    # Présence de sous-sol/cave → aggrave inondation
    if form.get("presence_sous_sol") or form.get("presence_cave"):
        penalties["sous_sol"] = penalties.get("sous_sol", 0) + 8

    # Année construction ancienne → aggrave structure
    annee = form.get("annee_construction")
    if isinstance(annee, (int, float)) and annee < 1950:
        penalties["fondations"] = penalties.get("fondations", 0) + 8
        for z in ["murs_nord", "murs_sud", "murs_est", "murs_ouest"]:
            penalties[z] = penalties.get(z, 0) + 5

    return penalties


# Les recommandations sont générées par le module dédié :
# backend/api/recommandations_generator.py → generate_zone_recommendations()
# et intégrées dans le contrat par backend/app/digital_twin/contract.py


# ── Sous-scores ─────────────────────────────────────────────────────────

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
        # Default amélioré : même sans donnée BDNB, on part sur du modéré (40) plutôt que 20
        base = min(40 + secheresses * 10, 70)
        source = f"aléa argile non fourni par la BDNB ; {secheresses} arrêté(s) CATNAT « sécheresse » ; estimation modérée par défaut"
    if aggravation_2050:
        base = min(base + 12, 100)
        source += " ; +12 pts pour horizon 2050"
    return _clamp(base), source


def _inondation_subscore(georisques: dict[str, Any] | None, precip_delta_pct: float = 0.0) -> tuple[int, str]:
    inondations = _count_catnat(georisques, "inondation")
    hazard_present = _has_hazard(georisques, "inondation")
    zones_inondables = _truthy_hazard_flag((georisques or {}).get("zones_inondables"))

    # Default amélioré : 25 au lieu de 15 pour être plus conservateur
    base = 25
    if inondations >= 6:
        base = 75
    elif inondations >= 3:
        base = 55
    elif inondations >= 1:
        base = 40
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
    # Default amélioré : 25 au lieu de 15, car par défaut il y a souvent des cavités
    base = 25 + min(n_cavites, 3) * 12 + min(n_mvt, 3) * 10
    source = f"{n_cavites} cavité(s), {n_mvt} mouvement(s) de terrain"
    return _clamp(base), source


def _sismique_subscore(georisques: dict[str, Any] | None) -> tuple[int, str]:
    zonage = _data_list(georisques, "zonage_sismique")
    zone = zonage[0].get("zone_sismicite") if zonage and isinstance(zonage[0], dict) else None
    mapping = {1: 15, 2: 30, 3: 50, 4: 70, 5: 88}
    zone_int = _parse_zone_sismicite(zone)
    if zone_int is not None and zone_int in mapping:
        return mapping[zone_int], f"zone de sismicité {zone_int}"
    # Default amélioré : 30 au lieu de 20 (par défaut, zone 2)
    return 30, "zone de sismicité non déterminée (estimation par défaut zone 2)"


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


# ── Assemblage par zone ─────────────────────────────────────────────────

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


def _compute_zones_for_period(
    building_data: dict[str, Any],
    climat_block: dict[str, Any] | None,
    is_projection: bool,
    form_penalties: dict[str, int] | None = None,
) -> dict[str, dict[str, Any]]:
    georisques = building_data.get("georisques")
    bdnb = building_data.get("bdnb")
    penalties = form_penalties or {}

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

    # Fondations
    fondations_risque = _clamp(
        argile_score * 0.55 + mvt_score * 0.25 + sismique_score * 0.20
        + penalties.get("fondations", 0)
    )
    zones["fondations"] = _build_zone(
        fondations_risque,
        "Retrait-gonflement des argiles" if argile_score >= mvt_score else "Mouvement de terrain",
        [argile_src, mvt_src, sismique_src],
    )

    # Murs
    murs_risque_base = precip_score * 0.5 + sismique_score * 0.3 + canicule_score * 0.2
    murs_justifs = [precip_src, canicule_src, sismique_src]
    for zone_name in ["murs_nord", "murs_sud", "murs_est", "murs_ouest"]:
        penalite = penalties.get(zone_name, 0)
        risque = _clamp(murs_risque_base + penalite)
        zones[zone_name] = _build_zone(risque, "Exposition climatique (façade)", murs_justifs)

    # Toiture
    toiture_risque = _clamp(
        canicule_score * 0.45 + precip_score * 0.15 + feu_foret_score * 0.40
        + penalties.get("toiture", 0)
    )
    zones["toiture"] = _build_zone(
        toiture_risque,
        "Feu de forêt" if feu_foret_score >= canicule_score else "Canicule / stress thermique",
        [canicule_src, precip_src, feu_foret_src],
    )

    # Sous-sol
    sous_sol_risque = _clamp(
        inondation_score * 0.7 + radon_score * 0.1 + argile_score * 0.2
        + penalties.get("sous_sol", 0)
    )
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


# ── Point d'entrée ──────────────────────────────────────────────────────

def compute_risk_scores(
    building_data: dict[str, Any],
    formulaire: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Point d'entrée du scoring_agent.

    Paramètres :
        building_data : données collectées (Georisques, BDNB, climat...)
        formulaire : formulaire client (fissures, infiltrations, etat_toiture...)

    Retourne :
        dict avec score_global, zones, projection_2050
    """
    logger.info("scoring_agent -- calcul des scores")

    climat = building_data.get("climat_open_meteo") or {}
    reference = climat.get("reference_2015_2024")
    projection = climat.get("projection_2041_2050")

    # Pénalités du formulaire client
    penalties = _form_penalties(formulaire)
    if penalties:
        logger.info("  -> penalités formulaire: %s", penalties)

    zones_2025 = _compute_zones_for_period(building_data, reference, is_projection=False, form_penalties=penalties)
    score_2025 = _score_global(zones_2025)

    zones_2050 = _compute_zones_for_period(building_data, projection or reference, is_projection=True, form_penalties=penalties)
    score_2050 = _score_global(zones_2050)

    return {
        "score_global": score_2025,
        "zones": zones_2025,
        "projection_2050": {
            "score_global": score_2050,
            "zones": zones_2050,
        },
    }
