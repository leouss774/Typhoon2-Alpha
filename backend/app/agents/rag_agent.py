"""
rag_agent : troisieme noeud du graphe LangGraph (voir README.md). Consomme
state["risk_scores"] (contrat "maison" produit par scoring_agent) et produit
state["recommendations"], en appelant l'agent recommandations de la collegue
(app/recommandations/agent2_rag.py, voir PROMPT_INTEGRATION_ouss.md).

Point important repris du guide d'integration (point 2) : l'index vectoriel
(data/index.json) doit etre charge UNE SEULE FOIS au demarrage du process, pas
relu a chaque requete. get_index() ci-dessous fait office de cache process-wide
(equivalent d'un `lifespan`/`startup` FastAPI - il n'y a pas encore d'app FastAPI
dans ce depot, voir README.md section Roadmap, donc un cache paresseux au niveau
module fait la meme chose en attendant).

Les appels Mistral (chat_json, embed_texts) sont synchrones (SDK mistralai) :
on les execute dans un threadpool via asyncio.to_thread, comme deja fait pour
Copernicus/DVF dans collector_agent.py, pour ne pas bloquer la boucle asyncio.
"""

from __future__ import annotations

from app.recommandations.agent2_rag import generate_recommendations, load_index

_index_cache: list | None = None


def get_index() -> list:
    """Charge data/index.json une seule fois par process (cache module-level)."""
    global _index_cache
    if _index_cache is None:
        _index_cache = load_index()
    return _index_cache


async def rag_node(state: dict) -> dict:
    """Noeud LangGraph : lit state['risk_scores'], ecrit state['recommendations']."""
    import asyncio

    house = state["risk_scores"]
    index = get_index()
    recommendations = await asyncio.to_thread(generate_recommendations, house, index)
    return {"recommendations": recommendations}
