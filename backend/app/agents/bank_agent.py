"""bank_agent — noeud LangGraph optionnel pour la décision bancaire.

Intégré entre scoring_agent et digital_twin_agent.
Utilise les tools bancaires du projet actuel.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.state import TyphoonState

logger = logging.getLogger(__name__)

# Import conditionnel des outils bancaires
# tools/ est accessible car backend/ est dans sys.path
try:
    from tools.bank_tools import (
        get_property_market_value,
        get_current_bank_rates,
        calculate_risk_premium,
        calculate_data_confidence,
        evaluate_hard_stops,
    )
    HAS_BANK_TOOLS = True
    logger.info("Bank tools chargés avec succès")
except ImportError as e:
    HAS_BANK_TOOLS = False
    logger.warning("Bank tools non disponibles: %s", e)


def run(state: TyphoonState) -> dict:
    """Exécute l'agent bancaire sur l'état courant."""
    logger.info("bank_agent (noeud) -- analyse bancaire")

    if not HAS_BANK_TOOLS:
        logger.warning("bank tools indisponibles -- décision vide")
        return {"bank_decision": {}}

    building_data = state.get("building_data", {})
    risk_scores = state.get("risk_scores", {})

    adresse = building_data.get("adresse", {}).get("label", "Adresse inconnue")
    score_global = risk_scores.get("score_global", 0)

    try:
        market_data = get_property_market_value(adresse)
        rates_data = get_current_bank_rates()
        premium_data = calculate_risk_premium(score_global)
        confidence_data = calculate_data_confidence(state.get("formulaire", {}), building_data.get("georisques", {}))
        hard_stops = evaluate_hard_stops(score_global, state.get("formulaire", {}))

        bank_decision = {
            "valeur_marche": market_data.get("valeur_estimee", 0),
            "valeur_ajustee": market_data.get("valeur_estimee", 0) * (1 - premium_data.get("decote_valeur_garantie_pct", 0) / 100),
            "decote_pct": premium_data.get("decote_valeur_garantie_pct", 0),
            "taux_propose": rates_data.get("taux_base_20_ans", 0) + premium_data.get("majoration_taux_interet", 0),
            "majoration_taux": premium_data.get("majoration_taux_interet", 0),
            "exigences": premium_data.get("exigences_banque", []),
            "indice_confiance": confidence_data.get("indice", 50),
            "score_climatique": score_global,
            "score_risque_bancaire": min(100, max(0, int(score_global * 0.7 + (100 - confidence_data.get("indice", 50)) * 0.3))),
            "hard_stops": hard_stops,
            "points_a_verifier": [],
            "statut_dossier": "Refus Automatique" if hard_stops else ("Fast-Track" if score_global < 30 else "Étude Manuelle"),
        }

        logger.info("bank_agent (noeud) -- décision: %s (score=%d)", bank_decision["statut_dossier"], score_global)
        return {"bank_decision": bank_decision}

    except Exception as e:
        logger.error("bank_agent -- erreur: %s", e)
        return {"bank_decision": {}}
