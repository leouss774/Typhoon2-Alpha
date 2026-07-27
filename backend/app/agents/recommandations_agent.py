"""
<<<<<<< HEAD
recommandations_agent — noeud LangGraph, insere entre scoring_agent et
digital_twin_agent (cf. recommendation_travaux/PROMPT_INTEGRATION_ouss.md).

Lit state.risk_scores (produit par scoring_agent) et state.building_data,
construit le JSON "maison" attendu par l'agent RAG (app.recommandations,
vocabulaire aligne via app.recommandations.mapping), puis ecrit les
recommandations obtenues directement dans risk_scores.zones[*].recommandations
(et la meme liste dans projection_2050.zones[*] : les travaux recommandes ne
dependent pas de l'annee, seul le score de risque varie entre 2025 et 2050).

Si l'index RAG n'a pas ete charge (build_index.py pas encore lance, ou
MISTRAL_API_KEY absente), le noeud ne casse pas le graphe : il journalise un
avertissement et laisse recommandations = [] (valeur par defaut deja posee
par risk_model._build_zone) — digital_twin_agent et le front continuent de
fonctionner normalement, juste sans recommandations.
=======
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
>>>>>>> agent/recommandation-RAG
"""

from __future__ import annotations

<<<<<<< HEAD
=======
import asyncio
>>>>>>> agent/recommandation-RAG
import time

from app.agents.state import TyphoonState
from app.core.logging import get_logger
<<<<<<< HEAD
from app.recommandations import rag_engine
from app.recommandations.mapping import build_house_payload
=======
from app.recommandations import mapping
from app.recommandations.service import generate_recommendations, get_index
>>>>>>> agent/recommandation-RAG

logger = get_logger(__name__)


<<<<<<< HEAD
def run(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    risk_scores = state["risk_scores"]
    building_data = state["building_data"]

    index = rag_engine.get_loaded_index()
    if index is None:
        logger.warning(
            "recommandations_agent (noeud) -- index RAG non charge, "
            "recommandations laissees vides (voir README_INTEGRATION / build_index.py)"
        )
        return {"risk_scores": risk_scores}

    house_payload = build_house_payload(building_data, risk_scores)

    try:
        result = rag_engine.generate_recommendations(house_payload, index)
    except Exception:
        logger.exception("recommandations_agent (noeud) -- echec generation recommandations")
        return {"risk_scores": risk_scores}

    reco_by_zone = {z["zone"]: z.get("recommandations", []) for z in result.get("zones", [])}
    proj_zones = risk_scores.get("projection_2050", {}).get("zones", {})
    for zone_name, recos in reco_by_zone.items():
        if zone_name in risk_scores.get("zones", {}):
            risk_scores["zones"][zone_name]["recommandations"] = recos
        if zone_name in proj_zones:
            proj_zones[zone_name]["recommandations"] = recos

    logger.info(
        "recommandations_agent (noeud) -- termine en %.2fs (%d zone(s) traitee(s))",
        time.perf_counter() - t0,
        len(reco_by_zone),
=======
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
>>>>>>> agent/recommandation-RAG
    )
    return {"risk_scores": risk_scores}
