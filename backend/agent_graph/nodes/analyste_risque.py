"""Nœud : Agent Analyste Risque (Agent #1).

Reçoit les scores déterministes + données brutes + formulaire client,
envoie le tout à Claude avec un prompt système structuré,
et récupère un JSON strict (scores par aléa, justifications).
"""

from __future__ import annotations

from backend.agent_graph.state import TyphoonState, AnalyseRisque
from backend.agents.analyste_risque.agent import analyser_risques


def analyste_risque_node(state: TyphoonState) -> dict:
    """Analyse qualitative des risques via LLM.

    Enrichit le state avec l'analyse structurée retournée par Claude.
    """
    analyse: AnalyseRisque = analyser_risques(
        client_form=state.client_form,
        scores_par_alea=state.scores_par_alea,
        score_global=state.score_global,
        raw_data=state.raw_data,
    )

    return {
        "analyse_risque": analyse,
        "next_node": "recommandation",
    }
