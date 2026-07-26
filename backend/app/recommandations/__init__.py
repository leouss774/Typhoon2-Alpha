"""
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
"""
