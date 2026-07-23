"""Noeud 2 : Generation des recommandations par zone.

Merge les donnees Georisques avec le formulaire client,
puis appelle generate_zone_recommendations() pour produire
les recommandations par zone (fondations, toiture, sous-sol, murs).

Note : le sys.path est deja configure par graph.py et orchestrator.py
"""

from __future__ import annotations

import logging

from agent_graph.state import TyphoonState

logger = logging.getLogger(__name__)

try:
    from api.recommandations_generator import generate_zone_recommendations
    HAS_GENERATOR = True
except ImportError:
    HAS_GENERATOR = False
    logger.warning("Module recommandations_generator non disponible")


def generate_recommandations_node(state: TyphoonState) -> dict:
    """Genere les recommandations par zone.

    Entree :
        state.client_form
        state.georisques_data

    Sortie :
        state.zone_recommandations
    """
    georisques = state.georisques_data or {}
    form = state.client_form

    # Construction de api_data a partir des donnees collectees
    brut = georisques.get("brut", {})
    if not isinstance(brut, dict):
        brut = {}

    osm_proximite = georisques.get("osm_proximite", {})
    if not isinstance(osm_proximite, dict):
        osm_proximite = {}

    api_data = {
        **brut,
        "georisques": georisques.get("georisques", {}) if isinstance(georisques.get("georisques"), dict) else {},
        "altitude": georisques.get("altitude", {}) if isinstance(georisques.get("altitude"), dict) else {},
        "coordonnees": georisques.get("coordonnees", {}) if isinstance(georisques.get("coordonnees"), dict) else {},
        "distance_eau": osm_proximite.get("cours_eau", {}).get("distance_m") if isinstance(osm_proximite.get("cours_eau"), dict) else None,
        "distance_foret": osm_proximite.get("foret", {}).get("distance_m") if isinstance(osm_proximite.get("foret"), dict) else None,
    }

    if HAS_GENERATOR:
        try:
            recommandations = generate_zone_recommendations(api_data=api_data, form_data=form)
            if not isinstance(recommandations, dict):
                logger.error("generate_zone_recommendations n'a pas retourne un dict")
                recommandations = _fallback_recommandations()
            else:
                logger.info(f"Recommandations generees : {recommandations.get('nb_recommandations', 0)} travaux")
        except Exception as e:
            logger.error(f"Erreur dans generate_zone_recommendations : {e}")
            recommandations = _fallback_recommandations()
    else:
        # Fallback minimal
        recommandations = _fallback_recommandations()
        logger.warning("Utilisation du fallback pour les recommandations")

    return {
        "zone_recommandations": recommandations,
        "next_node": "assemble_output",
    }


def _fallback_recommandations() -> dict:
    """Fallback minimal si le generateur de recommandations n'est pas disponible."""
    zones = {}
    for name, score in [("fondations", 15), ("murs_nord", 10), ("toiture", 15), ("sous_sol", 15)]:
        level = "critique" if score >= 70 else "eleve" if score >= 55 else "modere" if score >= 35 else "faible"
        zones[name] = {
            "risque": score,
            "niveau": level,
            "alea_principal": "Standard",
            "recommandations": [],
            "justification": "Donnees insuffisantes.",
            "test_vulnerabilite": {
                "verdict": "Vulnerabilite faible - aucune action urgente requise",
                "explication": "Donnees API insuffisantes pour un diagnostic detaille.",
            },
        }

    global_score = round(15 * 0.3 + 15 * 0.25 + 15 * 0.25 + 10 * 0.2)

    return {
        "zones": zones,
        "projection_2050": {
            "score_global": min(100, round(global_score * 1.4)),
            "scenario_climatique": "CMIP6 - defaut",
            "zones": {
                n: {
                    "risque_projete": min(100, round(z["risque"] * 1.3)),
                    "evolution": f"+{min(100, round(z['risque'] * 1.3)) - z['risque']} points"
                }
                for n, z in zones.items()
            }
        },
        "synthese_financiere": {
            "cout_brut_total": "0 EUR",
            "aides_mobilisables": "0 EUR",
            "reste_a_charge_net": "0 EUR"
        },
        "scores_par_alea": {"inondation": 15, "rga": 15, "canicule": 15, "tempete": 12},
        "score_global": global_score,
        "nb_recommandations": 0,
    }
