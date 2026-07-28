"""
Agent de décision de crédit.

Calcule le capital restant dû (amortissement standard), le LTV glissant sur
la durée du prêt pour chaque scénario, puis applique la grille de décision.
"""

from dataclasses import dataclass, field
from typing import List
from .projection_agent import PointAnnee

SEUIL_LTV_ACCORD = 0.80
SEUIL_LTV_MAX = 1.00
SEUIL_SCORE_PRIME_RISQUE = 60


def mensualite(montant: float, taux_annuel: float, duree_annees: int) -> float:
    i = taux_annuel / 12
    n = duree_annees * 12
    if i == 0:
        return montant / n
    return montant * i / (1 - (1 + i) ** (-n))


def capital_restant_du(montant: float, taux_annuel: float, duree_annees: int, annee_ecoulee: int) -> float:
    """Capital restant dû après `annee_ecoulee` années (formule standard d'amortissement)."""
    i = taux_annuel / 12
    n = duree_annees * 12
    t = min(annee_ecoulee, duree_annees) * 12
    if t >= n:
        return 0.0
    if i == 0:
        return montant * (1 - t / n)
    return montant * ((1 + i) ** n - (1 + i) ** t) / ((1 + i) ** n - 1)


@dataclass
class PointLTV:
    annee: int
    valeur_bien: float
    capital_restant_du: float
    ltv: float


@dataclass
class Decision:
    statut: str
    justification: str
    conditions: List[str] = field(default_factory=list)
    prime_de_risque_suggeree: float = None


def calculer_ltv_glissant(
    points_valeur: List[PointAnnee],
    montant_emprunte: float,
    taux_annuel: float,
    duree_annees: int,
) -> List[PointLTV]:
    resultats = []
    for p in points_valeur:
        t = p.annee - points_valeur[0].annee
        crd = capital_restant_du(montant_emprunte, taux_annuel, duree_annees, t)
        ltv = crd / p.valeur if p.valeur > 0 else float("inf")
        resultats.append(PointLTV(annee=p.annee, valeur_bien=p.valeur, capital_restant_du=round(crd, 2), ltv=round(ltv, 4)))
    return resultats


def decider(
    ltv_sans_travaux: List[PointLTV],
    ltv_avec_travaux: List[PointLTV],
    risque_pondere_actuel: float,
    recommandations_prioritaires: List[str],
) -> Decision:
    max_ltv_a = max(p.ltv for p in ltv_sans_travaux)
    max_ltv_b = max(p.ltv for p in ltv_avec_travaux)

    prime = None
    if risque_pondere_actuel > SEUIL_SCORE_PRIME_RISQUE:
        # exemple simple : +5 points de base par point de risque pondéré au-dessus du seuil
        prime = round((risque_pondere_actuel - SEUIL_SCORE_PRIME_RISQUE) * 0.05, 2)

    if max_ltv_a < SEUIL_LTV_ACCORD:
        return Decision(
            statut="accord",
            justification=(
                f"LTV maximal projeté sans travaux ({max_ltv_a:.1%}) reste sous le seuil de {SEUIL_LTV_ACCORD:.0%}. "
                "Le bien couvre le capital restant dû sur toute la durée du prêt."
            ),
            prime_de_risque_suggeree=prime,
        )

    if max_ltv_a < SEUIL_LTV_MAX:
        if max_ltv_b < SEUIL_LTV_ACCORD:
            return Decision(
                statut="accord_conditionnel",
                justification=(
                    f"LTV maximal projeté sans travaux ({max_ltv_a:.1%}) dépasse {SEUIL_LTV_ACCORD:.0%} mais reste sous {SEUIL_LTV_MAX:.0%}. "
                    f"La réalisation des travaux recommandés ramène le LTV maximal à {max_ltv_b:.1%}, sous le seuil cible."
                ),
                conditions=recommandations_prioritaires,
                prime_de_risque_suggeree=prime,
            )
        return Decision(
            statut="accord_conditionnel",
            justification=(
                f"LTV maximal projeté sans travaux ({max_ltv_a:.1%}) dépasse {SEUIL_LTV_ACCORD:.0%}. "
                "Marge de garantie réduite : accord possible sous condition d'apport complémentaire ou de garantie additionnelle."
            ),
            conditions=["Apport complémentaire ou garantie additionnelle à négocier"],
            prime_de_risque_suggeree=prime,
        )

    if max_ltv_b < SEUIL_LTV_MAX:
        return Decision(
            statut="accord_conditionnel",
            justification=(
                f"LTV maximal projeté sans travaux ({max_ltv_a:.1%}) dépasse {SEUIL_LTV_MAX:.0%} : le bien seul ne couvrirait plus le prêt. "
                f"Avec les travaux recommandés réalisés, le LTV maximal redescend à {max_ltv_b:.1%}."
            ),
            conditions=recommandations_prioritaires + ["Travaux à réaliser avant ou au déblocage des fonds"],
            prime_de_risque_suggeree=prime,
        )

    return Decision(
        statut="refus",
        justification=(
            f"Même avec les travaux recommandés réalisés, le LTV maximal projeté ({max_ltv_b:.1%}) dépasse {SEUIL_LTV_MAX:.0%}. "
            "Le bien ne peut pas couvrir le capital emprunté sur la durée du prêt dans ce scénario."
        ),
        prime_de_risque_suggeree=prime,
    )
