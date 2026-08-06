"""
Extensions industrielles du scoring de risque — détection du type de
bâtiment, sous-scores technologiques (ICPE, SSP, PPRT) et zones spécifiques
aux sites industriels.

Ces extensions réutilisent les données ALREADY collectées par le
collector_agent (georisques.icpe, georisques.ssp, georisques.pprt,
georisques.ppr, georisques.risques_commune) — aucune nouvelle source
externe n'est requise pour le niveau 1 (score automatique).
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.scoring.risk_model import (
    SourceStatus,
    _clamp,
    _combine_risk,
    _data_list,
    _has_hazard,
    _niveau,
    _source_en_erreur,
)

logger = get_logger(__name__)

# Codes d'usage BDNB considérés comme industriels/artisanaux
CODE_USAGE_INDUSTRIEL = {
    "I": "Industriel",
    "U": "Artisanat / industrie",
}

# Codes NAF/APE (sections) considérés comme industriels
NAF_INDUSTRIEL_PREFIXES = ("10", "11", "12", "13", "14", "15", "16", "17",
                           "18", "19", "20", "21", "22", "23", "24", "25",
                           "26", "27", "28", "29", "30", "31", "32", "33")


# ---------------------------------------------------------------------------
# Détection du type de bâtiment
# ---------------------------------------------------------------------------

def detecter_type_batiment(building_data: dict[str, Any]) -> dict[str, Any]:
    """Détecte si le bien est une usine / bâtiment industriel.

    Priorité :
      1. BDNB — code usage (I/U) au niveau du bâtiment
      2. BDNB — libellé usage contenant des mots-clés industriels
      3. SIRENE (non collecté actuellement, repli : indéterminé)

    Retourne un dict : {type, est_industriel, source, raison}
    """
    bdnb = building_data.get("bdnb")
    batiment = None
    if isinstance(bdnb, dict):
        batiment = bdnb.get("batiment") if isinstance(bdnb.get("batiment"), dict) else bdnb

    # 1. Code d'usage BDNB
    if isinstance(batiment, dict):
        code_usage = batiment.get("code_usage") or batiment.get("code_usage_principal")
        if code_usage:
            code = str(code_usage).strip().upper()
            if code in CODE_USAGE_INDUSTRIEL:
                return {
                    "type": "industriel",
                    "est_industriel": True,
                    "source": "bdnb.code_usage",
                    "raison": f"Code d'usage BDNB « {code} » = {CODE_USAGE_INDUSTRIEL[code]}",
                }

        # 2. Libellé d'usage
        libelle = batiment.get("libelle_usage") or batiment.get("libelle_usage_principal") or ""
        if isinstance(libelle, str):
            libelle_lower = libelle.lower()
            mots_industriels = [
                "usine", "industri", "atelier", "entrepôt", "entrepot",
                "fabrique", "manufacture", "hangar", "garage", "remise",
                "hangar", "mécanique", "mecanique", "fonderie", "chimie",
            ]
            if any(m in libelle_lower for m in mots_industriels):
                return {
                    "type": "industriel",
                    "est_industriel": True,
                    "source": "bdnb.libelle_usage",
                    "raison": f"Libellé d'usage BDNB « {libelle} » contient un terme industriel",
                }

    return {
        "type": None,
        "est_industriel": False,
        "source": None,
        "raison": "Aucune indication d'usage industriel — traité comme bâtiment standard",
    }


# ---------------------------------------------------------------------------
# Sous-scores F (aléas industriels/technologiques)
# ---------------------------------------------------------------------------

def _icpe_subscore(georisques: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
    """Score basé sur les installations classées (ICPE) proches.

    Sources : georisques.icpe (installations_classees)
    - 0 installation      → 10 (faible)
    - 1-2 installations   → 30
    - 3-9 installations   → 50
    - 10+ installations   → 65
    - SEVESO présent      → 85
    """
    if _source_en_erreur(georisques, "icpe"):
        return 20, "source ICPE en erreur — valeur de repli faible", {
            "source": "georisques.icpe",
            "statut": SourceStatus.SOURCE_ERROR.value,
        }

    icpe_list = _data_list(georisques, "icpe")
    n = len(icpe_list)
    seveso = any(
        (
            "seveso" in str(e.get("statut_seveso", "") or "").lower()
            or "seveso" in str(e.get("lib_statut_seveso", "") or "").lower()
        )
        for e in icpe_list
        if isinstance(e, dict)
    )
    seuil_haut = any(
        "seuil haut" in str(e.get("lib_statut_seveso", "") or "").lower()
        for e in icpe_list
        if isinstance(e, dict)
    )

    if seveso or seuil_haut:
        base = 85
    elif n >= 10:
        base = 65
    elif n >= 3:
        base = 50
    elif n >= 1:
        base = 30
    else:
        base = 10

    source = f"{n} installation(s) classée(s) recensée(s)"
    if seveso:
        source += " — présence de site SEVESO"
    elif seuil_haut:
        source += " — présence de site SEVESO seuil haut"

    tracking = {
        "source": "georisques.icpe",
        "statut": SourceStatus.AVAILABLE.value,
        "nb_icpe": n,
        "seveso": seveso or seuil_haut,
    }
    return _clamp(base), source, tracking


def _ssp_subscore(georisques: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
    """Score basé sur les sites et sols pollués (BASOL/BASIAS/SIS).

    Sources : georisques.ssp
    - 0 site        → 10 (faible)
    - 1-2 sites     → 40
    - 3-4 sites     → 55
    - 5+ sites      → 75
    """
    if _source_en_erreur(georisques, "ssp"):
        return 20, "source SSP en erreur — valeur de repli faible", {
            "source": "georisques.ssp",
            "statut": SourceStatus.SOURCE_ERROR.value,
        }

    ssp_list = _data_list(georisques, "ssp")
    n = len(ssp_list)
    if n >= 5:
        base = 75
    elif n >= 3:
        base = 55
    elif n >= 1:
        base = 40
    else:
        base = 10

    source = f"{n} site(s) et sol(s) pollué(s) recensé(s)"
    tracking = {
        "source": "georisques.ssp",
        "statut": SourceStatus.AVAILABLE.value,
        "nb_ssp": n,
    }
    return _clamp(base), source, tracking


def _pprt_subscore(georisques: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
    """Score basé sur les Plans de Prévention des Risques Technologiques (PPRT).

    Sources : georisques.pprt
    - Aucun PPRT        → 5 (très faible)
    - PPRT prescrit     → 50
    - PPRT approuvé     → 70
    """
    if _source_en_erreur(georisques, "pprt"):
        return 20, "source PPRT en erreur — valeur de repli faible", {
            "source": "georisques.pprt",
            "statut": SourceStatus.SOURCE_ERROR.value,
        }

    pprt_list = _data_list(georisques, "pprt")
    n = len(pprt_list)
    approuve = any(
        "approuv" in str(e.get("libelle_statut", "") or "").lower()
        for e in pprt_list
        if isinstance(e, dict)
    )

    if approuve:
        base = 70
    elif n >= 1:
        base = 50
    else:
        base = 5

    source = f"{n} PPRT recensé(s)"
    if approuve:
        source += " — au moins un PPRT approuvé"

    tracking = {
        "source": "georisques.pprt",
        "statut": SourceStatus.AVAILABLE.value,
        "nb_pprt": n,
        "approuve": approuve,
    }
    return _clamp(base), source, tracking


def _risque_technologique_subscore(georisques: dict[str, Any] | None) -> tuple[int, str, dict[str, Any]]:
    """Score composite des risques technologiques (TMD, canalisations, nucléaire).

    Sources : georisques.risques_commune (GASPAR)
    """
    if _source_en_erreur(georisques, "risques_commune"):
        return 20, "source risques_commune en erreur — valeur de repli faible", {
            "source": "georisques.risques_commune",
            "statut": SourceStatus.SOURCE_ERROR.value,
        }

    tmd = (
        _has_hazard(georisques, "transport de matières dangereuses")
        or _has_hazard(georisques, "matières dangereuses")
        or _has_hazard(georisques, "canalisation")
    )
    nucleaire = (
        _has_hazard(georisques, "nucléaire")
        or _has_hazard(georisques, "nucleaire")
    )
    pollution = (
        _has_hazard(georisques, "industriel")
        or _has_hazard(georisques, "pollution")
    )

    base = 5
    raisons = []
    if tmd:
        base += 30
        raisons.append("TMD / canalisations de matières dangereuses")
    if nucleaire:
        base += 35
        raisons.append("risque nucléaire")
    if pollution:
        base += 20
        raisons.append("risque de pollution industrielle")

    source = "; ".join(raisons) if raisons else "aucun risque technologique recensé"
    tracking = {
        "source": "georisques.risques_commune",
        "statut": SourceStatus.AVAILABLE.value,
        "tmd": tmd,
        "nucleaire": nucleaire,
        "pollution": pollution,
    }
    return _clamp(base), source, tracking


def compute_industry_scores(building_data: dict[str, Any]) -> dict[str, Any]:
    """Point d'entrée : calcule les scores technologiques pour un bâtiment.

    Retourne un dict avec :
      - est_industriel : bool
      - type_batiment : dict (détection)
      - risques_technologiques : dict des sous-scores (icpe, ssp, pprt, risque_techno)
      - zones_industrielles : dict des zones spécifiques usines
      - score_industriel_global : int (0-100)
    """
    georisques = building_data.get("georisques")
    detection = detecter_type_batiment(building_data)

    # Toujours calculer les scores technologiques (même pour un usage résidentiel,
    # une usine voisine impacte le risque du quartier)
    icpe_score, icpe_src, icpe_t = _icpe_subscore(georisques)
    ssp_score, ssp_src, ssp_t = _ssp_subscore(georisques)
    pprt_score, pprt_src, pprt_t = _pprt_subscore(georisques)
    techno_score, techno_src, techno_t = _risque_technologique_subscore(georisques)

    risques_technologiques = {
        "icpe": {
            "label": "Installations classées (ICPE)",
            "risque": icpe_score,
            "niveau": _niveau(icpe_score),
            "justification": icpe_src,
        },
        "ssp": {
            "label": "Sites et sols pollués",
            "risque": ssp_score,
            "niveau": _niveau(ssp_score),
            "justification": ssp_src,
        },
        "pprt": {
            "label": "Risques technologiques (PPRT)",
            "risque": pprt_score,
            "niveau": _niveau(pprt_score),
            "justification": pprt_src,
        },
        "risque_technologique": {
            "label": "Risques technologiques (TMD, nucléaire)",
            "risque": techno_score,
            "niveau": _niveau(techno_score),
            "justification": techno_src,
        },
    }

    # Score global technologique = max des sous-scores (le pire domine)
    score_techno_global = max(icpe_score, ssp_score, pprt_score, techno_score)

    # Zones industrielles spécifiques — seulement si le bâtiment est industriel
    zones_industrielles = {}
    if detection["est_industriel"]:
        v_base = 50.0  # vulnérabilité industrielle par défaut, sera surchargée par l'appelant
        bdnb = building_data.get("bdnb")
        batiment = None
        if isinstance(bdnb, dict):
            batiment = bdnb.get("batiment") if isinstance(bdnb.get("batiment"), dict) else bdnb
        if isinstance(batiment, dict):
            annee = batiment.get("annee_construction")
            if isinstance(annee, (int, float)):
                if annee < 1970:
                    v_base = 70
                elif annee < 2000:
                    v_base = 55
                else:
                    v_base = 40

        zones_industrielles = {
            "charpente": {
                "risque": _clamp(_combine_risk(techno_score * 0.4 + pprt_score * 0.3 + icpe_score * 0.3, v_base)),
                "niveau": "",
                "alea_principal": "Risques technologiques",
                "raison": "Structure porteuse industrielle (charpente, grandes portées)",
            },
            "equipements": {
                "risque": _clamp(_combine_risk(techno_score * 0.5 + ssp_score * 0.3 + icpe_score * 0.2, v_base)),
                "niveau": "",
                "alea_principal": "Équipements de production",
                "raison": "Équipements de production sensibles aux aléas",
            },
            "stockage": {
                "risque": _clamp(_combine_risk(icpe_score * 0.5 + ssp_score * 0.3 + techno_score * 0.2, v_base)),
                "niveau": "",
                "alea_principal": "Stockage de matières",
                "raison": "Zones de stockage (matières premières, produits finis)",
            },
            "cuves_reservoirs": {
                "risque": _clamp(_combine_risk(icpe_score * 0.6 + ssp_score * 0.4, v_base)),
                "niveau": "",
                "alea_principal": "Cuves et réservoirs",
                "raison": "Cuves et réservoirs (liquides, gaz, produits chimiques)",
            },
        }
        # Calculer les niveaux
        for zone_key, zone_data in zones_industrielles.items():
            zone_data["niveau"] = _niveau(zone_data["risque"])

    return {
        "est_industriel": detection["est_industriel"],
        "type_batiment": detection,
        "risques_technologiques": risques_technologiques,
        "zones_industrielles": zones_industrielles,
        "score_technologique_global": score_techno_global,
        "sources_tracking": [icpe_t, ssp_t, pprt_t, techno_t],
    }