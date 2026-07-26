"""
digital_twin_agent — noeud LangGraph (dernier maillon du graphe).

Lit `state.building_data`, `state.risk_scores_numeriques` (score 0-100 par
zone, produit par risk_scoring_agent) et `state.recommendations` (texte
sourcé, produit par rag_agent — optionnel, peut être absent si ce noeud a
échoué ou n'a pas de clé Mistral configurée). Ecrit `state.digital_twin` =
le contrat final consommé par la scène Three.js du front. L'assemblage
lui-même vit dans `app.digital_twin.contract`.
"""

from __future__ import annotations

import time

from app.agents.state import TyphoonState
from app.core.logging import get_logger
from app.digital_twin.contract import assemble_contract

logger = get_logger(__name__)


def run(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    contract = assemble_contract(
        state["building_data"],
        state["risk_scores_numeriques"],
        recommendations=state.get("recommendations"),
        formulaire=state.get("formulaire"),
    )
    logger.info("digital_twin_agent (noeud) -- termine en %.2fs", time.perf_counter() - t0)
    return {"digital_twin": contract}
