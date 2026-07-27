"""
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
"""

from __future__ import annotations

import time

from app.agents.state import TyphoonState
from app.core.logging import get_logger
from app.recommandations import rag_engine
from app.recommandations.mapping import build_house_payload

logger = get_logger(__name__)


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
    )
    return {"risk_scores": risk_scores}
