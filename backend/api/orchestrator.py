"""Orchestrateur principal — utilisant le graphe LangGraph Typhoon.

Point d'entree : run_analysis(form_data, session_id)
  → cree le state initial
  → invoque le graphe LangGraph (collect_georisques → generate_recommandations → assemble_output)
  → retourne le JSON final pret pour le frontend

Avantages par rapport a l'ancienne version :
  - Flux clair et sequentiel (graphe, pas de code spaghetti)
  - State type (Pydantic) — pas de dicts implicites
  - Chaque etape est un noeud isole et testable
  - Facile a etendre (ajouter un noeud = 3 lignes)
"""

from __future__ import annotations

import logging
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_graph.graph import run_typhoon_graph

logger = logging.getLogger(__name__)


def run_analysis(
    form_data: dict,
    session_id: str | None = None,
) -> dict:
    """Point d'entree principal de l'analyse.

    Utilise le graphe LangGraph pour orchestrer :
      1. Collecte des donnees Georisques
      2. Generation des recommandations par zone
      3. Assemblage du JSON final

    Args:
        form_data: Donnees du formulaire client
        session_id: Identifiant de session (optionnel)

    Returns:
        JSON final complet pour le dashboard + jumeau numerique
    """
    session_id = session_id or f"session-{uuid.uuid4().hex[:12]}"
    adresse = form_data.get("adresse", "")

    logger.info(f"Demarrage analyse via LangGraph pour : {adresse} (session: {session_id})")

    # Execution du graphe LangGraph
    result = run_typhoon_graph(
        session_id=session_id,
        client_form=form_data,
        raw_data={},
    )

    if result.get("erreur"):
        logger.error(f"Erreur graphe : {result['erreur']}")
    else:
        score = result.get("analyse_risques", {}).get("score", {}).get("global", "?")
        nb_recos = result.get("recommandations", {}).get("nb_recommandations", 0)
        logger.info(f"Analyse terminee - score: {score}/100, {nb_recos} recommandations")

    return result
