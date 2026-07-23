"""Nœud : assemble le rapport final à partir de toutes les analyses.

Consolide les scores, l'analyse LLM, les recommandations et les projections
dans un rapport structuré prêt pour le dashboard.
"""

from __future__ import annotations

from backend.agent_graph.state import TyphoonState, RapportFinal
from backend.services.drisas.projections import projeter_scores_2050


def generate_report_node(state: TyphoonState) -> dict:
    """Assemble le rapport final complet."""
    projection_2050 = projeter_scores_2050(
        scores_actuels=state.scores_par_alea,
        localisation=state.client_form.get("adresse", ""),
    )

    rapport = RapportFinal(
        score_global=state.score_global,
        analyse_risque=state.analyse_risque,
        recommandations=state.recommandations,
        projection_2050=projection_2050,
        synthese_executive=_generer_synthese(
            score=state.score_global,
            risques=state.analyse_risque.risques_dominants,
            nb_recos=len(state.recommandations),
        ),
    )

    return {
        "rapport_final": rapport,
        "next_node": "validate_rapport",
    }


def _generer_synthese(score: float, risques: list[str], nb_recos: int) -> str:
    """Génère une synthèse exécutive lisible par le client."""
    niveau = "faible" if score < 25 else "modéré" if score < 50 else "élevé" if score < 75 else "critique"
    risques_str = ", ".join(risques[:3])
    return (
        f"Le niveau de risque global est **{niveau}** (score: {score:.0f}/100). "
        f"Les risques dominants identifiés sont : {risques_str}. "
        f"{nb_recos} recommandations de travaux sont proposées pour améliorer la résilience du bien."
    )
