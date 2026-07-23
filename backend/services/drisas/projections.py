"""Service de projection climatique basé sur les données DRIAS.

Calcule l'évolution des scores de risque aux horizons
2025, 2050 et 2100 en fonction des scénarios climatiques.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Facteurs multiplicateurs par horizon pour chaque aléa
# Basés sur les tendances DRIAS (scénario RCP 4.5)
FACTEURS_PROJECTION = {
    "2025": {
        "rga": 1.05,
        "inondation": 1.08,
        "tempete": 1.10,
        "feu_foret": 1.10,
        "submersion": 1.05,
    },
    "2050": {
        "rga": 1.25,
        "inondation": 1.35,
        "tempete": 1.30,
        "feu_foret": 1.45,
        "submersion": 1.25,
    },
    "2100": {
        "rga": 1.50,
        "inondation": 1.70,
        "tempete": 1.60,
        "feu_foret": 1.90,
        "submersion": 1.60,
    },
}


def projeter_scores_2050(
    scores_actuels: dict[str, float],
    localisation: str = "",
    scenario: str = "rcp45",
) -> dict[str, float]:
    """Projette les scores actuels à l'horizon 2050.

    Utilise les facteurs DRIAS pour estimer l'évolution
    de chaque aléa d'ici 2050.

    Args:
        scores_actuels: Scores actuels par aléa (0-100).
        localisation: Adresse ou code INSEE (pour affinage futur).
        scenario: Scénario climatique (rcp45, rcp85).

    Returns:
        Dict des scores projetés en 2050.
    """
    facteurs = FACTEURS_PROJECTION.get("2050", FACTEURS_PROJECTION["2050"])
    projections = {}

    for alea, score in scores_actuels.items():
        facteur = facteurs.get(alea, 1.0)
        projections[alea] = round(min(100, score * facteur), 1)

    return projections


def projeter_toutes_annees(
    scores_actuels: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Projette les scores pour tous les horizons disponibles."""
    projections = {}
    for horizon in ["2025", "2050", "2100"]:
        facteurs = FACTEURS_PROJECTION.get(horizon, FACTEURS_PROJECTION["2050"])
        projections[horizon] = {
            alea: round(min(100, score * facteurs.get(alea, 1.0)), 1)
            for alea, score in scores_actuels.items()
        }
    return projections
