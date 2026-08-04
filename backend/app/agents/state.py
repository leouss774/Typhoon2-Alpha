"""
TyphoonState — etat partage entre les noeuds du StateGraph LangGraph (cf.
README racine, section "Architecture multi-agents" : "Les agents
communiquent exclusivement via un etat partage").

<<<<<<< HEAD
Graphe actuel (voir app/agents/graph.py) :

    collector_agent -> scoring_agent -> risk_scoring_agent -> rag_agent -> digital_twin_agent

Deux noeuds de scoring coexistent, avec deux cles d'etat distinctes (voir
docstring de risk_scoring_agent.py pour le detail du pourquoi) :
  - `risk_scores`            : derivation qualitative (risque/zone metier),
    format attendu par rag_agent (recommandations sourcees).
  - `risk_scores_numeriques` : score 0-100 par zone directionnelle, format
    attendu par digital_twin_agent (rendu 3D).

Un TypedDict (pas un modele Pydantic strict) pour la meme raison que
=======
Un TypedDict (pas un modele Pydantic strict), pour la meme raison que
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314
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
<<<<<<< HEAD
=======
    copernicus: bool  # True = activer Copernicus (CDS), False = desactive, champs null
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314

    # Ecrit par collector_agent
    building_data: dict[str, Any]

<<<<<<< HEAD
    # Ecrit par scoring_agent (qualitatif, 5 zones metier -> rag_agent)
    risk_scores: dict[str, Any]

    # Ecrit par risk_scoring_agent (0-100, 7 zones directionnelles -> digital_twin_agent)
    risk_scores_numeriques: dict[str, Any]

    # Ecrit par rag_agent (optionnel : peut manquer si Mistral n'est pas configure)
    recommendations: dict[str, Any]
=======
    # Ecrit par scoring_agent
    risk_scores: dict[str, Any]

    # Ecrit par interpretation_agent
    interpretations: dict[str, Any]
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314

    # Ecrit par digital_twin_agent (sortie finale, cf. contrat "Jumeau
    # numerique 3D" du README)
    digital_twin: dict[str, Any]
