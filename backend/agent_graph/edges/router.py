"""Arêtes conditionnelles pour le routage entre nœuds du graphe.

Définit les fonctions de routage utilisées par les conditional_edges
dans la construction du StateGraph.
"""

from __future__ import annotations

from backend.agent_graph.state import TyphoonState


def route_after_validation(state: TyphoonState) -> str:
    """Route après validation du rapport.

    Si la validation échoue, on reboucle vers l'analyse pour correction.
    Sinon, on termine le graphe.
    """
    if not state.validation_passed:
        return "analyste_risque"
    return "__end__"


def route_from_entry(state: TyphoonState) -> str:
    """Route depuis le point d'entrée.

    Permet de démarrer directement à une étape spécifique
    (utile pour les reprises après interruption).
    """
    if state.analyse_risque is not None:
        return "generate_report"
    if state.score_global is not None:
        return "analyste_risque"
    return "calculate_score"
