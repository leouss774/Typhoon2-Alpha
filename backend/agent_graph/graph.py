"""Construction du graphe principal LangGraph pour Typhoon.

Assemble les 3 noeuds du pipeline dans un StateGraph lineaire :
  collect_georisques → generate_recommandations → assemble_output → END
"""

from __future__ import annotations

import logging
import sys
import os

# Ajouter le backend au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END

from agent_graph.state import TyphoonState
from agent_graph.nodes.collect_georisques import collect_georisques_node
from agent_graph.nodes.generate_recommandations import generate_recommandations_node
from agent_graph.nodes.assemble_output import assemble_output_node

logger = logging.getLogger(__name__)

# Cache de l'application compilee
_app = None


def build_typhoon_graph() -> StateGraph:
    """Construit le StateGraph Typhoon avec ses 3 noeuds."""
    builder = StateGraph(TyphoonState)

    # ── Noeuds ──────────────────────────────────
    builder.add_node("collect_georisques", collect_georisques_node)
    builder.add_node("generate_recommandations", generate_recommandations_node)
    builder.add_node("assemble_output", assemble_output_node)

    # ── Point d'entree ─────────────────────────
    builder.set_entry_point("collect_georisques")

    # ── Aretes sequentielles ────────────────────
    builder.add_edge("collect_georisques", "generate_recommandations")
    builder.add_edge("generate_recommandations", "assemble_output")
    builder.add_edge("assemble_output", END)

    return builder


def get_typhoon_app():
    """Retourne l'application LangGraph compilee (avec cache)."""
    global _app
    if _app is None:
        graph = build_typhoon_graph()
        _app = graph.compile()
        logger.info("Graphe LangGraph Typhoon compile avec succes")
    return _app


def run_typhoon_graph(
    session_id: str,
    client_form: dict,
    raw_data: dict | None = None,
) -> dict:
    """Point d'entree principal : execute le graphe LangGraph complet.

    Args:
        session_id: Identifiant de session
        client_form: Donnees du formulaire client
        raw_data: Donnees brutes supplementaires (optionnel)

    Returns:
        JSON final complet au format assessment_complet.json
    """
    app = get_typhoon_app()

    initial_state = TyphoonState(
        session_id=session_id,
        client_form=client_form,
        raw_data=raw_data or {},
    )

    try:
        # Execution du graphe
        result = app.invoke(initial_state)

        # Le resultat est un dict avec tous les champs du state
        final_json = result.get("final_json")

        if final_json is None:
            logger.error("Le graphe n'a pas produit de JSON final")
            return _fallback_error(session_id, client_form, "Le graphe n'a pas produit de JSON final")

        logger.info(f"Graphe execute avec succes - score: {final_json.get('analyse_risques', {}).get('score', {}).get('global', '?')}")
        return final_json

    except Exception as e:
        logger.error(f"Erreur lors de l'execution du graphe : {e}")
        return _fallback_error(session_id, client_form, str(e))


def _fallback_error(session_id: str, client_form: dict, error_msg: str) -> dict:
    """Genere un JSON d'erreur si le graphe echoue.

    GARANTI de produire des zones par defaut (non vides) pour que le frontend
    ne recoive jamais "recommandations.zones = {}".
    """
    from datetime import datetime, timezone
    logger.error(f"Fallback error: {error_msg}")

    adresse = client_form.get("adresse", "") if isinstance(client_form, dict) else ""

    # Zones par defaut (non vides) pour eviter l'erreur frontend "zones manquantes"
    zones_default = {}
    for name, score in [("fondations", 15), ("murs_nord", 10), ("toiture", 15), ("sous_sol", 15)]:
        level = "critique" if score >= 70 else "eleve" if score >= 55 else "modere" if score >= 35 else "faible"
        zones_default[name] = {
            "risque": score,
            "niveau": level,
            "alea_principal": "Non determine (API indisponible)",
            "recommandations": [],
            "justification": "Les donnees API etaient indisponibles au moment de l'analyse. Reessayez plus tard.",
            "test_vulnerabilite": {
                "verdict": "Vulnerabilite non evaluee - API indisponible",
                "explication": "Les API externes (Georisques, IGN, OSM) n'ont pas repondu.",
            },
        }

    score_global = round(15 * 0.3 + 15 * 0.25 + 15 * 0.25 + 10 * 0.2)  # = 13, aligné avec _fallback_recommandations

    return {
        "session_id": session_id,
        "adresse": adresse,
        "coordonnees": {"latitude": 0, "longitude": 0},
        "date_analyse": datetime.now(timezone.utc).isoformat(),
        "erreur": error_msg,

        "formulaire_client": {
            "adresse": adresse,
            "type_bien": client_form.get("type_bien", "") if isinstance(client_form, dict) else "",
            "surface": client_form.get("surface", 0) if isinstance(client_form, dict) else 0,
            "nb_etages": client_form.get("nb_etages", 1) if isinstance(client_form, dict) else 1,
            "annee_construction": client_form.get("annee_construction", 2000) if isinstance(client_form, dict) else 2000,
            "type_structure": client_form.get("type_structure", "") if isinstance(client_form, dict) else "",
            "type_toiture": client_form.get("type_toiture", "") if isinstance(client_form, dict) else "",
            "presence_sous_sol": client_form.get("presence_sous_sol", False) if isinstance(client_form, dict) else False,
            "presence_cave": client_form.get("presence_cave", False) if isinstance(client_form, dict) else False,
        },

        "analyse_risques": {
            "score": {
                "global": score_global,
                "weights": {"infiltration": 0.3, "thermique": 0.25, "incendie_electrique": 0.25, "aleas_naturels": 0.2},
                "perils": {
                    "infiltration": {"score": 15},
                    "rga": {"score": 15},
                    "thermique": {"score": 15},
                },
            },
            "scores_par_alea": {"inondation": 15, "rga": 15, "canicule": 15, "tempete": 12},
            "profil_bien": {"disponible": False},
        },

        "recommandations": {
            "zones": zones_default,
            "projection_2050": {
                "score_global": score_global,
                "scenario_climatique": "CMIP6 - donnees insuffisantes",
                "zones": {
                    n: {
                        "risque_projete": min(100, round(z["risque"] * 1.3)),
                        "evolution": f"+{min(100, round(z['risque'] * 1.3)) - z['risque']} points (estimation)"
                    }
                    for n, z in zones_default.items()
                }
            },
            "synthese_financiere": {"cout_brut_total": "0 EUR", "aides_mobilisables": "0 EUR", "reste_a_charge_net": "0 EUR"},
            "scores_par_alea": {"inondation": 15, "rga": 15, "canicule": 15, "tempete": 12},
            "nb_recommandations": 0,
        },

        "resume": {
            "score_global": score_global,
            "niveau_risque": "faible",
            "nb_recommandations": 0,
            "cout_total_travaux": "0 EUR",
            "aides_mobilisables": "0 EUR",
            "reste_a_charge_net": "0 EUR",
        },

        "donnees_api": {
            "code_insee": "",
            "georisques": {},
            "climat": {},
        },

        "_performance": {"mode": "langgraph_error", "error": error_msg},
    }
