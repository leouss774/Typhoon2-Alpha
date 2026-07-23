"""Construction du graphe principal LangGraph pour Typhoon.

Assemble tous les nœuds et arêtes dans un StateGraph cohérent
qui orchestre le flux complet : score → analyse → recommandations → rapport.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from backend.agent_graph.state import TyphoonState
from backend.agent_graph.nodes.calculate_score import calculate_score_node
from backend.agent_graph.nodes.analyste_risque import analyste_risque_node
from backend.agent_graph.nodes.recommandation import recommandation_node
from backend.agent_graph.nodes.generate_report import generate_report_node
from backend.agent_graph.nodes.validate_rapport import validate_rapport_node
from backend.agent_graph.edges.router import route_after_validation

# Cache de l'application compilée
_app = None


def build_typhoon_graph() -> StateGraph:
    """Construit le StateGraph Typhoon avec tous ses nœuds et arêtes."""
    builder = StateGraph(TyphoonState)

    # ── Nœuds ──────────────────────────────────
    builder.add_node("calculate_score", calculate_score_node)
    builder.add_node("analyste_risque", analyste_risque_node)
    builder.add_node("recommandation", recommandation_node)
    builder.add_node("generate_report", generate_report_node)
    builder.add_node("validate_rapport", validate_rapport_node)

    # ── Point d'entrée ─────────────────────────
    builder.set_entry_point("calculate_score")

    # ── Arêtes normales (séquentielles) ────────
    builder.add_edge("calculate_score", "analyste_risque")
    builder.add_edge("analyste_risque", "recommandation")
    builder.add_edge("recommandation", "generate_report")
    builder.add_edge("generate_report", "validate_rapport")

    # ── Arête conditionnelle (validation) ──────
    builder.add_conditional_edges(
        "validate_rapport",
        route_after_validation,
        {
            "analyste_risque": "analyste_risque",  # boucle de correction
            "__end__": END,                         # terminé
        },
    )

    return builder


def get_typhoon_app():
    """Retourne l'application LangGraph compilée (avec cache)."""
    global _app
    if _app is None:
        graph = build_typhoon_graph()
        _app = graph.compile()
    return _app
