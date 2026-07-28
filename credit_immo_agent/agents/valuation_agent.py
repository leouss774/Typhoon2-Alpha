"""
Agent de valorisation.

Prend le score de risque par zone (agent de risque) et une valeur de marché,
et produit une valeur ajustée au risque avec la décote appliquée.

Toutes les pondérations sont des valeurs par défaut, documentées et modifiables
(voir POIDS_ZONES / FACTEUR_SEVERITE), conformément au prompt système.
"""

from dataclasses import dataclass, field
from typing import Dict, List

# Pondération par défaut des zones (doit sommer à 1.0)
POIDS_ZONES = {
    "fondations": 0.30,
    "toiture": 0.20,
    "sous_sol": 0.15,
    "murs_nord": 0.0875,
    "murs_sud": 0.0875,
    "murs_est": 0.0875,
    "murs_ouest": 0.0875,
}

# Part du score de risque pondéré traduite en décote de valeur (0.5 = 50%)
FACTEUR_SEVERITE = 0.5


@dataclass
class ResultatValorisation:
    risque_pondere: float
    decote_pct: float
    valeur_marche: float
    valeur_ajustee: float
    hypotheses: List[str] = field(default_factory=list)


def calculer_risque_pondere(zones: Dict[str, dict], poids: Dict[str, float] = None) -> float:
    """Calcule le score de risque pondéré à partir des scores par zone."""
    poids = poids or POIDS_ZONES
    total = 0.0
    poids_utilise = 0.0
    for zone, w in poids.items():
        if zone in zones:
            total += zones[zone]["risque"] * w
            poids_utilise += w
    if poids_utilise == 0:
        raise ValueError("Aucune zone reconnue dans les données de risque fournies.")
    # normalise si certaines zones manquent, pour rester sur une échelle 0-100
    return total / poids_utilise


def valoriser(
    valeur_marche: float,
    zones: Dict[str, dict],
    poids: Dict[str, float] = None,
    facteur_severite: float = FACTEUR_SEVERITE,
) -> ResultatValorisation:
    if valeur_marche is None:
        raise ValueError(
            "valeur_marche_bien manquante : impossible de produire une valorisation sans cette donnée."
        )

    risque_pondere = calculer_risque_pondere(zones, poids)
    decote_pct = (risque_pondere / 100) * facteur_severite
    valeur_ajustee = valeur_marche * (1 - decote_pct)

    hypotheses = [
        f"Pondération des zones : {poids or POIDS_ZONES}",
        f"Facteur de sévérité appliqué au score pondéré : {facteur_severite} (valeur par défaut, à valider avec la politique de risque de l'établissement)",
    ]

    return ResultatValorisation(
        risque_pondere=round(risque_pondere, 2),
        decote_pct=round(decote_pct, 4),
        valeur_marche=valeur_marche,
        valeur_ajustee=round(valeur_ajustee, 2),
        hypotheses=hypotheses,
    )
