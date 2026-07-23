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
    """Genere un JSON d'erreur si le graphe echoue."""
    import logging
    from datetime import datetime, timezone
    logger.error(f"Fallback error: {error_msg}")
    return {
        "session_id": session_id,
        "adresse": client_form.get("adresse", ""),
        "date_analyse": datetime.now(timezone.utc).isoformat(),
        "erreur": error_msg,
        "recommandations": {
            "zones": {},
            "projection_2050": {},
            "synthese_financiere": {"cout_brut_total": "0 EUR", "aides_mobilisables": "0 EUR", "reste_a_charge_net": "0 EUR"},
            "scores_par_alea": {},
            "nb_recommandations": 0,
        },
        "analyse_risques": {
            "score": {"global": 0, "weights": {}, "perils": {}},
            "scores_par_alea": {},
            "profil_bien": {"disponible": False},
        },
        "resume": {
            "score_global": 0,
            "niveau_risque": "non_evalue",
            "nb_recommandations": 0,
            "cout_total_travaux": "0 EUR",
            "aides_mobilisables": "0 EUR",
            "reste_a_charge_net": "0 EUR",
        },
        "_performance": {"mode": "langgraph_error", "error": error_msg},
    }
