"""
<<<<<<< HEAD
digital_twin_agent — noeud LangGraph (dernier maillon du graphe).

Lit `state.building_data`, `state.risk_scores_numeriques` (score 0-100 par
zone, produit par risk_scoring_agent) et `state.recommendations` (texte
sourcé, produit par rag_agent — optionnel, peut être absent si ce noeud a
échoué ou n'a pas de clé Mistral configurée). Ecrit `state.digital_twin` =
le contrat final consommé par la scène Three.js du front. L'assemblage
lui-même vit dans `app.digital_twin.contract`.
=======
diagnostic_agent — noeud LangGraph (dernier maillon du graphe).

Lit `state.building_data`, `state.risk_scores` et `state.interpretations`,
assemble le diagnostic final de vulnérabilité climatique consommé par
le frontend. L'assemblage lui-même vit dans `app.digital_twin.diagnostic_builder`.
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314
"""

from __future__ import annotations

import time

from app.agents.state import TyphoonState
from app.core.logging import get_logger
<<<<<<< HEAD
from app.digital_twin.contract import assemble_contract
=======
from app.digital_twin.diagnostic_builder import build_diagnostic
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314

logger = get_logger(__name__)


def run(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
<<<<<<< HEAD
    contract = assemble_contract(
        state["building_data"],
        state["risk_scores_numeriques"],
        recommendations=state.get("recommendations"),
        formulaire=state.get("formulaire"),
    )
    logger.info("digital_twin_agent (noeud) -- termine en %.2fs", time.perf_counter() - t0)
    return {"digital_twin": contract}
=======
    diagnostic = build_diagnostic(
        state["building_data"],
        state["risk_scores"],
        formulaire=state.get("formulaire"),
        interpretations=state.get("interpretations"),
    )
    logger.info("diagnostic_agent (noeud) -- terminé en %.2fs", time.perf_counter() - t0)
    return {"digital_twin": diagnostic}
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314
