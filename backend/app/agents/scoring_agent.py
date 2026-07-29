"""scoring_agent — noeud LangGraph.

Lit `state.building_data`, écrit `state.risk_scores`.
"""

from __future__ import annotations

import time

from app.agents.state import TyphoonState
from app.core.logging import get_logger
from app.scoring.risk_model import compute_risk_scores

logger = get_logger(__name__)


def run(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    risk_scores = compute_risk_scores(state["building_data"])
    logger.info("scoring_agent (noeud) -- terminé en %.2fs", time.perf_counter() - t0)
    return {"risk_scores": risk_scores}
