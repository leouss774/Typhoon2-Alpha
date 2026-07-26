"""
StateGraph LangGraph :

    collector_agent -> scoring_agent -> risk_scoring_agent -> rag_agent -> digital_twin_agent

- collector_agent       : fan-out/fan-in des sources live (BDNB, Georisques, IGN,
                           Open-Meteo, Copernicus, DVF), voir collector_agent.py.
- scoring_agent          : derivation qualitative risque/zone (collegue), format
                           attendu par rag_agent (recommandations sourcees).
- risk_scoring_agent     : score 0-100 par zone directionnelle (deterministe,
                           Georisques/BDNB/climat), format attendu par le rendu 3D.
- rag_agent              : recommandations sourcees via l'agent RAG de la collegue
                           (Mistral). NECESSITE MISTRAL_API_KEY dans backend/.env -
                           enveloppe ici dans un try/except pour ne jamais faire
                           echouer tout le diagnostic si la cle manque ou si l'appel
                           Mistral echoue : on continue sans recommandations plutot
                           que de renvoyer une erreur 502 pour un maillon optionnel.
- digital_twin_agent     : assemble geometry + risk_scores_numeriques +
                           recommendations (si presentes) dans le contrat final.

Checkpointer : `MemorySaver` (en memoire, perdu au redemarrage du process) pour
cette etape MVP. Le README prevoit un checkpointer SQLite en local / Postgres en
prod - a brancher quand la persistance entre redemarrages deviendra utile.
"""

from __future__ import annotations

import time

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import digital_twin_agent, risk_scoring_agent
from app.agents.collector_agent import collect
from app.agents.rag_agent import rag_node
from app.agents.scoring_agent import scoring_node
from app.agents.state import TyphoonState
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _collector_node(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    building_data = await collect(state["adresse"])
    logger.info("collector_agent (noeud) -- termine en %.2fs", time.perf_counter() - t0)
    return {"building_data": building_data}


async def _scoring_node(state: TyphoonState) -> dict:
    """scoring_agent (collegue) : qualitatif, pour rag_agent."""
    t0 = time.perf_counter()
    result = await scoring_node(state)
    logger.info("scoring_agent (noeud) -- termine en %.2fs", time.perf_counter() - t0)
    return result


def _risk_scoring_node(state: TyphoonState) -> dict:
    """risk_scoring_agent (ce depot) : numerique 0-100, pour digital_twin_agent."""
    return risk_scoring_agent.run(state)


async def _rag_node_safe(state: TyphoonState) -> dict:
    """rag_agent, mais sans jamais faire planter le graphe : une recommandation
    manquante degrade l'experience (moins de contenu affiche), une collecte ou
    un score manquant la casse - ce n'est pas le meme niveau de criticite."""
    t0 = time.perf_counter()
    try:
        result = await rag_node(state)
        logger.info("rag_agent (noeud) -- termine en %.2fs", time.perf_counter() - t0)
        return result
    except Exception as exc:
        logger.warning(
            "rag_agent (noeud) -- echec en %.2fs (%s: %s) -- le diagnostic continue sans recommandations. "
            "Verifie MISTRAL_API_KEY dans backend/.env si ce n'est pas volontaire.",
            time.perf_counter() - t0, type(exc).__name__, exc,
        )
        return {"recommendations": None}


def _digital_twin_node(state: TyphoonState) -> dict:
    return digital_twin_agent.run(state)


def build_graph():
    graph = StateGraph(TyphoonState)
    graph.add_node("collector_agent", _collector_node)
    graph.add_node("scoring_agent", _scoring_node)
    graph.add_node("risk_scoring_agent", _risk_scoring_node)
    graph.add_node("rag_agent", _rag_node_safe)
    graph.add_node("digital_twin_agent", _digital_twin_node)

    graph.add_edge(START, "collector_agent")
    graph.add_edge("collector_agent", "scoring_agent")
    graph.add_edge("scoring_agent", "risk_scoring_agent")
    graph.add_edge("risk_scoring_agent", "rag_agent")
    graph.add_edge("rag_agent", "digital_twin_agent")
    graph.add_edge("digital_twin_agent", END)

    return graph.compile(checkpointer=MemorySaver())


# Compile une seule fois au chargement du module (reutilise entre requetes).
diagnostic_graph = build_graph()


def get_graph():
    """Alias retro-compatible pour app/cli_pipeline.py (`from app.agents.graph
    import get_graph`), qui pre-datait le graphe a 5 noeuds ci-dessus."""
    return diagnostic_graph
