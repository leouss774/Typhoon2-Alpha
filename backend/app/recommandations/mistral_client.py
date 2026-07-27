"""
Client Mistral (copie de recommendation_travaux/utils/mistral_client.py,
import relatif adapte au package app.recommandations).

Les appels chat_json / embed_texts restent synchrones (SDK Mistral) : le
noeud LangGraph qui les utilise (app/agents/recommandations_agent.py) est
un noeud sync, cohere avec scoring_agent/digital_twin_agent qui le sont
deja — pas besoin de threadpool tant que le graphe n'est pas appele
massivement en parallele (cf. PROMPT_INTEGRATION_ouss.md, remarque sur
run_in_executor : a revisiter si la charge l'exige).
"""

from __future__ import annotations

import json
import time

from mistralai.client import Mistral

from . import config

_client: Mistral | None = None


def get_client() -> Mistral:
    global _client
    if _client is None:
        if not config.MISTRAL_API_KEY:
            raise RuntimeError(
                "MISTRAL_API_KEY manquant. Ajoute la ligne MISTRAL_API_KEY=ta_cle "
                "dans backend/.env"
            )
        _client = Mistral(api_key=config.MISTRAL_API_KEY, timeout_ms=config.REQUEST_TIMEOUT_MS)
    return _client


def chat_json(system_prompt: str, user_prompt: str, max_retries: int = 5) -> dict:
    """Appelle le modele de chat Mistral et force une reponse JSON."""
    client = get_client()
    last_err = None
    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model=config.CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            last_err = e
            print(f"    [retry {attempt + 1}/{max_retries}] erreur Mistral: {e}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Echec appel Mistral (chat) apres {max_retries} tentatives: {last_err}")


def embed_texts(texts: list) -> list:
    """Retourne la liste des vecteurs d'embedding pour une liste de textes."""
    client = get_client()
    response = client.embeddings.create(model=config.EMBED_MODEL, inputs=texts)
    return [item.embedding for item in response.data]
