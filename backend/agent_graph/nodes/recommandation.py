"""Nœud : Agent Recommandation RAG (Agent #2).

Reçoit les scores + risques dominants + caractéristiques maison,
interroge ChromaDB pour trouver les travaux adaptés,
et génère une liste priorisée avec coûts estimés et gain de résilience.
"""

from __future__ import annotations

from backend.agent_graph.state import TyphoonState, TravauxRecommandation
from backend.agents.recommandation.agent import generer_recommandations


def recommandation_node(state: TyphoonState) -> dict:
    """Génère les recommandations de travaux via RAG.

    Interroge la base vectorielle ChromaDB et enrichit via LLM.
    """
    recommandations: list[TravauxRecommandation] = generer_recommandations(
        analyse_risque=state.analyse_risque,
        score_global=state.score_global,
        scores_par_alea=state.scores_par_alea,
        client_form=state.client_form,
    )

    return {
        "recommandations": recommandations,
        "next_node": "generate_report",
    }
