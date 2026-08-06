"""
Client Mistral (chat + embeddings) pour l'agent recommandations.

Repris de recommendation_travaux-main/utils/mistral_client.py, adapte pour
lire la cle API depuis app.core.config.settings (meme mecanisme que le
reste du backend : backend/.env) plutot que depuis un config.py/.env propre
au sous-projet.

Appels synchrones (SDK mistralai) : le noeud LangGraph qui appelle
`generate_recommendations` les execute via `asyncio.to_thread` pour ne pas
bloquer la boucle asyncio de FastAPI (cf. app/agents/recommandations_agent.py).
"""

from __future__ import annotations

import json
import time

# Import depuis le sous-module `client` : l'init de paquet top-level n'est
# pas present dans toutes les versions installees du SDK mistralai (en 2.8.0
# l'import `from mistralai import Mistral` echoue sur un paquet namespace
# vide), alors que `mistralai.client` expose toujours la classe Mistral.
from mistralai.client import Mistral

from app.core.config import settings

CHAT_MODEL = "mistral-small-latest"
EMBED_MODEL = "mistral-embed"
# 15s : assez long pour une reponse Mistral normale, assez court pour
# basculer rapidement sur le fallback déterministe (recommandations/fallback.py)
# quand l'API est lente ou down. 5 min (ancienne valeur) faisait attendre
# l'utilisateur >10 min quand Mistral est indisponible.
REQUEST_TIMEOUT_MS = 15_000
THROTTLE_SECONDS = 0.1  # reduit : le fallback prend le relais en cas de 429

# Limite a 1000 tokens pour forcer la concision des recommandations
# (cf. amelioration_recommandation.md, section 2)
CHAT_MAX_TOKENS = 1000

# Limite plus large pour le chat conversationnel (syntheses, tableaux) :
# CHAT_MAX_TOKENS (1000) tronquait les reponses du chat en plein milieu
# d'une synthese. Le prompt SYSTEM_PROMPT (route /chat) borne la longueur
# attendue, ce max n'est qu'une securite contre les reponses fleuves.
CHAT_TEXT_MAX_TOKENS = 1800

_client: Mistral | None = None


def get_client() -> Mistral:
    global _client
    if _client is None:
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
        return min(2, 1.5 * (attempt + 1))
    return 0.5 * (attempt + 1)


def chat_json(system_prompt: str, user_prompt: str, max_retries: int = 1) -> dict:
    """Appelle le modele de chat Mistral et force une reponse JSON."""
    client = get_client()
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
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


def chat_text(system_prompt: str, messages: list[dict], max_retries: int = 2) -> str:
    """Appelle le modele de chat Mistral en texte libre, multi-tours.

    `messages` : liste de {"role": "user"|"assistant", "content": str}
    (l'historique de la conversation, le system prompt etant passe a
    part). Contrairement a chat_json, la reponse n'est PAS forcee en JSON :
    c'est le mode conversationnel du chat du jumeau numerique.
    """
    client = get_client()
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model=CHAT_MODEL,
                messages=[{"role": "system", "content": system_prompt}, *messages],
                temperature=0.7,
                max_tokens=CHAT_TEXT_MAX_TOKENS,
            )
            content = response.choices[0].message.content
            time.sleep(THROTTLE_SECONDS)
            # SDK mistralai : `content` est soit un str, soit une liste de
            # blocs content (modalites) selon la version — on normalise.
            if isinstance(content, list):
                return "".join(getattr(part, "text", "") or "" for part in content)
            return content or ""
        except Exception as e:
            last_err = e
            wait = _backoff_seconds(e, attempt)
            print(f"    [retry {attempt + 1}/{max_retries}] erreur Mistral chat_text: {e}")
            print(f"    -> attente {wait:.0f}s avant nouvelle tentative")
            time.sleep(wait)
    raise RuntimeError(f"Echec appel Mistral (chat_text) apres {max_retries} tentatives: {last_err}")


def embed_texts(texts: list[str], max_retries: int = 1) -> list[list[float]]:
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
