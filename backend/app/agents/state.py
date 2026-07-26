"""
TyphoonState — etat partage entre les noeuds du StateGraph LangGraph (cf.
README racine, section "Architecture multi-agents" : "Les agents
communiquent exclusivement via un etat partage").

Un TypedDict (pas un modele Pydantic strict), pour la meme raison que
`schemas/building_data.py` : chaque noeud n'ecrit qu'un sous-ensemble de
cles, et on ne veut pas qu'une validation stricte sur l'etat intermediaire
fasse echouer le graphe avant meme d'avoir atteint le noeud qui produit le
champ manquant.
"""

from __future__ import annotations

from typing import Any, TypedDict


class TyphoonState(TypedDict, total=False):
    # Entree
    adresse: str
    formulaire: dict[str, Any] | None

    # Ecrit par collector_agent
    building_data: dict[str, Any]

    # Ecrit par scoring_agent
    risk_scores: dict[str, Any]

    # Ecrit par digital_twin_agent (sortie finale, cf. contrat "Jumeau
    # numerique 3D" du README)
    digital_twin: dict[str, Any]
