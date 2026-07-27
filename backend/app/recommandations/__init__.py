"""
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
"""
