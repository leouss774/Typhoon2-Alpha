"""
<<<<<<< HEAD
Module recommandations de travaux (agent RAG "rag_agent" du graphe LangGraph Typhoon).

Copie refactorée de recommendation_travaux-main (dépôt de la collègue en charge de ce
noeud), voir PROMPT_INTEGRATION_ouss.md et GUIDE_DEMARRAGE.md dans ce même dépôt
d'origine pour le contexte complet (phase de curation Agent 1 -> référentiel validé
-> index vectoriel -> Agent 2 RAG en production).

Seule la partie "production" (Agent 2) est embarquée ici : data/index.json (déjà
construit, embeddings Mistral) et data/referentiel.json (pour référence / audit). La
phase de curation (agent1_extract.py, populate_registry.py, les PDF sources) reste
dans le dépôt recommendation_travaux-main, qui fait foi si le référentiel doit être
regénéré un jour.
=======
recommandations — noeud LangGraph "recommandations de travaux" (cf.
PROMPT_INTEGRATION_ouss.md dans backend/recommendation_travaux-main/).

Ce package est l'integration, dans le backend orchestrateur, de l'agent RAG
fourni separement (dossier recommendation_travaux-main/ a la racine de
backend/, garde tel quel comme reference / CLI autonome). Il expose :

- `service.get_index()` / `service.generate_recommendations(...)` : le coeur
  RAG (recherche + appel Mistral), rendu importable et sans I/O disque a
  chaque appel (index charge une seule fois, cf. service.py).
- `mapping.build_house_payload(...)` / `mapping.merge_recommendations(...)` :
  la traduction entre le contrat de state.risk_scores (produit par
  app.scoring.risk_model) et le contrat JSON attendu par l'agent RAG
  (adresse/bien/zones[].risques), dans les deux sens.
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314
"""
