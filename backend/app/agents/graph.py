"""
StateGraph LangGraph : collector_agent -> scoring_agent -> recommandations_agent
-> digital_twin_agent (cf. README racine, section "Architecture
multi-agents", et backend/recommendation_travaux-main/PROMPT_INTEGRATION_ouss.md
pour l'integration du noeud recommandations).

recommandations_agent tourne apres scoring_agent (dont il consomme
`risk_scores.zones`) et avant digital_twin_agent (qui assemble le contrat
final a partir de `risk_scores`, recommandations desormais incluses) :
`zones[*].recommandations` n'est plus une liste vide a la sortie du graphe.

Checkpointer : `MemorySaver` (en memoire, perdu au redemarrage du process)
pour cette etape MVP. Le README prevoit un checkpointer SQLite en local
/ Postgres en prod — a brancher quand la persistance entre redemarrages
deviendra utile (reprise d'un diagnostic interrompu, audit).
"""

from __future__ import annotations

import time

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import digital_twin_agent, recommandations_agent, scoring_agent
from app.agents.collector_agent import collect
from app.agents.state import TyphoonState
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _collector_node(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    copernicus_enabled = state.get("copernicus", True)
    building_data = await collect(state["adresse"], enable_copernicus=copernicus_enabled)
    logger.info("collector_agent (noeud) -- termine en %.2fs (copernicus=%s)", time.perf_counter() - t0, copernicus_enabled)
    return {"building_data": building_data}


def _scoring_node(state: TyphoonState) -> dict:
    return scoring_agent.run(state)


async def _recommandations_node(state: TyphoonState) -> dict:
    return await recommandations_agent.run(state)


def _digital_twin_node(state: TyphoonState) -> dict:
    return digital_twin_agent.run(state)


def build_graph():
    graph = StateGraph(TyphoonState)
    graph.add_node("collector_agent", _collector_node)
    graph.add_node("scoring_agent", _scoring_node)
    graph.add_node("recommandations_agent", _recommandations_node)
    graph.add_node("digital_twin_agent", _digital_twin_node)

    graph.add_edge(START, "collector_agent")
    graph.add_edge("collector_agent", "scoring_agent")
    graph.add_edge("scoring_agent", "recommandations_agent")
    graph.add_edge("recommandations_agent", "digital_twin_agent")
    graph.add_edge("digital_twin_agent", END)

    return graph.compile(checkpointer=MemorySaver())


# Compile une seule fois au chargement du module (reutilise entre requetes).
diagnostic_graph = build_graph()
