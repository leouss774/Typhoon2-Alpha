"""
Agent de projection.

Projette la valeur du bien année par année sur la durée du prêt, selon deux
scénarios :
  - sans travaux : le risque évolue linéairement vers le score projection_2050
  - avec travaux : le risque est amélioré selon le gain_resilience_pct des
    recommandations applicables, avant d'être projeté de la même façon.
"""

from dataclasses import dataclass
from typing import Dict, List
from datetime import date

from .valuation_agent import calculer_risque_pondere, POIDS_ZONES, FACTEUR_SEVERITE


@dataclass
class PointAnnee:
    annee: int
    risque_pondere: float
    valeur: float


def _interpoler(risque_actuel: float, risque_2050: float, annee_actuelle: int, annee_cible: int) -> float:
    horizon = 2050 - annee_actuelle
    if horizon <= 0:
        return risque_2050
    t = annee_cible - annee_actuelle
    t = max(0, min(t, horizon))
    return risque_actuel + (risque_2050 - risque_actuel) * (t / horizon)


def appliquer_travaux(zones: Dict[str, dict], recommandations: Dict[str, dict]) -> Dict[str, dict]:
    """
    Retourne une copie des zones avec le risque réduit pour les aléas couverts
    par les recommandations fournies (via aleas_adresses -> mapping simplifié
    aléa -> zone la plus directement concernée).
    """
    # Mapping simplifié aléa -> zone principale impactée. À ajuster si votre
    # agent de risque fournit une correspondance plus fine.
    mapping_alea_zone = {
        "rga": "fondations",
        "inondation": "sous_sol",
        "tempete": "toiture",
        "incendie": "murs_nord",  # exemple : bardage bois façade nord
    }

    zones_ameliorees = {z: dict(v) for z, v in zones.items()}

    for alea, reco in recommandations.items():
        zone_cible = mapping_alea_zone.get(alea)
        if zone_cible and zone_cible in zones_ameliorees:
            gain = reco.get("gain_resilience_pct", 0) / 100
            risque_actuel = zones_ameliorees[zone_cible]["risque"]
            zones_ameliorees[zone_cible] = dict(zones_ameliorees[zone_cible])
            zones_ameliorees[zone_cible]["risque"] = round(risque_actuel * (1 - gain), 2)

    return zones_ameliorees


def projeter(
    valeur_ajustee: float,
    zones: Dict[str, dict],
    score_global_2050: float,
    duree_annees: int,
    tendance_marche_annuelle: float = 0.0,
    annee_depart: int = None,
    poids: Dict[str, float] = None,
    facteur_severite: float = FACTEUR_SEVERITE,
) -> List[PointAnnee]:
    """Projette la valeur année par année pour UN scénario donné (zones figées en entrée)."""
    poids = poids or POIDS_ZONES
    annee_depart = annee_depart or date.today().year

    risque_actuel = calculer_risque_pondere(zones, poids)
    decote_initiale = (risque_actuel / 100) * facteur_severite

    points = []
    for t in range(0, duree_annees + 1):
        annee = annee_depart + t
        # on interpole le score global (proxy simple : on suppose une évolution
        # homothétique de toutes les zones vers le score global 2050 fourni)
        ratio_evolution = _interpoler(risque_actuel, score_global_2050, annee_depart, annee) / risque_actuel if risque_actuel else 1
        risque_t = risque_actuel * ratio_evolution
        decote_t = (risque_t / 100) * facteur_severite

        # variation nette : tendance de marché moins aggravation du risque
        # par rapport à la décote déjà intégrée dans valeur_ajustee (t=0)
        ajustement_risque = decote_initiale - decote_t
        valeur_t = valeur_ajustee * ((1 + tendance_marche_annuelle) ** t) * (1 + ajustement_risque)

        points.append(PointAnnee(annee=annee, risque_pondere=round(risque_t, 2), valeur=round(valeur_t, 2)))

    return points
