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
from app.recommandations.service import (
    generate_recommendations,
    get_index,
    SYSTEM_PROMPT,
    search_zone_candidates,
    build_user_prompt_for_zone,
)
from app.recommandations.mistral_client import chat_json

logger = get_logger(__name__)


async def run(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    risk_scores = state["risk_scores"]

    house_payload = mapping.build_house_payload(state["building_data"], risk_scores)
    zones = house_payload.get("zones", [])
    logger.info(
        "recommandations_agent (noeud) -- %d zone(s) a risque non-faible a traiter : %s",
        len(zones),
        [z["zone"] for z in zones],
    )

    if not zones:
        logger.info("recommandations_agent (noeud) -- aucune zone a risque, aucun appel RAG")
        return {"risk_scores": risk_scores}

    index = get_index()

    async def _process_zone(zone_info: dict) -> dict:
        """Traite une zone isolement (peut etre parallelise)."""
        zone_name = zone_info.get("zone")
        risques = zone_info.get("risques", [])
        zone_reco: dict = {"zone": zone_name, "risques": risques, "recommandations": []}

        if not risques or not index:
            return zone_reco

        # Meme si la recherche ne remonte aucune fiche vraiment pertinente,
        # on appelle quand meme le modele : le SYSTEM_PROMPT (service.py) lui
        # demande dans ce cas de proposer une recommandation de bonne
        # pratique generale plutot que de laisser la zone sans rien (une
        # zone a risque non-faible ne doit jamais repartir sans
        # recommandation, et l'absence de fiche ne doit jamais etre
        # mentionnee au proprietaire).
        candidates = search_zone_candidates(index, zone_name, risques)

        user_prompt = build_user_prompt_for_zone(
            house_payload.get("bien", {}), zone_name, risques, candidates
        )

        try:
            result = await asyncio.to_thread(chat_json, SYSTEM_PROMPT, user_prompt)
            zone_reco["recommandations"] = result.get("recommandations", [])
        except Exception as e:
            logger.warning("  -> erreur Mistral pour %s: %s", zone_name, e)

        return zone_reco

    # Parallelisation des zones via asyncio.gather
    tasks = [_process_zone(z) for z in zones]
    zones_out = await asyncio.gather(*tasks)

    reco_result = {
        "adresse": house_payload.get("adresse"),
        "bien": house_payload.get("bien"),
        "zones": zones_out,
    }
    mapping.merge_recommendations(risk_scores, reco_result)

    logger.info(
        "recommandations_agent (noeud) -- termine en %.2fs (%d recommandation(s) au total)",
        time.perf_counter() - t0,
        sum(len(z.get("recommandations", [])) for z in risk_scores["zones"].values()),
    )
    return {"risk_scores": risk_scores}
