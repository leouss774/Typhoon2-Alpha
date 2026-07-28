"""
Agent de suivi.

Ne recalcule rien lui-même : il produit le plan de suivi (fréquences, seuils,
sources de données à interroger) qui sera exécuté périodiquement par
l'orchestrateur, en rappelant les autres agents à intervalle régulier.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from connectors import dvf_connector
from connectors import georisques_connector


@dataclass
class PlanDeSuivi:
    frequence_indices_marche: str = "trimestrielle"
    frequence_risque_climatique: str = "mensuelle"
    seuil_alerte_banque: float = 0.90
    seuil_reexpertise: float = 1.00
    sources: List[str] = field(default_factory=lambda: [
        "DVF (data.gouv.fr) - indices de transactions",
        "Indices notaires-INSEE - prix des logements anciens",
        "Géorisques (data.gouv.fr) - aléas RGA/inondation/sismique",
        "CCR - projections de sinistralité climatique",
        "Déclarations de sinistre (si connecté à un assureur partenaire)",
    ])
    declencheurs_evenementiels: List[str] = field(default_factory=lambda: [
        "Sinistre déclaré sur le bien",
        "Nouvelle classification de zone à risque (Géorisques)",
        "Preuve de réalisation des travaux recommandés fournie par le client",
    ])


def executer_cycle_suivi_reel(
    lat: float,
    lon: float,
    valeur_reference: float,
    prix_m2_reference: float,
    capital_restant_du: float,
    code_exposition_rga_reference: Optional[str] = None,
    nb_catnat_reference: Optional[int] = None,
) -> dict:
    """
    Exécute un vrai cycle de suivi : interroge DVF pour l'évolution du marché
    local et Géorisques pour toute dégradation du risque, puis recalcule le
    LTV actualisé.

    Ne masque jamais une panne d'API : si une source est indisponible, le champ
    correspondant est explicitement marqué "indisponible", jamais deviné.
    """
    resultat = {
        "marche": {"statut": "ok"},
        "risque": {"statut": "ok"},
    }

    # --- Marché : DVF ---
    try:
        ratio = dvf_connector.indice_evolution(
            prix_m2_reference=prix_m2_reference, lat=lat, lon=lon
        )
        if ratio is None:
            resultat["marche"] = {"statut": "aucune_donnee", "message": "Aucune transaction DVF trouvée dans le rayon."}
            valeur_actualisee = valeur_reference
        else:
            valeur_actualisee = round(valeur_reference * ratio, 2)
            resultat["marche"] = {"statut": "ok", "ratio_evolution_marche": ratio, "valeur_actualisee": valeur_actualisee}
    except dvf_connector.DVFIndisponible as e:
        resultat["marche"] = {"statut": "indisponible", "erreur": str(e)}
        valeur_actualisee = valeur_reference  # dernière valeur connue, pas une supposition nouvelle

    # --- Risque : Géorisques ---
    try:
        detection = georisques_connector.detecter_nouvelle_alerte(
            lat, lon, code_exposition_rga_reference, nb_catnat_reference
        )
        resultat["risque"] = {"statut": "ok", **detection}
    except georisques_connector.GeorisquesIndisponible as e:
        resultat["risque"] = {"statut": "indisponible", "erreur": str(e)}

    # --- LTV actualisé ---
    ltv_actualise = capital_restant_du / valeur_actualisee if valeur_actualisee > 0 else float("inf")
    plan = PlanDeSuivi()

    resultat["ltv_actualise"] = round(ltv_actualise, 4)
    resultat["alerte_banque"] = ltv_actualise >= plan.seuil_alerte_banque
    resultat["reexpertise_requise"] = (
        ltv_actualise >= plan.seuil_reexpertise
        or bool(resultat["risque"].get("alertes"))
    )

    return resultat


def generer_plan(ltv_actuel: float) -> dict:
    plan = PlanDeSuivi()
    alerte = ltv_actuel >= plan.seuil_alerte_banque
    reexpertise = ltv_actuel >= plan.seuil_reexpertise
    return {
        "frequence_indices_marche": plan.frequence_indices_marche,
        "frequence_risque_climatique": plan.frequence_risque_climatique,
        "seuil_alerte_banque": plan.seuil_alerte_banque,
        "seuil_reexpertise": plan.seuil_reexpertise,
        "sources": plan.sources,
        "declencheurs_evenementiels": plan.declencheurs_evenementiels,
        "statut_actuel": {
            "ltv_actuel": ltv_actuel,
            "alerte_declenchee": alerte,
            "reexpertise_requise": reexpertise,
        },
    }
