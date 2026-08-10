"""
scoring_agent — calcul déterministe du score de risque par aléa et par
partie du bâtiment.

Améliorations intégrées depuis le Typhon Risk Engine v2 (collègue) :
  - D01 : Statuts explicites de source (AVAILABLE / SOURCE_ERROR / …)
    → une API en erreur 404 n'est plus traitée comme « pas de risque »
  - D02 : Score de confiance (0-100) indépendant du score de risque
  - D03 : Cinq bandes de risque alignées sur les classes du Risk Engine
  - D04 : Traçabilité des sources utilisées dans chaque zone
  - D05 : Séparation F (aléa) / V (vulnérabilité) + combinaison par
    moyenne géométrique non-compensatoire : R = 100 × (F/100)^0.5 × (V/100)^0.5
  - D06 : Projection 2050 intégrée (choix délibéré pour le jumeau 3D,
    contrairement au Risk Engine qui l'exclut de F/V/R)

Aucun LLM ici : chaque sous-score est une fonction pure d'un champ réel de
`building_data` (sortie de collector_agent), avec une justification texte
qui cite explicitement la donnée utilisée.

Sources utilisées :
  - georisques.risques_commune / catnat / cavites / mouvements_de_terrain /
    zonage_sismique / radon  (aléas officiels + historique de sinistres)
  - bdnb.alea_argile (aléa RGA précalculé au niveau du bâtiment)
  - bdnb.annee_construction (vulnérabilité structurelle)
  - climat_open_meteo.reference_2015_2024 / projection_2041_2050
    (canicule, précipitations)
"""

from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

ZONE_NAMES = ["fondations", "murs_nord", "murs_sud", "murs_est", "murs_ouest", "toiture", "sous_sol"]

# ---------------------------------------------------------------------------
# D01 : Statuts explicites de source
# ---------------------------------------------------------------------------


class SourceStatus(str, Enum):
    """Statut d'une source de données. Sept cas non interchangeables.

    AVAILABLE : donnée présente et exploitable
    NO_FEATURE_FOUND : requête OK, zéro objet retourné (≠ « risque nul »)
    SOURCE_ERROR : API en erreur (404, 429, 5xx…) → ne prouve PAS l'absence
    NOT_CONFIGURED : source non paramétrée
    NOT_COLLECTED : le pipeline ne demande pas ce champ
    NOT_APPLICABLE : sans objet pour ce bien
    DEFAULT_VALUE : valeur de repli arbitraire
    """

    AVAILABLE = "AVAILABLE"
    NO_FEATURE_FOUND = "NO_FEATURE_FOUND"
    SOURCE_ERROR = "SOURCE_ERROR"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_COLLECTED = "NOT_COLLECTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    DEFAULT_VALUE = "DEFAULT_VALUE"


def _qualite_source(nom_source: str) -> float:
    """Qualité de base par source (1.0 = meilleure). Utilisée par la confiance."""
    qualites = {
        "bdnb.alea_argile": 1.0,
        "bdnb.annee_construction": 0.95,
        "bdnb.batiment": 0.95,
        "ign.altitude": 1.0,
        "georisques.risques_commune": 0.70,
        "georisques.catnat": 0.70,
        "georisques.zonage_sismique": 0.70,
        "georisques.zones_inondables": 0.70,
        "georisques.radon": 0.65,
        "georisques.cavites": 0.65,
        "georisques.mouvements_de_terrain": 0.65,
        "georisques.feu_foret": 0.70,
        "open_meteo.reference": 0.50,
        "open_meteo.projection": 0.40,
        "fallback.catnat": 0.25,
        "default": 0.10,
    }
    return qualites.get(nom_source, 0.30)


# ---------------------------------------------------------------------------
# Helpers bas niveau
# ---------------------------------------------------------------------------


def _clamp(v: float, lo: float = 0, hi: float = 100) -> int:
    return int(round(max(lo, min(hi, v))))


def _niveau(risque: int) -> str:
    """D03 : Cinq bandes de risque alignées sur le Risk Engine.

    0-19  : très faible
    20-39 : faible
    40-59 : modéré
    60-79 : élevé
    80-100: très élevé
    """
    if risque < 20:
        return "tres faible"
    if risque < 40:
        return "faible"
    if risque < 60:
        return "modere"
    if risque < 80:
        return "eleve"
    return "tres eleve"


def _combine_risk(f_score: float, v_score: float) -> float:
    """D05 : Combinaison F × V par moyenne géométrique non-compensatoire.

    R = 100 × (F/100)^0.5 × (V/100)^0.5

    Propriétés :
      - F = 0 ⇒ R = 0 (pas d'aléa = pas de risque)
      - Monotone en F et V
      - Bornée dans [0, 100]
    """
    if f_score <= 0:
        return 0.0
    v = max(float(v_score), 0.0)
    return 100.0 * math.sqrt(f_score / 100.0) * math.sqrt(v / 100.0)


def _data_list(georisques: dict[str, Any] | None, key: str) -> list:
    """Extrait la liste « data » d'un sous-champ Géorisques paginé."""
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
    return sum(1 for a in data if keyword in (a.get("libelle_risque_jo") or "").lower())


def _has_hazard(georisques: dict[str, Any] | None, keyword: str) -> bool:
    rc = (georisques or {}).get("risques_commune") or {}
    data = rc.get("data") if isinstance(rc, dict) else None
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
    # Erreurs peuvent être des dicts (forme normale) OU des chaînes brutes
    # (ex. "georisques totalement indisponible" quand la source a totalement
    # échoué) : on ignore les entrées non structurées au lieu de planter.
    return any(
        nom_source in (e.get("source") or "")
        for e in erreurs
        if isinstance(e, dict)
    )


def _vulnerabilite_batiment(bdnb: dict[str, Any] | None) -> tuple[float, str, dict[str, Any]]:
    """D05 : Calcule l'indice de vulnérabilité V (0-100) du bâtiment à partir
    de ses caractéristiques structurelles.

    Utilise l'année de construction comme principal indicateur :
    plus le bâtiment est ancien, plus il est vulnérable (normes moins récentes,
    matériaux moins résistants, vétusté).
    """
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else (bdnb or {})
    if isinstance(batiment, dict):
        annee = batiment.get("annee_construction")
    else:
        annee = None

    tracking = {
        "source": "bdnb.annee_construction",
        "statut": SourceStatus.AVAILABLE.value if annee else SourceStatus.NOT_COLLECTED.value,
        "annee": annee,
    }

    if not annee or not isinstance(annee, (int, float)):
        return 50.0, "vulnérabilité du bâti non déterminée (année de construction inconnue) — valeur neutre par défaut", tracking

    if annee < 1949:
        base = 70
        raison = "antérieur à 1949 : construction ancienne, normes parasismiques absentes, vétusté probable"
    elif annee < 1975:
        base = 55
        raison = "1949-1974 : construction d'après-guerre, normes limitées"
    elif annee < 2000:
        base = 40
        raison = "1975-2000 : construction récente, premières normes thermiques et parasismiques"
    elif annee < 2012:
        base = 30
        raison = "2001-2011 : construction moderne, RT2000/RT2005"
    else:
        base = 25
        raison = "2012 ou après : construction récente aux normes EC8 et RT2012"

    return float(base), raison, tracking


# ---------------------------------------------------------------------------
# Sous-scores F (aléa) — chaque fonction retourne (score_0_100, source_text, tracking_dict)
# ---------------------------------------------------------------------------


def _argile_subscore(
    bdnb: dict[str, Any] | None,
    georisques: dict[str, Any] | None,
    aggravation_2050: bool = False,
) -> tuple[int, str, dict[str, Any]]:
    alea = None
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else None
    if isinstance(batiment, dict):
        alea = batiment.get("alea_argile")
    if alea is None and isinstance(bdnb, dict):
        alea = bdnb.get("alea_argile")

    if alea:
        base = {"faible": 15, "moyen": 50, "fort": 82}.get(str(alea).strip().lower(), 40)
        source = f"aléa retrait-gonflement des argiles = « {alea} » (BDNB, au niveau du bâtiment)"
        tracking = {"source": "bdnb.alea_argile", "statut": SourceStatus.AVAILABLE.value, "valeur": str(alea)}
    else:
        secheresses = _count_catnat(georisques, "sécheresse") or _count_catnat(georisques, "secheresse")
        base = min(20 + secheresses * 12, 65)
        source = (
            f"aléa argile non fourni par la BDNB pour ce bâtiment ; "
            f"{secheresses} arrêté(s) CATNAT « sécheresse » recensé(s) sur la commune (indicateur de repli)"
        )
        tracking = {"source": "fallback.catnat", "statut": SourceStatus.NO_FEATURE_FOUND.value, "fallback": True, "nb_catnat_secheresse": secheresses}

    if aggravation_2050:
        base = min(base + 12, 100)
        source += " ; +12 pts pour horizon 2050 (sécheresses plus fréquentes, cf. BRGM/CCR)"

    return _clamp(base), source, tracking


def _inondation_subscore(
    georisques: dict[str, Any] | None,
    precip_delta_pct: float = 0.0,
) -> tuple[int, str, dict[str, Any]]:
    inondations = _count_catnat(georisques, "inondation")
    hazard_present = _has_hazard(georisques, "inondation")
    zones_inondables = _truthy_hazard_flag((georisques or {}).get("zones_inondables"))
    zones_en_erreur = _source_en_erreur(georisques, "zones_inondables")

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
    elif zones_en_erreur:
        source += " ; atlas zones inondables indisponible (API en erreur) — non pris en compte"

    tracking: dict[str, Any] = {
        "source": "georisques.inondation",
        "statut": SourceStatus.AVAILABLE.value,
        "nb_catnat": inondations,
        "zones_inondables": zones_inondables,
        "zones_inondables_en_erreur": zones_en_erreur,
    }
    if zones_en_erreur:
        tracking["statut"] = SourceStatus.SOURCE_ERROR.value
        tracking["erreur"] = "api_azi_404"

    return _clamp(base), source, tracking


def _mouvement_terrain_subscore(georisques: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
    cavites = _data_list(georisques, "cavites")
    mvt = _data_list(georisques, "mouvements_de_terrain")
    mvt_catnat = _count_catnat(georisques, "mouvement de terrain")
    n_cavites, n_mvt = len(cavites), len(mvt)
    base = 15 + min(n_cavites, 3) * 12 + min(n_mvt, 3) * 10 + min(mvt_catnat, 3) * 8
    source = f"{n_cavites} cavité(s), {n_mvt} mouvement(s) de terrain, {mvt_catnat} arrêté(s) CATNAT"
    tracking = {"source": "georisques.mouvement_terrain", "statut": SourceStatus.AVAILABLE.value, "nb_cavites": n_cavites, "nb_mouvements": n_mvt}
    return _clamp(base), source, tracking


def _sismique_subscore(georisques: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
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
    tracking = {"source": "georisques.zonage_sismique", "statut": SourceStatus.AVAILABLE.value if zone_int is not None else SourceStatus.NO_FEATURE_FOUND.value, "zone": zone_int}
    if zone_int is not None and zone_int in mapping:
        return mapping[zone_int], f"zone de sismicité {zone_int} (Géorisques)", tracking
    return 20, "zone de sismicité non déterminée (valeur de repli faible)", tracking


def _radon_subscore(georisques: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
    radon = _data_list(georisques, "radon")
    potentiel = radon[0].get("classe_potentiel") if radon and isinstance(radon[0], dict) else None
    try:
        potentiel_int = int(potentiel)
    except (TypeError, ValueError):
        potentiel_int = None
    tracking = {"source": "georisques.radon", "statut": SourceStatus.AVAILABLE.value if potentiel_int is not None else SourceStatus.NO_FEATURE_FOUND.value, "classe": potentiel_int}
    mapping = {1: 10, 2: 35, 3: 65}
    if potentiel_int in mapping:
        return mapping[potentiel_int], f"potentiel radon classe {potentiel_int}/3 (Géorisques)", tracking
    return 15, "potentiel radon non déterminé (valeur de repli faible)", tracking


def _feu_foret_subscore(georisques: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
    present = _has_hazard(georisques, "feu de forêt") or _has_hazard(georisques, "feu de foret")
    tracking = {"source": "georisques.feu_foret", "statut": SourceStatus.AVAILABLE.value if present else SourceStatus.NO_FEATURE_FOUND.value}
    if present:
        return 55, "aléa feu de forêt présent dans le référentiel Géorisques communal", tracking
    return 10, "aucun aléa feu de forêt recensé par Géorisques", tracking


def _canicule_subscore(climat_block: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
    jours = (climat_block or {}).get("jours_chaleur_extreme_par_an")
    tracking = {"source": "open_meteo.canicule", "statut": SourceStatus.AVAILABLE.value if jours is not None else SourceStatus.NOT_COLLECTED.value}
    if jours is None:
        return 30, "jours de chaleur extrême non disponibles (Open-Meteo)", tracking
    if jours < 3:
        base = 20
    elif jours < 6:
        base = 40
    elif jours < 10:
        base = 60
    else:
        base = 80
    return _clamp(base), f"{jours:.1f} j de chaleur extrême/an (Open-Meteo)", tracking


def _precipitation_subscore(climat_block: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
    mm = (climat_block or {}).get("precipitation_annuelle_moyenne_mm")
    tracking = {"source": "open_meteo.precipitation", "statut": SourceStatus.AVAILABLE.value if mm is not None else SourceStatus.NOT_COLLECTED.value}
    if mm is None:
        return 30, "précipitations annuelles non disponibles (Open-Meteo)", tracking
    if mm < 600:
        base = 20
    elif mm < 800:
        base = 35
    elif mm < 1000:
        base = 50
    else:
        base = 65
    return _clamp(base), f"{mm:.0f} mm/an de précipitations (Open-Meteo)", tracking


# ---------------------------------------------------------------------------
# D02 : Score de confiance (indépendant du risque)
# ---------------------------------------------------------------------------


def _compute_confidence(sources_tracking: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcule un score de confiance (0-100) basé sur :
      1. Couverture des sources (poids 0.40)
      2. Qualité des sources disponibles (poids 0.30)
      3. Absence d'erreur API (poids 0.15)
      4. Absence de repli/fallback (poids 0.10)
      5. Données de projection disponibles (poids 0.05)

    La confiance est STRICTEMENT indépendante du score de risque (D02).
    """
    total = len(sources_tracking)
    if total == 0:
        return {"score": 0, "niveau": "indetermine", "composantes": {}, "independent_of_risk": True}

    disponibles = sum(1 for s in sources_tracking if s.get("statut") == SourceStatus.AVAILABLE.value)
    en_erreur = sum(1 for s in sources_tracking if s.get("statut") == SourceStatus.SOURCE_ERROR.value)
    en_repli = sum(1 for s in sources_tracking if s.get("fallback"))
    projection_dispo = sum(1 for s in sources_tracking if s.get("source", "").startswith("open_meteo"))

    # 1. Couverture
    couverture = disponibles / max(total, 1)

    # 2. Qualité moyenne
    qualite_moyenne = 0.0
    if disponibles:
        qualite_moyenne = (
            sum(_qualite_source(s.get("source", "default")) for s in sources_tracking if s.get("statut") == SourceStatus.AVAILABLE.value)
            / disponibles
        )

    # 3. Pénalité erreur API
    penalite_erreur = max(0.0, 1.0 - en_erreur / max(total, 1))

    # 4. Pénalité repli
    penalite_repli = max(0.0, 1.0 - en_repli / max(total, 1) * 0.3)

    # 5. Bonus projection
    bonus_projection = min(1.0, projection_dispo * 0.1)

    score = _clamp(couverture * 40.0 + qualite_moyenne * 30.0 + penalite_erreur * 15.0 + penalite_repli * 10.0 + bonus_projection * 5.0)

    if score >= 80:
        niveau_conf = "elevee"
    elif score >= 60:
        niveau_conf = "bonne"
    elif score >= 40:
        niveau_conf = "moyenne"
    elif score >= 20:
        niveau_conf = "faible"
    else:
        niveau_conf = "tres faible"

    return {
        "score": score,
        "niveau": niveau_conf,
        "composantes": {
            "couverture": round(couverture, 3),
            "qualite_sources": round(qualite_moyenne, 3),
            "absence_erreurs": round(penalite_erreur, 3),
            "absence_replis": round(penalite_repli, 3),
            "bonus_projection": round(bonus_projection, 3),
        },
        "independent_of_risk": True,
        "n_sources_disponibles": disponibles,
        "n_sources_total": total,
        "n_sources_erreur": en_erreur,
    }


# ---------------------------------------------------------------------------
# D05 : Assemblage F/V par zone
# ---------------------------------------------------------------------------


def _build_zone(
    risque: int,
    alea_principal: str,
    justifications: list[str],
    f_score: float | None = None,
    v_score: float | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble une zone du contrat avec justification en puces et traçabilité."""
    puces = []
    for texte in justifications:
        texte = (texte or "").strip()
        if not texte:
            continue
        texte = texte[0].upper() + texte[1:]
        if not texte.endswith((".", "!", "?")):
            texte += "."
        puces.append(texte)

    zone: dict[str, Any] = {
        "risque": risque,
        "niveau": _niveau(risque),
        "alea_principal": alea_principal,
        "justification": "\n".join(f"• {p}" for p in puces),
        "recommandations": [],
    }
    if sources:
        zone["_sources"] = sources
    if f_score is not None:
        zone["_f_score"] = round(f_score, 1)
    if v_score is not None:
        zone["_v_score"] = round(v_score, 1)
    return zone


def _compute_zones_for_period(
    building_data: dict[str, Any],
    climat_block: dict[str, Any] | None,
    is_projection: bool,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Calcule les zones pour une période.

    D05 : chaque zone calcule F (aléa) et V (vulnérabilité) séparément,
    puis combine via moyenne géométrique : R = 100 × (F/100)^0.5 × (V/100)^0.5
    """
    georisques = building_data.get("georisques")
    bdnb = building_data.get("bdnb")

    ref_block = (building_data.get("climat_open_meteo") or {}).get("reference_2015_2024")
    precip_ref = (ref_block or {}).get("precipitation_annuelle_moyenne_mm")
    precip_now = (climat_block or {}).get("precipitation_annuelle_moyenne_mm")
    precip_delta_pct = 0.0
    if is_projection and precip_ref and precip_now:
        precip_delta_pct = max(0.0, (precip_now - precip_ref) / precip_ref * 100)

    # --- Tous les sous-scores F (aléas) ---
    argile_score, argile_src, argile_t = _argile_subscore(bdnb, georisques, aggravation_2050=is_projection)
    inondation_score, inondation_src, inondation_t = _inondation_subscore(georisques, precip_delta_pct)
    mvt_score, mvt_src, mvt_t = _mouvement_terrain_subscore(georisques)
    sismique_score, sismique_src, sismique_t = _sismique_subscore(georisques)
    radon_score, radon_src, radon_t = _radon_subscore(georisques)
    canicule_score, canicule_src, canicule_t = _canicule_subscore(climat_block)
    precip_score, precip_src, precip_t = _precipitation_subscore(climat_block)
    feu_foret_score, feu_foret_src, feu_foret_t = _feu_foret_subscore(georisques)

    # --- V (vulnérabilité du bâtiment) ---
    v_base, v_raison, v_tracking = _vulnerabilite_batiment(bdnb)

    # Toiture : bonus âge toiture (si < 1970)
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else (bdnb or {})
    if isinstance(batiment, dict):
        annee = batiment.get("annee_construction")
    else:
        annee = None
    roof_age_bonus = 10 if isinstance(annee, (int, float)) and annee < 1970 else 0
    v_toiture = min(v_base + roof_age_bonus, 100)
    if roof_age_bonus:
        v_raison_toit = v_raison + " ; toiture antérieure à 1970 : +10 pts"
    else:
        v_raison_toit = v_raison

    # Tracking des sources
    sources_tracking = [
        argile_t, inondation_t, mvt_t, sismique_t, radon_t,
        canicule_t, precip_t, feu_foret_t, v_tracking,
    ]

    zones: dict[str, dict[str, Any]] = {}

    # --- Fondations ---
    f_fondations = argile_score * 0.55 + mvt_score * 0.25 + sismique_score * 0.20
    # V fondations = V bâtiment (pas de données spécifiques fondations)
    risque_fondations = _clamp(_combine_risk(f_fondations, v_base))
    zones["fondations"] = _build_zone(
        risque_fondations,
        "Retrait-gonflement des argiles" if argile_score >= mvt_score else "Mouvement de terrain",
        [argile_src, mvt_src, sismique_src, v_raison],
        f_score=f_fondations, v_score=v_base,
        sources=[argile_t, mvt_t, sismique_t, v_tracking],
    )

    # --- Murs (4 façades) ---
    f_murs = precip_score * 0.5 + sismique_score * 0.3 + canicule_score * 0.2
    risque_murs = _clamp(_combine_risk(f_murs, v_base))
    murs_justifs = [precip_src, canicule_src, sismique_src, v_raison]
    murs_sources_list = [precip_t, canicule_t, sismique_t, v_tracking]
    for zone_name in ["murs_nord", "murs_sud", "murs_est", "murs_ouest"]:
        zones[zone_name] = _build_zone(
            risque_murs, "Exposition climatique (façade)", murs_justifs,
            f_score=f_murs, v_score=v_base, sources=murs_sources_list,
        )

    # --- Toiture ---
    f_toiture = canicule_score * 0.45 + precip_score * 0.15 + feu_foret_score * 0.40
    risque_toiture = _clamp(_combine_risk(f_toiture, v_toiture))
    toiture_justifs = [canicule_src, precip_src, feu_foret_src, v_raison_toit]
    toiture_sources = [canicule_t, precip_t, feu_foret_t, v_tracking]
    zones["toiture"] = _build_zone(
        risque_toiture,
        "Feu de forêt" if feu_foret_score >= canicule_score else "Canicule / stress thermique",
        toiture_justifs,
        f_score=f_toiture, v_score=v_toiture, sources=toiture_sources,
    )

    # --- Sous-sol ---
    f_sous_sol = inondation_score * 0.8 + radon_score * 0.2
    # V sous-sol = V bâtiment (pas de données spécifiques sous-sol)
    risque_sous_sol = _clamp(_combine_risk(f_sous_sol, v_base))
    zones["sous_sol"] = _build_zone(
        risque_sous_sol,
        "Inondation / remontée de nappe",
        [inondation_src, radon_src, v_raison],
        f_score=f_sous_sol, v_score=v_base,
        sources=[inondation_t, radon_t, v_tracking],
    )

    for zone_name in ZONE_NAMES:
        z = zones[zone_name]
        logger.info("  [%s] risque=%d (%s) | F=%.1f V=%.1f", zone_name, z["risque"], z["niveau"], z.get("_f_score", 0), z.get("_v_score", 0))

    return zones, sources_tracking


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
    """Point d'entrée du scoring_agent.

    Retourne un dict avec :
      - score_global : int (0-100)
      - zones : dict[str, dict] (7 zones, chaque zone contient risque/niveau/...)
      - projection_2050 : {score_global, zones}
      - confidence : dict (D02, score de confiance 0-100)
      - sources : list[dict] (D04, traçabilité des sources)

    Compatible avec tous les consommateurs existants :
      - diagnostic_builder lit score_global / zones / projection_2050
      - interpretation_agent lit score_global / zones / projection_2050
      - zone_scoring lit score_global / zones
      - property_id lit score_global / projection_2050
    """
    logger.info("scoring_agent -- calcul des scores F/V (période courante + projection 2050)")

    climat = building_data.get("climat_open_meteo") or {}
    reference = climat.get("reference_2015_2024")
    projection = climat.get("projection_2041_2050")

    logger.info("période référence (2025) :")
    zones_2025, sources_2025 = _compute_zones_for_period(building_data, reference, is_projection=False)
    score_2025 = _score_global(zones_2025)
    logger.info("  -> score_global = %d", score_2025)

    logger.info("période projection (2050) :")
    zones_2050, sources_2050 = _compute_zones_for_period(building_data, projection or reference, is_projection=True)
    score_2050 = _score_global(zones_2050)
    logger.info("  -> score_global = %d", score_2050)

    confidence = _compute_confidence(sources_2025)
    logger.info("  -> confiance = %d (%s)", confidence["score"], confidence["niveau"])

    return {
        "score_global": score_2025,
        "zones": zones_2025,
        "projection_2050": {
            "score_global": score_2050,
            "zones": zones_2050,
        },
        "confidence": confidence,
        "sources": sources_2025,
    }
