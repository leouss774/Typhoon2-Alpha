"""
digital_twin_agent — noeud LangGraph (dernier maillon du graphe).

Lit `state.building_data` et `state.risk_scores`, ecrit `state.digital_twin`
= le contrat final consomme par la scene Three.js du front. L'assemblage
lui-meme vit dans `app.digital_twin.contract`, cf. README section
"digital_twin_agent".
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
        state["risk_scores"],
        formulaire=state.get("formulaire"),
    )
    logger.info("digital_twin_agent (noeud) -- termine en %.2fs", time.perf_counter() - t0)
    return {"digital_twin": contract}
