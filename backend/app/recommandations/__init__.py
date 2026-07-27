"""
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
"""
