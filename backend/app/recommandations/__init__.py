"""
<<<<<<< HEAD
app.recommandations — Agent recommandations (RAG), integre comme noeud
LangGraph (cf. recommendation_travaux/PROMPT_INTEGRATION_ouss.md).

Ce package contient le code fourni par la collegue (recommendation_travaux/),
refactore en fonction pure appelable depuis le graphe :
  - config.py           reglages (modeles Mistral, chemins data/, top_k)
  - mistral_client.py   client Mistral (chat_json, embed_texts)
  - mapping.py          alignement du vocabulaire zones/aleas avec scoring_agent
  - rag_engine.py       generate_recommendations(house, index) + chargement de l'index

Voir app/agents/recommandations_agent.py pour le noeud du graphe, et
app/main.py (evenement startup) pour le chargement unique de l'index en memoire.
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
>>>>>>> agent/recommandation-RAG
"""
