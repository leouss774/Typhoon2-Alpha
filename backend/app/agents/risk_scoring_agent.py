"""
risk_scoring_agent — noeud LangGraph.

Lit `state.building_data` (produit par collector_agent), ecrit
`state.risk_scores_numeriques`. Le calcul lui-meme (deterministe, base sur
Georisques/BDNB/Open-Meteo) vit dans `app.scoring.risk_model` ; ce module
n'est que le point de branchement dans le graphe.

Nommage : ce noeud coexiste avec `scoring_agent.py` (derivation qualitative
risque/zone au format attendu par `rag_agent`, cf. sa propre docstring) —
deux besoins différents en aval (recommandations textuelles sourcées d'un
côté, score 0-100 par zone pour le rendu 3D de l'autre), donc deux clés
d'etat distinctes plutôt qu'un seul champ `risk_scores` ambigu :
  - `risk_scores`            (scoring_agent.py, qualitatif, 5 zones) -> rag_agent
  - `risk_scores_numeriques` (ce module, 0-100, 7 zones)             -> digital_twin_agent
"""

from __future__ import annotations

import time

from app.agents.state import TyphoonState
from app.core.logging import get_logger
from app.scoring.risk_model import compute_risk_scores

logger = get_logger(__name__)


def run(state: TyphoonState) -> dict:
    t0 = time.perf_counter()
    risk_scores_numeriques = compute_risk_scores(state["building_data"])
    logger.info("risk_scoring_agent (noeud) -- termine en %.2fs", time.perf_counter() - t0)
    return {"risk_scores_numeriques": risk_scores_numeriques}
