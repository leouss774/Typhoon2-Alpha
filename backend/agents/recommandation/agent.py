"""Agent Recommandation RAG (Agent #2).

Reçoit les scores + risques dominants + caractéristiques maison,
interroge ChromaDB pour les fiches techniques pertinentes,
et génère une liste priorisée de travaux avec coûts et gains.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.agent_graph.state import AnalyseRisque, TravauxRecommandation
from backend.agents.recommandation.vectordb import RecommandationVectorDB

logger = logging.getLogger(__name__)


def generer_recommandations(
    analyse_risque: AnalyseRisque | None,
    score_global: float | None,
    scores_par_alea: dict[str, float],
    client_form: dict,
) -> list[TravauxRecommandation]:
    """Génère les recommandations de travaux via RAG.

    Interroge ChromaDB sur les risques dominants, puis structure
    la réponse avec coûts et gains de résilience.

    Returns:
        Liste priorisée de TravauxRecommandation.
    """
    if analyse_risque is None:
        logger.warning("Analyse risque manquante, retour liste vide")
        return []

    risques_dominants = analyse_risque.risques_dominants
    if not risques_dominants:
        logger.info("Aucun risque dominant, pas de recommandations")
        return []

    # Interroger la base vectorielle
    db = RecommandationVectorDB()
    query = _construire_requete(risques_dominants, client_form)
    fiches = db.rechercher(query=query, aleas_cibles=risques_dominants, k=8)

    if not fiches:
        # Fallback: recommandations génériques
        return _generer_recommandations_fallback(risques_dominants, client_form)

    recommandations = [
        TravauxRecommandation(
            priorite=i + 1,
            titre=f.get("titre", "Travaux recommandés"),
            description=f.get("description", ""),
            cout_estime_bas=float(f.get("cout_bas", 0)),
            cout_estime_haut=float(f.get("cout_haut", 0)),
            gain_resilience_pct=min(float(f.get("gain_resilience", 0)), 100.0),
            aleas_adresses=f.get("aleas_cibles", risques_dominants),
        )
        for i, f in enumerate(fiches)
    ]

    return recommandations


def _construire_requete(risques: list[str], client_form: dict) -> str:
    """Construit une requête de recherche RAG à partir des risques."""
    materiaux = client_form.get("materiau_principal", "maçonnerie")
    type_bien = client_form.get("type_bien", "maison")
    annee = client_form.get("annee_construction", 2000)

    risques_str = ", ".join(risques)
    return f"Travaux de rénovation pour {type_bien} en {materiaux} (construit en {annee}) exposée à {risques_str}. Solutions de renforcement et adaptation."


def _generer_recommandations_fallback(risques: list[str], client_form: dict) -> list[TravauxRecommandation]:
    """Génère des recommandations par défaut si le RAG ne trouve rien."""
    base_recommandations = {
        "rga": TravauxRecommandation(
            priorite=1,
            titre="Renforcement des fondations",
            description="Traitement des sols argileux par injection de résine expansive et reprise en sous-œuvre des fondations pour stabiliser la structure face au retrait-gonflement.",
            cout_estime_bas=8000,
            cout_estime_haut=25000,
            gain_resilience_pct=70.0,
            aleas_adresses=["rga"],
        ),
        "inondation": TravauxRecommandation(
            priorite=1,
            titre="Drainage périphérique",
            description="Installation d'un système de drainage périphérique avec pompe de relevage et clapets anti-retour pour protéger le sous-sol et les fondations des infiltrations.",
            cout_estime_bas=5000,
            cout_estime_haut=15000,
            gain_resilience_pct=65.0,
            aleas_adresses=["inondation"],
        ),
        "tempete": TravauxRecommandation(
            priorite=2,
            titre="Renforcement de la toiture",
            description="Pose de fixations anti-arrachement, renforcement de la charpente et remplacement des tuiles par des modèles plus résistants aux vents violents.",
            cout_estime_bas=6000,
            cout_estime_haut=18000,
            gain_resilience_pct=55.0,
            aleas_adresses=["tempete"],
        ),
        "feu_foret": TravauxRecommandation(
            priorite=2,
            titre="Isolation pare-feu extérieure",
            description="Traitement ignifuge des bardages bois, installation de volets coupe-feu et création d'une zone pare-feu périphérique (débroussaillement renforcé).",
            cout_estime_bas=4000,
            cout_estime_haut=12000,
            gain_resilience_pct=60.0,
            aleas_adresses=["feu_foret"],
        ),
    }

    recommandations = []
    for risque in risques:
        if risque in base_recommandations:
            rec = base_recommandations[risque].model_copy()
            rec.priorite = len(recommandations) + 1
            recommandations.append(rec)

    if not recommandations:
        recommandations.append(TravauxRecommandation(
            priorite=1,
            titre="Audit structurel complet",
            description="Réalisation d'un audit complet de la structure du bâtiment par un bureau d'études spécialisé en risques climatiques.",
            cout_estime_bas=2000,
            cout_estime_haut=5000,
            gain_resilience_pct=30.0,
            aleas_adresses=risques,
        ))

    return recommandations
