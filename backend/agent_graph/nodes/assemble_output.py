"""Noeud 3 : Assemble le JSON final pour le jumeau numerique.

Prend les recommandations par zone generees a l'etape precedente
et construit le JSON final au format assessment_complet.json,
pret a etre consomme par le frontend (Dashboard + JumeauNumerique).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agent_graph.state import TyphoonState

logger = logging.getLogger(__name__)


def assemble_output_node(state: TyphoonState) -> dict:
    """Assemble le JSON final pour le jumeau numerique.

    Entree :
        state.client_form : donnees du formulaire
        state.georisques_data : donnees collectees
        state.zone_recommandations : recommandations par zone

    Sortie :
        state.final_json : JSON complet format assessment_complet.json
        Garanti de toujours produire une structure valide meme en cas de donnees partielles.
    """
    form = state.client_form or {}
    georisques = state.georisques_data or {}
    if not isinstance(georisques, dict):
        georisques = {}
    recommandations = state.zone_recommandations or {}
    if not isinstance(recommandations, dict):
        recommandations = {}

    zones = recommandations.get("zones", {})
    if not isinstance(zones, dict):
        zones = {}
    projection = recommandations.get("projection_2050", {})
    if not isinstance(projection, dict):
        projection = {}
    synthese_fin = recommandations.get("synthese_financiere", {})
    if not isinstance(synthese_fin, dict):
        synthese_fin = {}
    scores_alea = recommandations.get("scores_par_alea", {})
    if not isinstance(scores_alea, dict):
        scores_alea = {}
    score_global = _to_int(recommandations.get("score_global"), 50)
    nb_recos = _to_int(recommandations.get("nb_recommandations"), 0)

    coord = georisques.get("coordonnees", {})
    if not isinstance(coord, dict):
        coord = {}
    lat = _to_float(coord.get("latitude"), 0)
    lon = _to_float(coord.get("longitude"), 0)
    code_insee = str(georisques.get("code_insee", "") or "")
    altitude = georisques.get("altitude", {})
    if not isinstance(altitude, dict):
        altitude = {}

    # Calcul du niveau de risque global
    niveau_global = "critique" if score_global >= 70 else "eleve" if score_global >= 55 else "modere" if score_global >= 35 else "faible"

    final_json = {
        "session_id": state.session_id,
        "adresse": form.get("adresse", "") if isinstance(form, dict) else "",
        "coordonnees": {"latitude": lat, "longitude": lon},
        "date_analyse": datetime.now(timezone.utc).isoformat(),

        "formulaire_client": {
            "adresse": form.get("adresse", "") if isinstance(form, dict) else "",
            "type_bien": form.get("type_bien", "") if isinstance(form, dict) else "",
            "surface": form.get("surface", 0) if isinstance(form, dict) else 0,
            "nb_etages": form.get("nb_etages", 1) if isinstance(form, dict) else 1,
            "annee_construction": form.get("annee_construction", 2000) if isinstance(form, dict) else 2000,
            "type_structure": form.get("type_structure", "") if isinstance(form, dict) else "",
            "type_toiture": form.get("type_toiture", "") if isinstance(form, dict) else "",
            "presence_sous_sol": form.get("presence_sous_sol", False) if isinstance(form, dict) else False,
            "presence_cave": form.get("presence_cave", False) if isinstance(form, dict) else False,
        },

        "analyse_risques": {
            "score": {
                "global": score_global,
                "weights": {"infiltration": 0.3, "thermique": 0.25, "incendie_electrique": 0.25, "aleas_naturels": 0.2},
                "perils": {
                    "infiltration": {"score": scores_alea.get("inondation", 0)},
                    "rga": {"score": scores_alea.get("rga", 0)},
                    "thermique": {"score": scores_alea.get("canicule", 0)},
                },
            },
            "scores_par_alea": scores_alea,
            "profil_bien": _build_profil_bien(form, georisques),
        },

        "recommandations": {
            "zones": zones,
            "projection_2050": projection,
            "synthese_financiere": synthese_fin,
            "scores_par_alea": scores_alea,
            "nb_recommandations": nb_recos,
        },

        "resume": {
            "score_global": score_global,
            "niveau_risque": niveau_global,
            "nb_recommandations": nb_recos,
            "cout_total_travaux": synthese_fin.get("cout_brut_total", "0 EUR"),
            "aides_mobilisables": synthese_fin.get("aides_mobilisables", "0 EUR"),
            "reste_a_charge_net": synthese_fin.get("reste_a_charge_net", "0 EUR"),
        },

        "donnees_api": {
            "code_insee": code_insee,
            "georisques": georisques.get("georisques", {}) if isinstance(georisques.get("georisques"), dict) else {},
            "climat": {},
        },

        "_performance": {
            "mode": "langgraph_v2",
            "api_pipeline": bool(georisques.get("brut")),
        },
    }

    # Si la collecte Georisques a echoue, on leve un flag dans _performance
    if state.collect_error:
        final_json["_performance"]["collect_error"] = state.collect_error
        logger.warning(f"Collecte Georisques partielle : {state.collect_error}")

    logger.info(f"JSON final assemble - score global: {score_global}/100, {nb_recos} recommandations")

    return {
        "final_json": final_json,
        "next_node": "__end__",
    }


def _to_int(value: Any, default: int = 0) -> int:
    """Convertit en int de facon securisee."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    """Convertit en float de facon securisee."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_profil_bien(form: dict, georisques: dict) -> dict:
    """Construit le profil du bien a partir du formulaire et des donnees API."""
    if not isinstance(form, dict):
        form = {}
    if not isinstance(georisques, dict):
        georisques = {}

    # Extraction securisee de l'altitude
    altitude = georisques.get("altitude", {})
    altitude_m = None
    if isinstance(altitude, dict):
        elevations = altitude.get("elevations", [])
        if isinstance(elevations, list) and len(elevations) > 0:
            first = elevations[0]
            if isinstance(first, dict):
                altitude_m = first.get("z")

    return {
        "disponible": True,
        "source": "formulaire_client",
        "adresse": form.get("adresse", ""),
        "code_insee": str(georisques.get("code_insee", "") or ""),
        "type_bien": form.get("type_bien", "Maison individuelle"),
        "surface_m2": form.get("surface", 100),
        "nb_etages": form.get("nb_etages", 1),
        "annee_construction": form.get("annee_construction", 2000),
        "annee_renovation": form.get("annee_renovation"),
        "type_structure": form.get("type_structure", ""),
        "etat_structure": form.get("etat_structure", ""),
        "fissures": form.get("fissures", ""),
        "affaissement": form.get("affaissement", ""),
        "type_toiture": form.get("type_toiture", ""),
        "age_toiture": form.get("age_toiture"),
        "etat_toiture": form.get("etat_toiture", ""),
        "isolation_toiture": form.get("isolation_toiture", ""),
        "isolation_murs": form.get("isolation_murs", ""),
        "infiltrations": form.get("infiltrations", ""),
        "presence_sous_sol": form.get("presence_sous_sol", False),
        "presence_cave": form.get("presence_cave", False),
        "occupation": form.get("occupation", ""),
        "installation_electrique_annee": form.get("installation_electrique_annee"),
        "altitude_m": altitude_m,
    }
