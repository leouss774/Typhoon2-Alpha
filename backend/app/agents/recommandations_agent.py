"""
recommandations_agent — noeud LangGraph, place entre scoring_agent et
digital_twin_agent (cf. PROMPT_INTEGRATION_ouss.md section 3 : "Ajoute un
noeud `recommandations` apres le(s) noeud(s) de calcul du score de risque").

Lit `state.building_data` + `state.risk_scores`, appelle l'agent RAG
(app.recommandations.service.generate_recommendations) et reecrit
`state.risk_scores.zones[*].recommandations` (jusque-la des listes vides,
cf. app.scoring.risk_model) avec les recommandations sourcees. C'est cette
version enrichie de `risk_scores` que digital_twin_agent consomme ensuite
pour assembler le contrat final (zones + recommandations dans le meme
objet, cf. app/digital_twin/contract.py).

Les appels Mistral (embeddings + chat) sont synchrones (SDK mistralai) :
executes via `asyncio.to_thread` pour ne pas bloquer la boucle asyncio
FastAPI le temps de la sequence d'appels RAG (plusieurs dizaines de
secondes possible selon le nombre de zones/risques a traiter), cf.
PROMPT_INTEGRATION_ouss.md section 2.
"""

from __future__ import annotations

import asyncio
import time

from app.agents.state import TyphoonState
from app.core.logging import get_logger
from app.recommandations import mapping
from app.recommandations.service import generate_recommendations, get_index

logger = get_logger(__name__)


async def run(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    risk_scores = state["risk_scores"]

    house_payload = mapping.build_house_payload(state["building_data"], risk_scores)
    n_zones = len(house_payload["zones"])
    logger.info(
        "recommandations_agent (noeud) -- %d zone(s) a risque non-faible a traiter : %s",
        n_zones,
        [z["zone"] for z in house_payload["zones"]],
    )

    if n_zones == 0:
        logger.info("recommandations_agent (noeud) -- aucune zone a risque, aucun appel RAG")
        return {"risk_scores": risk_scores}

    index = get_index()
    reco_result = await asyncio.to_thread(generate_recommendations, house_payload, index)
    mapping.merge_recommendations(risk_scores, reco_result)

    logger.info(
        "recommandations_agent (noeud) -- termine en %.2fs (%d recommandation(s) au total)",
        time.perf_counter() - t0,
        sum(len(z.get("recommandations", [])) for z in risk_scores["zones"].values()),
    )
    return {"risk_scores": risk_scores}
