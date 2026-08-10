"""
StateGraph LangGraph :
  collector_agent -> scoring_agent -> recommandations_agent -> interpretation_agent -> digital_twin_agent

Le noeud `interpretation_agent` est inséré entre recommandations_agent et
digital_twin_agent : il lit state.building_data + state.risk_scores, interroge
l'API Mistral pour croiser les risques avec les caractéristiques du bâtiment
(matériaux, année de construction, climat, géorisques...), et écrit
state.interpretations avant que digital_twin_agent n'assemble le diagnostic
final. Si la clé Mistral API est absente ou si l'appel échoue, le noeud
produit des interprétations vides sans faire échouer le graphe.

Checkpointer : ``MemorySaver`` (en memoire, perdu au redemarrage du process)
pour cette etape MVP. Le README prevoit un checkpointer SQLite en local
/ Postgres en prod — a brancher quand la persistance entre redemarrages
deviendra utile (reprise d'un diagnostic interrompu, audit).

Documentation de reference : backend/recommendation_travaux-main/PROMPT_INTEGRATION_ouss.md
"""

from __future__ import annotations

import time

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import (
    digital_twin_agent,
    interpretation_agent,
    recommandations_agent,
    scoring_agent,
)
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


def _interpretation_node(state: TyphoonState) -> dict:
    return interpretation_agent.run(state)


def _digital_twin_node(state: TyphoonState) -> dict:
    return digital_twin_agent.run(state)


def build_graph():
    graph = StateGraph(TyphoonState)
    graph.add_node("collector_agent", _collector_node)
    graph.add_node("scoring_agent", _scoring_node)
    graph.add_node("recommandations_agent", _recommandations_node)
    graph.add_node("interpretation_agent", _interpretation_node)
    graph.add_node("digital_twin_agent", _digital_twin_node)

    graph.add_edge(START, "collector_agent")
    graph.add_edge("collector_agent", "scoring_agent")
    graph.add_edge("scoring_agent", "recommandations_agent")
    graph.add_edge("recommandations_agent", "interpretation_agent")
    graph.add_edge("interpretation_agent", "digital_twin_agent")
    graph.add_edge("digital_twin_agent", END)

    return graph.compile(checkpointer=MemorySaver())


# Compile une seule fois au chargement du module (reutilise entre requetes).
diagnostic_graph = build_graph()
