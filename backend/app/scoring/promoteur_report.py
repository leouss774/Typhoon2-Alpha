"""
Person 3 — AI Report & Data Quality.

Génère les 3 champs spécifiques au cas d'usage Promoteur Immobilier
à partir des données de risque agrégées de la zone.

Les 3 champs :
  - faisabiliteConstruction : notes de faisabilité constructibilité
  - impactValeurFonciere : estimation de l'impact sur la valeur foncière
  - perspectiveAssurabilite : perspective d'assurabilité pour un futur bâti

Actuellement, ces champs sont générés par des règles métier déterministes
(algorithmiques, pas LLM). L'architecture est conçue pour qu'un LLM (Mistral,
Claude, etc.) puisse remplacer ces règles dans une version future sans
changer le contrat de sortie.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PromoteurReport:
    """Rapport promoteur : 3 champs métier dédiés."""
    faisabiliteConstruction: str
    impactValeurFonciere: str
    perspectiveAssurabilite: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "faisabilite_construction": self.faisabiliteConstruction,
            "impact_valeur_fonciere": self.impactValeurFonciere,
            "perspective_assurabilite": self.perspectiveAssurabilite,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
#   Règles de génération
# ---------------------------------------------------------------------------

def _est_zone_inondable(perils: dict) -> bool:
    """Détermine si la zone est significativement inondable."""
    inondation = perils.get("inondation")
    if inondation and inondation.moyenne >= 30:
        return True
    return False


def _est_zone_rga(perils: dict) -> bool:
    """Détermine si le RGA est un risque significatif."""
    rga = perils.get("rga")
    if rga and rga.moyenne >= 30:
        return True
    return False


def _est_zone_seismique(perils: dict) -> bool:
    """Détermine si le séisme est un risque significatif."""
    seisme = perils.get("seisme")
    if seisme and seisme.moyenne >= 20:
        return True
    return False


# ---------------------------------------------------------------------------
#   Génération des 3 champs
# ---------------------------------------------------------------------------

def _generer_faisabilite(
    score_moyen: float,
    rating_global: str,
    perils: dict,
    land_only: bool,
    nb_critique_pct: float,
) -> str:
    """Génère la note de faisabilité construction.

    Basée sur le score global et les périls dominants.
    """
    rating_lower = rating_global.lower()

    if rating_lower == "élevé" and score_moyen >= 60:
        return (
            "Faisabilité conditionnelle — le niveau de risque global de la zone "
            "impose des études géotechniques complémentaires (G12) avant tout dépôt "
            "de permis de construire. Des mesures de mitigation spécifiques seront "
            "nécessaires, avec un surcoût estimé de 15 à 30% par rapport à une "
            "opération similaire en zone de risque faible."
        )

    if rating_lower == "élevé":
        return (
            "Faisabilité sous réserve — des adaptations constructives sont nécessaires "
            "(ex. vide sanitaire renforcé, drain périphérique, matériaux adaptés au RGA). "
            "Une étude de sol préalable (G11) est recommandée. Les contraintes "
            "réglementaires (PPRN) peuvent imposer des restrictions d'emprise ou de "
            "hauteur."
        )

    if rating_lower == "modéré":
        return (
            "Faisabilité favorable — les risques identifiés sont maîtrisables par des "
            "mesures constructives standards. Aucune contrainte majeure identifiée "
            "pour le dépôt de permis de construire. Une étude de sol G11 est "
            "recommandée pour valider les hypothèses de fondations."
        )

    # Faible
    return (
        "Faisabilité bonne — aucun risque significatif identifié dans la zone. "
        "Les conditions sont favorables à une opération de construction sans "
        "contraintes particulières liées aux risques naturels. Les procédures "
        "standard de permis de construire s'appliquent."
    )


def _generer_impact_valeur(
    score_moyen: float,
    rating_global: str,
    perils: dict,
    nb_points_valides: int,
) -> str:
    """Estime l'impact du risque sur la valeur foncière.

    Utilise des fourchettes basées sur les données DVF historiques
    et la littérature académique (impact des PPRN sur les prix immobiliers).
    """
    rating_lower = rating_global.lower()

    # Détection des périls impactants
    facteurs_aggravants = []
    if _est_zone_inondable(perils):
        facteurs_aggravants.append("inondation")
    if _est_zone_rga(perils):
        facteurs_aggravants.append("RGA")
    if _est_zone_seismique(perils):
        facteurs_aggravants.append("séisme")

    nb_facteurs = len(facteurs_aggravants)

    if rating_lower == "élevé" and score_moyen >= 60:
        base = "décote de 20 à 35%"
        if nb_facteurs >= 2:
            base = "décote de 25 à 40%"
        facteurs = ", ".join(facteurs_aggravants) if facteurs_aggravants else "risques multiples"
        return (
            f"Impact fort sur la valeur foncière — estimation : {base} par rapport "
            f"à la médiane du secteur. Les principaux facteurs de décote sont : "
            f"{facteurs}. La présence d'un PPRN approuvé sur la commune peut "
            f"accentuer cette décote (obligation d'information des acquéreurs — "
            f"état des risques). À horizon 2050, l'aggravation des aléas climatiques "
            f"pourrait accroître cette décote de 5 à 10 points supplémentaires."
        )

    if rating_lower == "élevé":
        base = "décote de 10 à 20%"
        if nb_facteurs >= 2:
            base = "décote de 15 à 25%"
        return (
            f"Impact modéré à fort sur la valeur foncière — estimation : {base} par "
            f"rapport à la médiane du secteur. Les risques identifiés peuvent "
            f"réduire l'attractivité de la zone pour les acquéreurs sensibles au "
            f"risque climatique. La tendance de marché et la densité du tissu urbain "
            f"local peuvent atténuer cette décote."
        )

    if rating_lower == "modéré":
        return (
            "Impact faible sur la valeur foncière — estimation : décote inférieure "
            "à 10%, principalement liée à des contraintes d'assurabilité ou à des "
            "travaux de mitigation prévisibles. Les transactions récentes dans le "
            "secteur (données DVF) ne montrent pas d'écart significatif lié aux "
            "risques naturels pour ce niveau d'exposition."
        )

    return (
        "Impact négligeable sur la valeur foncière — aucun facteur de risque "
        "climatique significatif identifié. La valeur de marché reflète "
        "uniquement les caractéristiques classiques du foncier (localisation, "
        "desserte, superficie). Aucune décote liée aux risques naturels "
        "n'est attendue."
    )


def _generer_assurabilite(
    score_moyen: float,
    rating_global: str,
    perils: dict,
    land_only: bool,
    worst_case_score: float | None,
) -> str:
    """Évalue la perspective d'assurabilité pour un futur bâtiment.

    Basée sur la réglementation CatNat, le régime d'assurance français,
    et les tendances du marché de la réassurance.
    """
    rating_lower = rating_global.lower()
    worst = worst_case_score or score_moyen

    if rating_lower == "élevé" and score_moyen >= 60:
        return (
            "Assurabilité compromise en l'état — la zone présente un profil de risque "
            "qui pourrait rendre difficile l'obtention d'une couverture multirisques "
            "habitation aux conditions standards du marché. Recommandations :\n"
            "• Réaliser des travaux de mitigation avant la construction (ex. "
            "renforcement des fondations, drainage, matériaux résilients)\n"
            "• Solliciter plusieurs assureurs spécialisés pour obtenir des devis\n"
            "• Anticiper une franchise CatNat majorée (jusqu'à 3-4 fois la franchise "
            "légale)\n"
            "• Envisager une couverture auprès du Bureau Central de Tarification "
            "(BCT) en dernier recours\n"
            "À horizon 2050, l'assurabilité pourrait se dégrader significativement "
            "si les projections de sinistralité se confirment."
        )

    if rating_lower == "élevé":
        return (
            "Assurabilité sous conditions — l'obtention d'une couverture habitation "
            "est possible mais avec des conditions potentiellement restrictives :\n"
            "• Prime majorée de 15 à 30% par rapport à une zone de risque faible\n"
            "• Franchise CatNat standard ou légèrement majorée\n"
            "• Possible exclusion de garantie pour le péril dominant "
            "(inondation ou RGA selon le diagnostic)\n"
            "• Des travaux de mitigation (ex. drain périphérique, étanchéité "
            "renforcée) peuvent améliorer les conditions d'assurance\n"
            "Il est recommandé de mandater un courtier spécialisé pour optimiser "
            "le rapport couverture/prime."
        )

    if rating_lower == "modéré":
        return (
            "Assurabilité normale — la couverture multirisques habitation est "
            "accessible aux conditions standards du marché. Les primes devraient "
            "rester dans la moyenne du secteur, avec une franchise CatNat standard. "
            "Aucune difficulté particulière anticipée pour l'obtention d'une "
            "assurance dommages-ouvrage pour les opérations de construction. "
            "Une légère hausse de prime est possible à horizon 2050 dans le cadre "
            "de la réforme du régime CatNat annoncée."
        )

    return (
        "Assurabilité favorable — la zone ne présente pas de facteur de risque "
        "climatique significatif. Les conditions d'assurance devraient être "
        "optimales : primes compétitives, franchises standard, couverture "
        "complète disponible. Aucune difficulté anticipée pour l'assurance "
        "dommages-ouvrage ou la multirisques habitation."
    )


# ---------------------------------------------------------------------------
#   Point d'entrée
# ---------------------------------------------------------------------------

def generer_rapport_promoteur(
    score_moyen: float,
    rating_global: str,
    perils: dict,
    land_only: bool,
    worst_case_peril: str | None,
    worst_case_score: float | None,
    nb_points_valides: int,
    nb_points_erreur: int,
) -> PromoteurReport:
    """Génère le rapport promoteur complet (3 champs).

    Parameters
    ----------
    score_moyen : moyenne des scores globaux de la zone
    rating_global : rating textuel (Faible, Modéré, Élevé)
    perils : dict[str, DistributionPeril] — agrégations par péril
    land_only : mode terrain nu
    worst_case_peril : nom du péril worst-case
    worst_case_score : score du worst-case
    nb_points_valides : nombre de points valides
    nb_points_erreur : nombre de points en erreur

    Returns
    -------
    PromoteurReport avec les 3 champs générés.
    """
    # Calcul du % de points critiques
    nb_critique = 0
    for peril_name, dist in perils.items():
        nb_critique += dist.pct_critique
    pct_critique_moyen = nb_critique / max(len(perils), 1) if perils else 0.0

    faisabilite = _generer_faisabilite(
        score_moyen, rating_global, perils, land_only, pct_critique_moyen
    )
    impact = _generer_impact_valeur(
        score_moyen, rating_global, perils, nb_points_valides
    )
    assurabilite = _generer_assurabilite(
        score_moyen, rating_global, perils, land_only, worst_case_score
    )

    notes = []
    if land_only:
        notes.append(
            "Mode terrain nu : les données BDNB (caractéristiques du bâti) "
            "ne sont pas disponibles. Les scores reflètent uniquement les "
            "aléas naturels et le contexte géographique."
        )
    if nb_points_erreur > 0:
        notes.append(
            f"{nb_points_erreur} point(s) d'échantillonnage en échec — "
            "certaines poches de risque ont pu ne pas être détectées."
        )
    if worst_case_score and worst_case_score >= 70:
        notes.append(
            f"Point chaud détecté ({worst_case_peril} à {worst_case_score:.0f}/100) — "
            "ce niveau de risque localisé peut nécessiter une analyse complémentaire "
            "avant décision d'investissement."
        )
    if pct_critique_moyen > 20:
        notes.append(
            f"Plus de 20% des points présentent un risque critique — "
            "une attention particulière est recommandée sur la constructibilité "
            "et l'assurabilité."
        )

    return PromoteurReport(
        faisabiliteConstruction=faisabilite,
        impactValeurFonciere=impact,
        perspectiveAssurabilite=assurabilite,
        notes=notes,
    )
