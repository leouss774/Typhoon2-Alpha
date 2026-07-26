"""
StateGraph LangGraph : collector_agent -> scoring_agent -> digital_twin_agent
(cf. README racine, section "Architecture multi-agents").

rag_agent n'est pas encore branche (base documentaire/RAG non implementee,
voir README Roadmap) : le graphe s'arrete a digital_twin_agent, et
`zones[*].recommandations` reste une liste vide en attendant ce noeud.

Checkpointer : `MemorySaver` (en memoire, perdu au redemarrage du process)
pour cette etape MVP. Le README prevoit un checkpointer SQLite en local
/ Postgres en prod — a brancher quand la persistance entre redemarrages
deviendra utile (reprise d'un diagnostic interrompu, audit).
"""

from __future__ import annotations

import time

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import digital_twin_agent, scoring_agent
from app.agents.collector_agent import collect
from app.agents.state import TyphoonState
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _collector_node(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    building_data = await collect(state["adresse"])
    logger.info("collector_agent (noeud) -- termine en %.2fs", time.perf_counter() - t0)
    return {"building_data": building_data}


def _scoring_node(state: TyphoonState) -> dict:
    return scoring_agent.run(state)


def _digital_twin_node(state: TyphoonState) -> dict:
    return digital_twin_agent.run(state)


def build_graph():
    graph = StateGraph(TyphoonState)
    graph.add_node("collector_agent", _collector_node)
    graph.add_node("scoring_agent", _scoring_node)
    graph.add_node("digital_twin_agent", _digital_twin_node)

    graph.add_edge(START, "collector_agent")
    graph.add_edge("collector_agent", "scoring_agent")
    graph.add_edge("scoring_agent", "digital_twin_agent")
    graph.add_edge("digital_twin_agent", END)

    return graph.compile(checkpointer=MemorySaver())


# Compile une seule fois au chargement du module (reutilise entre requetes).
diagnostic_graph = build_graph()
