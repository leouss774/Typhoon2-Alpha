"""
<<<<<<< HEAD
Client Mistral (copie de recommendation_travaux/utils/mistral_client.py,
import relatif adapte au package app.recommandations).

Les appels chat_json / embed_texts restent synchrones (SDK Mistral) : le
noeud LangGraph qui les utilise (app/agents/recommandations_agent.py) est
un noeud sync, cohere avec scoring_agent/digital_twin_agent qui le sont
deja — pas besoin de threadpool tant que le graphe n'est pas appele
massivement en parallele (cf. PROMPT_INTEGRATION_ouss.md, remarque sur
run_in_executor : a revisiter si la charge l'exige).
=======
Client Mistral (chat + embeddings) pour l'agent recommandations.

Repris de recommendation_travaux-main/utils/mistral_client.py, adapte pour
lire la cle API depuis app.core.config.settings (meme mecanisme que le
reste du backend : backend/.env) plutot que depuis un config.py/.env propre
au sous-projet.

Appels synchrones (SDK mistralai) : le noeud LangGraph qui appelle
`generate_recommendations` les execute via `asyncio.to_thread` pour ne pas
bloquer la boucle asyncio de FastAPI (cf. app/agents/recommandations_agent.py).
>>>>>>> agent/recommandation-RAG
"""

from __future__ import annotations

import json
import time

<<<<<<< HEAD
from mistralai import Mistral

from . import config
=======
from mistralai.client import Mistral

from app.core.config import settings

CHAT_MODEL = "mistral-large-latest"
EMBED_MODEL = "mistral-embed"
REQUEST_TIMEOUT_MS = 300_000  # 5 minutes, cf. repo source (chunks volumineux)
THROTTLE_SECONDS = 3  # anti rate-limit, cf. repo source

# Plafond genereux : les recommandations detaillees (champ "explication",
# plusieurs recommandations par reponse) tiennent sur un JSON plus long que
# la version initiale courte -- evite une reponse tronquee (JSON invalide).
CHAT_MAX_TOKENS = 4000
>>>>>>> agent/recommandation-RAG

_client: Mistral | None = None


def get_client() -> Mistral:
    global _client
    if _client is None:
<<<<<<< HEAD
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
=======
        if not settings.mistral_api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY manquant. Renseigne-la dans backend/.env "
                "(voir backend/.env.example)."
            )
        _client = Mistral(api_key=settings.mistral_api_key, timeout_ms=REQUEST_TIMEOUT_MS)
    return _client


def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "429" in msg or "rate_limited" in msg or "rate limit" in msg


def _backoff_seconds(e: Exception, attempt: int) -> float:
    if _is_rate_limit_error(e):
        return min(60, 20 * (attempt + 1))
    return 5 * (attempt + 1)


def chat_json(system_prompt: str, user_prompt: str, max_retries: int = 5) -> dict:
    """Appelle le modele de chat Mistral et force une reponse JSON."""
    client = get_client()
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model=CHAT_MODEL,
>>>>>>> agent/recommandation-RAG
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
<<<<<<< HEAD
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
=======
                max_tokens=CHAT_MAX_TOKENS,
            )
            content = response.choices[0].message.content
            time.sleep(THROTTLE_SECONDS)
            return json.loads(content)
        except Exception as e:
            last_err = e
            wait = _backoff_seconds(e, attempt)
            print(f"    [retry {attempt + 1}/{max_retries}] erreur Mistral chat: {e}")
            print(f"    -> attente {wait:.0f}s avant nouvelle tentative")
            time.sleep(wait)
    raise RuntimeError(f"Echec appel Mistral (chat) apres {max_retries} tentatives: {last_err}")


def embed_texts(texts: list[str], max_retries: int = 5) -> list[list[float]]:
    client = get_client()
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(model=EMBED_MODEL, inputs=texts)
            time.sleep(THROTTLE_SECONDS)
            return [item.embedding for item in response.data]
        except Exception as e:
            last_err = e
            wait = _backoff_seconds(e, attempt)
            print(f"    [retry embeddings {attempt + 1}/{max_retries}] erreur Mistral: {e}")
            print(f"    -> attente {wait:.0f}s avant nouvelle tentative")
            time.sleep(wait)
    raise RuntimeError(f"Echec appel Mistral (embeddings) apres {max_retries} tentatives: {last_err}")
>>>>>>> agent/recommandation-RAG
