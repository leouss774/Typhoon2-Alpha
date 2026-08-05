"""
Service d'entrée du volet économique — cf.
docs/STRATEGIE_RETOUR_INVESTISSEMENT.md et app/api/routes/
retour_investissement.py.

Déterministe et sans LLM : tous les montants sont des fonctions pures des
entrées réelles (building_data, risk_scores) et de paramètres référencés
(registre app.economie.sources). Aucun nombre n'est jamais inventé.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.economie.roi import evaluate

logger = get_logger(__name__)


def compute_retour_investissement(
    building_data: dict[str, Any],
    risk_scores: dict[str, Any],
    surface_m2: float | None = None,
) -> dict[str, Any]:
    """Point d'entrée : calcule le contrat économique complet.

    Paramètres
    ----------
    building_data : sortie de collector_agent (/diagnostic/fast->_resume).
    risk_scores : sortie de scoring_agent, enrichie des recommandations
        (zone.recommandations avec cout_estime) — idéalement après
        /diagnostic/recommandations.
    surface_m2 : optionnel, emprise au sol du bien (geometry du jumeau) ;
        sinon repli sur les champs surface de la BDNB.

    Retourne le contrat du volet économique (niveaux A/B/C + ROI + valeur
    immobilière qualitative), avec 3 statuts seulement : calcule /
    fourchette / null.
    """
    logger.info("economie -- calcul du retour sur investissement")
    result = evaluate(building_data, risk_scores, surface_m2=surface_m2)
    logger.info(
        "  -> valeur=%s | cout_net=%s | B_assu=%s | AAL=%s | TR=%s | confiance=%s",
        result["valeur"]["valeur_reconstruction"].get("statut"),
        result["niveau_b"]["cout_travaux"]["cout_net"].get("statut"),
        result["niveau_b"]["benefice_assurance"]["total"].get("statut"),
        result["niveau_c"].get("statut"),
        result["roi"]["temps_de_retour"].get("statut"),
        result["confidence"].get("niveau"),
    )
    return result
