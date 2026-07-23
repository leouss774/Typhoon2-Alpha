"""Nœud : validation du rapport final.

Vérifie la cohérence des données. Si des erreurs sont détectées,
le graphe peut reboucler vers l'analyse pour correction.
"""

from __future__ import annotations

from backend.agent_graph.state import TyphoonState


def validate_rapport_node(state: TyphoonState) -> dict:
    """Valide la cohérence du rapport final."""
    errors: list[str] = []

    if state.rapport_final is None:
        errors.append("Le rapport final est vide")

    if state.analyse_risque is None:
        errors.append("L'analyse des risques est manquante")

    if not state.recommandations:
        errors.append("Aucune recommandation générée")

    if state.score_global is None:
        errors.append("Le score global est manquant")

    passed = len(errors) == 0

    return {
        "validation_errors": errors,
        "validation_passed": passed,
        "next_node": "__end__" if passed else "analyste_risque",
    }
