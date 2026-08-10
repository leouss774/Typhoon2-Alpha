"""
diagnostic_agent — noeud LangGraph (dernier maillon du graphe).

Lit `state.building_data`, `state.risk_scores` et `state.interpretations`,
assemble le diagnostic final de vulnérabilité climatique consommé par
le frontend. L'assemblage lui-même vit dans `app.digital_twin.diagnostic_builder`.
"""

from __future__ import annotations

import time

from app.agents.state import TyphoonState
from app.core.logging import get_logger
from app.digital_twin.diagnostic_builder import build_diagnostic

logger = get_logger(__name__)


def run(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    diagnostic = build_diagnostic(
        state["building_data"],
        state["risk_scores"],
        formulaire=state.get("formulaire"),
        interpretations=state.get("interpretations"),
        risques_principaux=state.get("risques_principaux"),
    )
    logger.info("diagnostic_agent (noeud) -- terminé en %.2fs", time.perf_counter() - t0)
    return {"digital_twin": diagnostic}
