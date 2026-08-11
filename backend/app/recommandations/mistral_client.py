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

from mistralai.client import Mistral

from app.core.config import settings

CHAT_MODEL = "mistral-small-latest"
EMBED_MODEL = "mistral-embed"
REQUEST_TIMEOUT_MS = 300_000  # 5 minutes, cf. repo source (chunks volumineux)
THROTTLE_SECONDS = 0.3  # reduit : le retry backoff gere les rares 429

# Limite a 1000 tokens pour forcer la concision des recommandations
# (cf. amelioration_recommandation.md, section 2)
CHAT_MAX_TOKENS = 1000

_client: Mistral | None = None
_cached_api_key: str | None = None


def get_client() -> Mistral:
    global _client, _cached_api_key
    current_key = settings.mistral_api_key
    if _client is None or _cached_api_key != current_key:
        if not current_key:
            raise RuntimeError(
                "MISTRAL_API_KEY manquant. Renseigne-la dans le .env racine "
                "du projet (voir .env.example à la racine)."
            )
        _client = Mistral(api_key=current_key, timeout_ms=REQUEST_TIMEOUT_MS)
        _cached_api_key = current_key
    return _client


def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "429" in msg or "rate_limited" in msg or "rate limit" in msg


def _is_capacity_error(e: Exception) -> bool:
    """Une saturation du service/model tier n'est pas un quota temporaire.

    Mistral renvoie le code 3505 dans ce cas. Attendre 20 puis 40 secondes
    dans une requete HTTP ne libere pas cette capacite et rend le diagnostic
    inutilisable. Le niveau appelant gere deja cet echec en mode fail-soft.
    """
    msg = str(e).lower()
    return (
        "request_tier_capacity_exceeded" in msg
        or "service tier capacity exceeded" in msg
        or '"code":"3505"' in msg.replace(" ", "")
    )


def _backoff_seconds(e: Exception, attempt: int) -> float:
    if _is_rate_limit_error(e):
        return min(60, 20 * (attempt + 1))
    return 5 * (attempt + 1)


def chat_json(
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 5,
    max_tokens: int | None = None,
) -> dict:
    """Appelle le modele de chat Mistral et force une reponse JSON.

    `max_tokens` par defaut = CHAT_MAX_TOKENS (1000, concision des
    recommandations travaux). Le rapport narratif (introduction + sections +
    synthese + obligations) depasse facilement ce plafond et se retrouvait
    tronque en plein JSON ("Unterminated string") : il passe explicitement
    max_tokens=4000 (cf. rapport_narratif.py).
    """
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
                max_tokens=max_tokens or CHAT_MAX_TOKENS,
            )
            content = response.choices[0].message.content
            time.sleep(THROTTLE_SECONDS)
            if isinstance(content, list):
                text_parts = []
                for chunk in content:
                    text = getattr(chunk, "text", None)
                    if isinstance(text, str):
                        text_parts.append(text)
                    elif hasattr(text, "text"):
                        text_parts.append(str(text.text))
                content = "".join(text_parts)
            return json.loads(content)
        except Exception as e:
            last_err = e
            print(f"    [retry {attempt + 1}/{max_retries}] erreur Mistral chat: {e}")
            if _is_capacity_error(e) or attempt == max_retries - 1:
                break
            wait = _backoff_seconds(e, attempt)
            print(f"    -> attente {wait:.0f}s avant nouvelle tentative")
            time.sleep(wait)
    raise RuntimeError(f"Echec appel Mistral (chat) apres {max_retries} tentatives: {last_err}")


def chat_text(
    system_prompt: str,
    messages: list[dict[str, str]],
    max_retries: int = 5,
    max_tokens: int | None = None,
) -> str:
    """Appelle le modele de chat Mistral en texte libre (multi-tours).

    Utilise par la route `POST /chat` de l'assistant conversationnel du
    jumeau numerique. Accepte un historique de messages
    ``[{role: system|user|assistant, content: ...}, ...]`` (le system_prompt
    est prependu en premiere position) et renvoie la reponse texte.
    """
    client = get_client()
    last_err: Exception | None = None
    full_messages = [{"role": "system", "content": system_prompt}] + list(messages)
    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model=CHAT_MODEL,
                messages=full_messages,
                temperature=0.2,
                max_tokens=max_tokens or CHAT_MAX_TOKENS,
            )
            content = response.choices[0].message.content
            time.sleep(THROTTLE_SECONDS)
            if isinstance(content, list):
                text_parts = []
                for chunk in content:
                    text = getattr(chunk, "text", None)
                    if isinstance(text, str):
                        text_parts.append(text)
                    elif hasattr(text, "text"):
                        text_parts.append(str(text.text))
                content = "".join(text_parts)
            return str(content)
        except Exception as e:
            last_err = e
            print(f"    [retry chat_text {attempt + 1}/{max_retries}] erreur Mistral: {e}")
            if _is_capacity_error(e) or attempt == max_retries - 1:
                break
            wait = _backoff_seconds(e, attempt)
            print(f"    -> attente {wait:.0f}s avant nouvelle tentative")
            time.sleep(wait)
    raise RuntimeError(
        f"Echec appel Mistral (chat_text) apres {max_retries} tentatives: {last_err}"
    )


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
            print(f"    [retry embeddings {attempt + 1}/{max_retries}] erreur Mistral: {e}")
            if _is_capacity_error(e) or attempt == max_retries - 1:
                break
            wait = _backoff_seconds(e, attempt)
            print(f"    -> attente {wait:.0f}s avant nouvelle tentative")
            time.sleep(wait)
    raise RuntimeError(f"Echec appel Mistral (embeddings) apres {max_retries} tentatives: {last_err}")
