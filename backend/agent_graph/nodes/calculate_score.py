"""Nœud : calcul du score déterministe global.

À partir des données brutes et du formulaire client, calcule
un score de risque (0-100) pour chaque aléa naturel.
"""

from __future__ import annotations

from backend.agent_graph.state import TyphoonState
from backend.services.scoring.score_global import compute_all_scores


def calculate_score_node(state: TyphoonState) -> dict:
    """Calcule les scores déterministes pour tous les aléas.

    Prend les données du state et retourne les scores calculés.
    """
    scores = compute_all_scores(
        client_form=state.client_form,
        raw_data=state.raw_data,
    )

    return {
        "score_global": scores["score_global"],
        "scores_par_alea": scores["scores_par_alea"],
        "next_node": "analyste_risque",
    }
